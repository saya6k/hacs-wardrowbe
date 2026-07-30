"""HTTP view that proxies Wardrowbe image URLs through HA.

Wardrowbe returns item/outfit image URLs as presigned **relative paths**
(``/api/v1/images/...?expires=...&sig=...``). Browsers loading the
response from a different origin (HA dashboard hostname, Glance,
voice-satellite card) resolve those paths against the wrong host and
404. This view rebroadcasts the bytes from HA's own HTTP server so any
consumer just hits ``/api/wardrowbe/image/{entry_id}/...`` on HA.

The view does not require HA auth: the Wardrowbe signature on the URL
already gates access, and bouncing the request through here without
revealing Wardrowbe's own hostname is the whole point.
"""

from __future__ import annotations

import logging

from aiohttp import ClientError, web
from homeassistant.components.http import HomeAssistantView
from homeassistant.core import HomeAssistant

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

_ALLOWED_PATH_PREFIX = "/api/v1/images/"


class WardrowbeImageProxyView(HomeAssistantView):
    """Proxy Wardrowbe presigned image URLs through HA's HTTP layer."""

    url = "/api/wardrowbe/image/{entry_id}/{path:.*}"
    name = "api:wardrowbe:image"
    requires_auth = False

    def __init__(self, hass: HomeAssistant) -> None:
        self._hass = hass

    async def get(
        self, request: web.Request, entry_id: str, path: str
    ) -> web.StreamResponse:
        entry = self._hass.config_entries.async_get_entry(entry_id)
        if entry is None or entry.domain != DOMAIN:
            return web.Response(status=404)
        runtime = getattr(entry, "runtime_data", None)
        if runtime is None:
            return web.Response(status=503)

        full_path = f"/{path}"
        if not full_path.startswith(_ALLOWED_PATH_PREFIX):
            return web.Response(status=403)

        client = runtime.client
        target = f"{client.host}{full_path}"
        if request.query_string:
            target = f"{target}?{request.query_string}"

        try:
            async with client._session.get(
                target, ssl=client._verify_ssl
            ) as upstream:
                if upstream.status != 200:
                    return web.Response(status=upstream.status)
                body = await upstream.read()
                content_type = upstream.headers.get(
                    "Content-Type", "application/octet-stream"
                )
                response = web.Response(body=body, content_type=content_type)
                response.headers["Cache-Control"] = "private, max-age=3600"
                return response
        except ClientError as err:
            _LOGGER.warning("Wardrowbe image proxy failed for %s: %s", target, err)
            return web.Response(status=502)
