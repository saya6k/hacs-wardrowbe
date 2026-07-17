"""HTTP client for the Wardrowbe REST API.

Authentication is two-legged:

* An external ``TokenProvider`` produces the payload accepted by Wardrowbe's
  ``POST /api/v1/auth/sync`` endpoint — either an OIDC ``id_token`` or, in
  dev-mode installs, an ``external_id``.
* ``WardrowbeClient`` exchanges that payload for a Wardrowbe-issued JWT,
  caches it, and re-syncs on expiry or 401.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import aiohttp
from aiohttp import ClientSession

from .const import (
    API_ANALYTICS,
    API_AUTH_CONFIG,
    API_AUTH_SESSION,
    API_AUTH_SYNC,
    API_CAPABILITIES,
    API_HEALTH,
    API_ITEMS,
    API_NOTIFICATIONS_HISTORY,
    API_NOTIFICATIONS_SETTINGS,
    API_OUTFIT_SUGGEST,
    API_OUTFITS,
    DEFAULT_TIMEOUT,
)

_LOGGER = logging.getLogger(__name__)

_JWT_REFRESH_LEEWAY = timedelta(hours=1)
_DEFAULT_JWT_TTL_SECONDS = 6 * 24 * 3600  # 6 days; Wardrowbe defaults to 7


class WardrowbeApiError(Exception):
    """Generic Wardrowbe API error.

    ``status`` carries the HTTP status code when the error originates from a
    non-2xx response, so callers can react to specific codes (e.g. a 503 from
    ``/outfits/suggest`` when the server has internal AI disabled).
    """

    def __init__(self, message: str, *, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


class WardrowbeAuthError(WardrowbeApiError):
    """Authentication failed and could not be recovered."""


class TokenProvider:
    """Produces the payload expected by Wardrowbe's /auth/sync endpoint."""

    async def async_get_sync_payload(self) -> dict[str, Any]:
        raise NotImplementedError


class DevTokenProvider(TokenProvider):
    """Sends external_id + synthesised email/display_name for dev-mode installs."""

    def __init__(
        self,
        external_id: str,
        *,
        email: str | None = None,
        display_name: str | None = None,
    ) -> None:
        self._external_id = external_id
        self._email = email or f"{external_id}@local"
        self._display_name = display_name or external_id

    async def async_get_sync_payload(self) -> dict[str, Any]:
        return {
            "external_id": self._external_id,
            "email": self._email,
            "display_name": self._display_name,
        }


class StaticIdTokenProvider(TokenProvider):
    """Wraps a fixed ``id_token`` — used during the config flow's first sync."""

    def __init__(self, id_token: str) -> None:
        self._id_token = id_token

    async def async_get_sync_payload(self) -> dict[str, Any]:
        return build_oidc_sync_payload(self._id_token)


def build_oidc_sync_payload(id_token: str) -> dict[str, Any]:
    """Decode an OIDC id_token and shape it for Wardrowbe's /auth/sync.

    Wardrowbe's endpoint expects the canonical OIDC claims spelled out as
    body fields (``external_id``, ``email``, ``display_name``); it does not
    decode the raw JWT itself. The id_token is sent alongside so that the
    server can still verify it if it wants.

    The signature is not verified here — we trust HA's OAuth flow to have
    received this token over an authenticated TLS channel from the
    pre-registered token endpoint.
    """
    claims = _decode_jwt_payload(id_token)
    sub = claims.get("sub")
    if not sub:
        raise WardrowbeAuthError("id_token is missing required `sub` claim")
    email = claims.get("email")
    display_name = (
        claims.get("name")
        or claims.get("preferred_username")
        or claims.get("nickname")
        or email
        or str(sub)
    )
    payload: dict[str, Any] = {
        "external_id": str(sub),
        "email": email or "",
        "display_name": display_name,
        "id_token": id_token,
    }
    return payload


def _decode_jwt_payload(id_token: str) -> dict[str, Any]:
    """Return the claims dict from a JWT without verifying the signature."""
    parts = id_token.split(".")
    if len(parts) != 3:
        raise WardrowbeAuthError("Malformed id_token (expected 3 dot-separated parts)")
    encoded = parts[1]
    pad = "=" * (-len(encoded) % 4)
    try:
        raw = base64.urlsafe_b64decode(encoded + pad)
        decoded = json.loads(raw)
    except (ValueError, binascii.Error, json.JSONDecodeError) as err:
        raise WardrowbeAuthError(f"Could not decode id_token payload: {err}") from err
    if not isinstance(decoded, dict):
        raise WardrowbeAuthError("id_token payload is not a JSON object")
    return decoded


