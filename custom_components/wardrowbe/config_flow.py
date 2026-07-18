"""Config flow for Wardrowbe.

Two paths from the initial user step:

* **OIDC** — user supplies the issuer URL plus client_id/client_secret. We
  fetch ``.well-known/openid-configuration``, register a per-install
  ``WardrowbeOAuth2Implementation``, and delegate to HA's OAuth helper.
  After tokens come back, we exchange the ``id_token`` for a Wardrowbe JWT
  via ``/auth/sync`` and probe ``/auth/session`` to derive the unique_id.
* **Dev mode** — user supplies an ``external_id`` only (matches Wardrowbe's
  development authentication). Same probe, same unique_id derivation.

The unique_id is ``{host}::{user_id}``, so multiple Wardrowbe accounts —
across hosts or within a single host — coexist as separate config entries.
"""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlparse

import aiohttp
import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlowResult
from homeassistant.helpers import config_entry_oauth2_flow
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    BooleanSelector,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import (
    DevTokenProvider,
    StaticIdTokenProvider,
    WardrowbeApiError,
    WardrowbeAuthError,
    WardrowbeClient,
)
from .const import (
    API_AUTH_CONFIG,
    AUTH_MODE_DEV,
    AUTH_MODE_OIDC,
    CONF_AUTH_MODE,
    CONF_AUTHORIZE_URL,
    CONF_CLIENT_ID,
    CONF_CLIENT_SECRET,
    CONF_EXTERNAL_ID,
    CONF_HOST,
    CONF_ISSUER_URL,
    CONF_SCOPES,
    CONF_TOKEN_URL,
    CONF_USE_PKCE,
    CONF_USER_ID,
    CONF_USER_NAME,
    CONF_VERIFY_SSL,
    DEFAULT_OIDC_SCOPES,
    DOMAIN,
)
from .oauth2 import WardrowbeOAuth2Implementation, discover_oidc_endpoints

_LOGGER = logging.getLogger(__name__)


