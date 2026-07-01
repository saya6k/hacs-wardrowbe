"""Tests for the /capabilities probe and HTTP-status attachment on errors."""

from __future__ import annotations

import aiohttp
import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.wardrowbe.api import (
    DevTokenProvider,
    WardrowbeApiError,
    WardrowbeClient,
)
from custom_components.wardrowbe.const import (
    API_AUTH_SESSION,
    API_AUTH_SYNC,
    API_CAPABILITIES,
)

HOST = "http://wardrowbe.test"


def _client(hass: HomeAssistant) -> WardrowbeClient:
    return WardrowbeClient(
        async_get_clientsession(hass),
        HOST,
        DevTokenProvider("user-123"),
        verify_ssl=False,
    )


async def test_capabilities_returns_dict(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.get(
        f"{HOST}{API_CAPABILITIES}",
        json={
            "ai": {"vision": False, "text": False},
            "features": {"external_suggestions": False},
            "version": "1.0.0",
        },
    )
    caps = await _client(hass).async_capabilities()
    assert caps is not None
    assert caps["ai"]["text"] is False


async def test_capabilities_none_on_404(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Servers predating the endpoint (< 1.4.0) 404 → unknown, not an error."""
    aioclient_mock.get(f"{HOST}{API_CAPABILITIES}", status=404)
    assert await _client(hass).async_capabilities() is None


async def test_capabilities_none_on_transport_error(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.get(f"{HOST}{API_CAPABILITIES}", exc=aiohttp.ClientError())
    assert await _client(hass).async_capabilities() is None


async def test_api_error_carries_http_status(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A non-2xx response surfaces its status on the raised error."""
    aioclient_mock.post(
        f"{HOST}{API_AUTH_SYNC}",
        json={"access_token": "jwt", "expires_in": 100000},
    )
    aioclient_mock.get(f"{HOST}{API_AUTH_SESSION}", status=503)
    with pytest.raises(WardrowbeApiError) as exc:
        await _client(hass).async_session_info()
    assert exc.value.status == 503