class WardrowbeClient:
    """Async client for Wardrowbe's REST API."""

    def __init__(
        self,
        session: ClientSession,
        host: str,
        token_provider: TokenProvider,
        *,
        verify_ssl: bool = True,
        entry_id: str | None = None,
    ) -> None:
        self._session = session
        self._host = host.rstrip("/")
        self._token_provider = token_provider
        self._verify_ssl = verify_ssl
        self._entry_id = entry_id
        self._jwt: str | None = None
        self._jwt_expires_at: datetime | None = None
        self._sync_lock = asyncio.Lock()

    @property
    def host(self) -> str:
        return self._host

    # ---- unauthenticated probes ----

    async def async_health(self) -> bool:
        try:
            async with self._session.get(
                self._url(API_HEALTH),
                ssl=self._verify_ssl,
                timeout=aiohttp.ClientTimeout(total=DEFAULT_TIMEOUT),
            ) as resp:
                return resp.status == 200
        except aiohttp.ClientError:
            return False

    async def async_capabilities(self) -> dict[str, Any] | None:
        """Fetch the server's effective AI capabilities (public, no auth).

        Returns ``None`` on servers predating the endpoint (Wardrowbe < 1.4.0)
        or on any transport/HTTP error, so callers treat an unknown state as
        "assume enabled" rather than blocking actions.
        """
        try:
            async with self._session.get(
                self._url(API_CAPABILITIES),
                ssl=self._verify_ssl,
                timeout=aiohttp.ClientTimeout(total=DEFAULT_TIMEOUT),
            ) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json(content_type=None)
        except aiohttp.ClientError:
            return None
        return data if isinstance(data, dict) else None

    async def async_auth_config(self) -> dict[str, Any]:
        async with self._session.get(
            self._url(API_AUTH_CONFIG),
            ssl=self._verify_ssl,
            timeout=aiohttp.ClientTimeout(total=DEFAULT_TIMEOUT),
        ) as resp:
            resp.raise_for_status()
            return await resp.json()

    # ---- authenticated reads ----

    async def async_session_info(self) -> dict[str, Any]:
        return await self._request("GET", API_AUTH_SESSION)

    async def async_analytics(self) -> dict[str, Any]:
        data = await self._request("GET", API_ANALYTICS)
        if isinstance(data, dict):
            _resolve_image_urls(data, self._host, self._entry_id)
        return data

    async def async_recent_outfits(self, limit: int = 20) -> list[dict[str, Any]]:
        data = await self._request("GET", API_OUTFITS, params={"limit": limit})
        outfits = _coerce_list(data)
        _resolve_image_urls(outfits, self._host, self._entry_id)
        return outfits

    async def async_recent_notifications(self, limit: int = 50) -> list[dict[str, Any]]:
        data = await self._request(
            "GET", API_NOTIFICATIONS_HISTORY, params={"limit": limit}
        )
        return _coerce_list(data)

    async def async_items_needing_wash(self, limit: int = 100) -> list[dict[str, Any]]:
        data = await self._request(
            "GET",
            API_ITEMS,
            params={
                "needs_wash": "true",
                "is_archived": "false",
                "page_size": limit,
            },
        )
        items = _coerce_list(data)
        _resolve_image_urls(items, self._host, self._entry_id)
        return items

    # ---- authenticated writes ----

    async def async_suggest_outfit(self, payload: dict[str, Any]) -> dict[str, Any]:
        result = await self._request("POST", API_OUTFIT_SUGGEST, json=payload)
        if isinstance(result, dict):
            _resolve_image_urls(result, self._host, self._entry_id)
        return result

    async def async_outfit_action(self, outfit_id: str, action: str) -> dict[str, Any]:
        if action not in {"accept", "reject", "skip"}:
            raise ValueError(f"Unsupported outfit action: {action}")
        return await self._request("POST", f"{API_OUTFITS}/{outfit_id}/{action}")

    async def async_post_outfit_feedback(
        self, outfit_id: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        return await self._request(
            "POST", f"{API_OUTFITS}/{outfit_id}/feedback", json=payload
        )

    async def async_log_wear(self, item_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return await self._request("POST", f"{API_ITEMS}/{item_id}/wear", json=payload)

    async def async_log_wash(self, item_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return await self._request("POST", f"{API_ITEMS}/{item_id}/wash", json=payload)

    async def async_archive_item(
        self, item_id: str, reason: str | None
    ) -> dict[str, Any]:
        body = {"reason": reason} if reason else {}
        return await self._request("POST", f"{API_ITEMS}/{item_id}/archive", json=body)

    async def async_restore_item(self, item_id: str) -> dict[str, Any]:
        return await self._request("POST", f"{API_ITEMS}/{item_id}/restore")

    async def async_test_notification(self, setting_id: str) -> dict[str, Any]:
        return await self._request(
            "POST", f"{API_NOTIFICATIONS_SETTINGS}/{setting_id}/test"
        )

    # ---- internals ----

    def _url(self, path: str) -> str:
        return f"{self._host}{path}"

    async def _ensure_jwt(self, *, force: bool = False) -> str:
        async with self._sync_lock:
            now = datetime.now(timezone.utc)
            if (
                not force
                and self._jwt
                and self._jwt_expires_at
                and self._jwt_expires_at - _JWT_REFRESH_LEEWAY > now
            ):
                return self._jwt
            try:
                payload = await self._token_provider.async_get_sync_payload()
            except aiohttp.ClientError as err:
                raise WardrowbeAuthError(f"Failed to refresh auth token: {err}") from err
            try:
                async with self._session.post(
                    self._url(API_AUTH_SYNC),
                    json=payload,
                    ssl=self._verify_ssl,
                    timeout=aiohttp.ClientTimeout(total=DEFAULT_TIMEOUT),
                ) as resp:
                    body_text = await resp.text()
                    if resp.status >= 400:
                        raise WardrowbeAuthError(
                            f"/auth/sync failed: {resp.status} {body_text}"
                        )
                    body = await resp.json(content_type=None)
            except aiohttp.ClientError as err:
                raise WardrowbeApiError(f"/auth/sync transport error: {err}") from err
            jwt = body.get("access_token")
            if not jwt:
                raise WardrowbeAuthError("/auth/sync did not return access_token")
            ttl = int(body.get("expires_in", _DEFAULT_JWT_TTL_SECONDS))
            self._jwt = jwt
            self._jwt_expires_at = now + timedelta(seconds=ttl)
            return jwt

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: Any | None = None,
        params: dict[str, Any] | None = None,
    ) -> Any:
        last_status: int | None = None
        last_body: str | None = None
        for attempt in (0, 1):
            jwt = await self._ensure_jwt(force=attempt == 1)
            try:
                async with self._session.request(
                    method,
                    self._url(path),
                    json=json,
                    params=params,
                    headers={"Authorization": f"Bearer {jwt}"},
                    ssl=self._verify_ssl,
                    timeout=aiohttp.ClientTimeout(total=DEFAULT_TIMEOUT),
                ) as resp:
                    if resp.status == 401 and attempt == 0:
                        continue
                    last_status = resp.status
                    if resp.status >= 400:
                        last_body = await resp.text()
                        break
                    if resp.status == 204:
                        return None
                    return await resp.json(content_type=None)
            except aiohttp.ClientError as err:
                raise WardrowbeApiError(f"{method} {path} failed: {err}") from err
        if last_status == 401:
            raise WardrowbeAuthError(
                f"{method} {path} → 401 after re-sync: {last_body}"
            )
        raise WardrowbeApiError(
            f"{method} {path} → {last_status}: {last_body}", status=last_status
        )


def _coerce_list(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("items", "results", "data", "outfits", "notifications"):
            value = data.get(key)
            if isinstance(value, list):
                return value
    return []


_IMAGE_URL_KEYS: tuple[str, ...] = (
    "image_url",
    "thumbnail_url",
    "image_path",
    "thumbnail_path",
    "preview_url",
    "composite_image_url",
    "composite_url",
    "photo_url",
    "media_url",
)


def _resolve_image_urls(
    payload: Any, host: str, entry_id: str | None = None
) -> None:
    """Recursively rewrite relative Wardrowbe image URLs in-place.

    When ``entry_id`` is provided, paths are rewritten to point at the
    HA-side proxy view (``/api/wardrowbe/image/{entry_id}/...``) so
    browsers always load images from HA's own origin — sidestepping
    mixed-content, CORS, and split-network issues with the Wardrowbe
    host. Without ``entry_id`` we fall back to prepending the Wardrowbe
    host directly.
    """
    if isinstance(payload, list):
        for entry in payload:
            _resolve_image_urls(entry, host, entry_id)
        return
    if not isinstance(payload, dict):
        return
    for key in _IMAGE_URL_KEYS:
        val = payload.get(key)
        if not isinstance(val, str) or not val.startswith("/"):
            continue
        # Idempotent: skip values that have already been routed through
        # the HA proxy, otherwise we'd double-prefix on repeated passes.
        if val.startswith("/api/wardrowbe/image/"):
            continue
        if entry_id:
            payload[key] = f"/api/wardrowbe/image/{entry_id}{val}"
        elif host:
            payload[key] = f"{host}{val}"
    for val in payload.values():
        if isinstance(val, (list, dict)):
            _resolve_image_urls(val, host, entry_id)