class WardrowbeConfigFlow(
    config_entry_oauth2_flow.AbstractOAuth2FlowHandler, domain=DOMAIN
):
    """Wardrowbe config flow."""

    VERSION = 1
    DOMAIN = DOMAIN

    def __init__(self) -> None:
        super().__init__()
        self._host: str | None = None
        self._verify_ssl: bool = True
        self._auth_mode: str | None = None
        self._issuer_url: str | None = None
        self._client_id: str | None = None
        self._client_secret: str | None = None
        self._use_pkce: bool = True
        self._scopes: str = DEFAULT_OIDC_SCOPES
        self._authorize_url: str | None = None
        self._token_url: str | None = None
        self._external_id: str | None = None
        self._reauth_entry: ConfigEntry | None = None
        self._reconfigure_entry: ConfigEntry | None = None

    @property
    def logger(self) -> logging.Logger:
        return _LOGGER

    @property
    def extra_authorize_data(self) -> dict[str, Any]:
        return {"scope": self._scopes}

    # --- step: user (entry point) ---

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST].rstrip("/")
            parsed = urlparse(host)
            if parsed.scheme not in ("http", "https") or not parsed.netloc:
                errors["base"] = "invalid_host"
            else:
                self._host = host
                self._verify_ssl = user_input.get(CONF_VERIFY_SSL, True)
                self._auth_mode = user_input[CONF_AUTH_MODE]
                if self._auth_mode == AUTH_MODE_DEV:
                    return await self.async_step_dev()
                return await self.async_step_oidc()

        schema = vol.Schema(
            {
                vol.Required(CONF_HOST, default=self._host or ""): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.URL)
                ),
                vol.Required(
                    CONF_AUTH_MODE, default=self._auth_mode or AUTH_MODE_OIDC
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=[
                            SelectOptionDict(value=AUTH_MODE_OIDC, label="OIDC / SSO"),
                            SelectOptionDict(
                                value=AUTH_MODE_DEV, label="Development mode"
                            ),
                        ],
                        translation_key="auth_mode",
                    )
                ),
                vol.Required(CONF_VERIFY_SSL, default=self._verify_ssl): BooleanSelector(),
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    # --- step: dev mode ---

    async def async_step_dev(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        assert self._host is not None
        errors: dict[str, str] = {}
        if user_input is not None:
            external_id = user_input[CONF_EXTERNAL_ID].strip()
            session = async_get_clientsession(self.hass)
            client = WardrowbeClient(
                session,
                self._host,
                DevTokenProvider(external_id),
                verify_ssl=self._verify_ssl,
            )
            try:
                info = await client.async_session_info()
            except WardrowbeAuthError as err:
                _LOGGER.warning("Dev auth failed: %s", err)
                errors["base"] = "auth_failed"
            except WardrowbeApiError as err:
                _LOGGER.warning("Dev probe failed: %s", err)
                errors["base"] = "cannot_connect"
            else:
                user_id = str(info.get("id") or info.get("external_id") or external_id)
                user_name = info.get("name") or info.get("email") or external_id
                return await self._finalise_entry(
                    user_id=user_id,
                    user_name=user_name,
                    extra_data={
                        CONF_AUTH_MODE: AUTH_MODE_DEV,
                        CONF_EXTERNAL_ID: external_id,
                    },
                )

        schema = vol.Schema(
            {vol.Required(CONF_EXTERNAL_ID, default=self._external_id or ""): str}
        )
        return self.async_show_form(step_id="dev", data_schema=schema, errors=errors)

    # --- step: OIDC config + handoff to OAuth helper ---

    async def async_step_oidc(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        assert self._host is not None
        errors: dict[str, str] = {}
        suggested_issuer = self._issuer_url or await self._discover_issuer()

        if user_input is not None:
            issuer = user_input[CONF_ISSUER_URL].rstrip("/")
            try:
                metadata = await discover_oidc_endpoints(self.hass, issuer)
            except aiohttp.ClientError as err:
                _LOGGER.warning("Issuer discovery failed: %s", err)
                errors["base"] = "issuer_discovery_failed"
            else:
                self._issuer_url = issuer
                self._authorize_url = metadata["authorization_endpoint"]
                self._token_url = metadata["token_endpoint"]
                self._client_id = user_input[CONF_CLIENT_ID]
                # Empty client_secret signals a PKCE public client — but only on
                # fresh setup. On reauth/reconfigure, a blank field just means
                # "didn't retype it", so keep whatever was already stored.
                raw_secret = (user_input.get(CONF_CLIENT_SECRET) or "").strip()
                if raw_secret:
                    self._client_secret = raw_secret
                elif self._reauth_entry is None and self._reconfigure_entry is None:
                    self._client_secret = None
                use_pkce = user_input.get(CONF_USE_PKCE, self._use_pkce)
                self._scopes = user_input.get(CONF_SCOPES) or DEFAULT_OIDC_SCOPES

                # A confidential client can still opt into PKCE (OAuth 2.1
                # recommends it for every client type), but a public client
                # (no secret) has no other way to authenticate the code
                # exchange, so it can't opt out.
                if not use_pkce and not self._client_secret:
                    errors["base"] = "pkce_required_without_secret"
                else:
                    self._use_pkce = use_pkce
                    impl = WardrowbeOAuth2Implementation(
                        self.hass,
                        domain=self._impl_id(self._host),
                        client_id=self._client_id,
                        client_secret=self._client_secret,
                        use_pkce=self._use_pkce,
                        authorize_url=self._authorize_url,
                        token_url=self._token_url,
                        issuer_url=issuer,
                        name=f"Wardrowbe @ {urlparse(self._host).netloc}",
                        scopes=self._scopes,
                    )
                    config_entry_oauth2_flow.async_register_implementation(
                        self.hass, DOMAIN, impl
                    )
                    return await self.async_step_pick_implementation(
                        user_input={"implementation": impl.domain}
                    )

        schema = vol.Schema(
            {
                vol.Required(CONF_ISSUER_URL, default=suggested_issuer): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.URL)
                ),
                vol.Required(CONF_CLIENT_ID, default=self._client_id or ""): str,
                # Optional — leave blank for public clients.
                vol.Optional(CONF_CLIENT_SECRET, default=""): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.PASSWORD)
                ),
                vol.Required(CONF_USE_PKCE, default=self._use_pkce): BooleanSelector(),
                vol.Optional(CONF_SCOPES, default=self._scopes): str,
            }
        )
        return self.async_show_form(
            step_id="oidc", data_schema=schema, errors=errors
        )

    async def async_oauth_create_entry(
        self, data: dict[str, Any]
    ) -> ConfigFlowResult:
        """Called by AbstractOAuth2FlowHandler after tokens are obtained."""
        assert self._host is not None
        token = data["token"]
        id_token = token.get("id_token")
        if not id_token:
            return self.async_abort(reason="no_id_token")

        session = async_get_clientsession(self.hass)
        probe_client = WardrowbeClient(
            session,
            self._host,
            StaticIdTokenProvider(id_token),
            verify_ssl=self._verify_ssl,
        )
        try:
            info = await probe_client.async_session_info()
        except WardrowbeAuthError as err:
            _LOGGER.error("/auth/sync rejected id_token: %s", err)
            return self.async_abort(reason="auth_failed")
        except WardrowbeApiError as err:
            _LOGGER.error("Could not probe Wardrowbe session: %s", err)
            return self.async_abort(reason="cannot_connect")

        user_id = str(info.get("id") or info.get("external_id") or "")
        user_name = info.get("name") or info.get("email") or "Wardrowbe user"
        if not user_id:
            return self.async_abort(reason="no_user_id")

        return await self._finalise_entry(
            user_id=user_id,
            user_name=user_name,
            extra_data={
                CONF_AUTH_MODE: AUTH_MODE_OIDC,
                CONF_ISSUER_URL: self._issuer_url,
                CONF_AUTHORIZE_URL: self._authorize_url,
                CONF_TOKEN_URL: self._token_url,
                CONF_CLIENT_ID: self._client_id,
                CONF_CLIENT_SECRET: self._client_secret,
                CONF_USE_PKCE: self._use_pkce,
                CONF_SCOPES: self._scopes,
                "token": token,
                "auth_implementation": data.get("auth_implementation"),
            },
        )

    # --- reauth ---

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        self._reauth_entry = self._get_reauth_entry()
        existing = self._reauth_entry.data
        self._host = existing.get(CONF_HOST)
        self._verify_ssl = existing.get(CONF_VERIFY_SSL, True)
        self._auth_mode = existing.get(CONF_AUTH_MODE)
        self._external_id = existing.get(CONF_EXTERNAL_ID)
        self._issuer_url = existing.get(CONF_ISSUER_URL)
        self._authorize_url = existing.get(CONF_AUTHORIZE_URL)
        self._token_url = existing.get(CONF_TOKEN_URL)
        self._client_id = existing.get(CONF_CLIENT_ID)
        self._client_secret = existing.get(CONF_CLIENT_SECRET)
        self._use_pkce = existing.get(CONF_USE_PKCE, not self._client_secret)
        self._scopes = existing.get(CONF_SCOPES, DEFAULT_OIDC_SCOPES)
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is None:
            return self.async_show_form(step_id="reauth_confirm")
        if self._auth_mode == AUTH_MODE_DEV:
            return await self.async_step_dev()
        # client_secret is intentionally allowed to be missing (public clients).
        if not all(
            (
                self._host,
                self._issuer_url,
                self._authorize_url,
                self._token_url,
                self._client_id,
            )
        ):
            return self.async_abort(reason="missing_oidc_config")
        impl = WardrowbeOAuth2Implementation(
            self.hass,
            domain=self._impl_id(self._host or ""),
            client_id=self._client_id or "",
            client_secret=self._client_secret,  # may be None for public clients
            use_pkce=self._use_pkce,
            authorize_url=self._authorize_url or "",
            token_url=self._token_url or "",
            issuer_url=self._issuer_url or "",
            name=f"Wardrowbe @ {urlparse(self._host or '').netloc}",
            scopes=self._scopes,
        )
        config_entry_oauth2_flow.async_register_implementation(
            self.hass, DOMAIN, impl
        )
        return await self.async_step_pick_implementation(
            user_input={"implementation": impl.domain}
        )

    # --- reconfigure ---

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        self._reconfigure_entry = self._get_reconfigure_entry()
        existing = self._reconfigure_entry.data
        self._host = existing.get(CONF_HOST)
        self._verify_ssl = existing.get(CONF_VERIFY_SSL, True)
        self._auth_mode = existing.get(CONF_AUTH_MODE)
        self._external_id = existing.get(CONF_EXTERNAL_ID)
        self._issuer_url = existing.get(CONF_ISSUER_URL)
        self._authorize_url = existing.get(CONF_AUTHORIZE_URL)
        self._token_url = existing.get(CONF_TOKEN_URL)
        self._client_id = existing.get(CONF_CLIENT_ID)
        self._client_secret = existing.get(CONF_CLIENT_SECRET)
        self._use_pkce = existing.get(CONF_USE_PKCE, not self._client_secret)
        self._scopes = existing.get(CONF_SCOPES, DEFAULT_OIDC_SCOPES)
        # Reuse the initial "user" step so host/auth_mode/verify_ssl (and, via
        # the dev/oidc steps it leads to, everything else) are all editable —
        # not just the token, unlike reauth.
        return await self.async_step_user()

    # --- helpers ---

    async def _discover_issuer(self) -> str:
        """Best-effort fetch of issuer URL from Wardrowbe's /auth/config."""
        if not self._host:
            return ""
        session = async_get_clientsession(self.hass)
        try:
            async with session.get(
                f"{self._host}{API_AUTH_CONFIG}",
                ssl=self._verify_ssl,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status != 200:
                    return ""
                cfg = await resp.json()
        except aiohttp.ClientError:
            return ""
        oidc_block = cfg.get("oidc") if isinstance(cfg.get("oidc"), dict) else {}
        return (
            oidc_block.get("issuer_url")
            or cfg.get("issuer_url")
            or ""
        )

    @staticmethod
    def _impl_id(host: str) -> str:
        digest = hashlib.sha1(host.encode("utf-8"), usedforsecurity=False).hexdigest()[:10]
        return f"{DOMAIN}_{digest}"

    async def _finalise_entry(
        self,
        *,
        user_id: str,
        user_name: str,
        extra_data: dict[str, Any],
    ) -> ConfigFlowResult:
        assert self._host is not None
        unique_id = f"{self._host}::{user_id}"
        await self.async_set_unique_id(unique_id)
        entry_to_update = self._reauth_entry or self._reconfigure_entry
        if entry_to_update is None:
            self._abort_if_unique_id_configured()
        else:
            self._abort_if_unique_id_mismatch(
                reason="reauth_account_mismatch"
                if self._reauth_entry is not None
                else "reconfigure_account_mismatch"
            )
        data: dict[str, Any] = {
            CONF_HOST: self._host,
            CONF_VERIFY_SSL: self._verify_ssl,
            CONF_USER_ID: user_id,
            CONF_USER_NAME: user_name,
            **extra_data,
        }
        if entry_to_update is not None:
            return self.async_update_reload_and_abort(entry_to_update, data=data)
        return self.async_create_entry(title=f"Wardrowbe ({user_name})", data=data)
