"""Config flow tests — focused on the dev-mode happy path.

OIDC paths require a full OAuth dance which is best covered with the upstream
``current_request_with_proxy`` and ``aioclient_mock`` fixtures; left as a TODO
for follow-up coverage.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.wardrowbe.const import (
    API_AUTH_CONFIG,
    AUTH_MODE_DEV,
    AUTH_MODE_OIDC,
    CONF_AUTH_MODE,
    CONF_CLIENT_ID,
    CONF_CLIENT_SECRET,
    CONF_EXTERNAL_ID,
    CONF_HOST,
    CONF_ISSUER_URL,
    CONF_SCOPES,
    CONF_USE_PKCE,
    CONF_VERIFY_SSL,
    DOMAIN,
)


async def test_dev_mode_happy_path(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_HOST: "http://wardrowbe.test",
            CONF_AUTH_MODE: AUTH_MODE_DEV,
            CONF_VERIFY_SSL: False,
        },
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "dev"

    with patch(
        "custom_components.wardrowbe.config_flow.WardrowbeClient", autospec=True
    ) as ClientCls:
        ClientCls.return_value.async_session_info = AsyncMock(
            return_value={"id": "user-123", "name": "Test User"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_EXTERNAL_ID: "user-123"}
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Wardrowbe (Test User)"
    data = result["data"]
    assert data[CONF_HOST] == "http://wardrowbe.test"
    assert data[CONF_AUTH_MODE] == AUTH_MODE_DEV
    assert data[CONF_EXTERNAL_ID] == "user-123"


async def test_dev_mode_reconfigure(
    hass: HomeAssistant, dev_mode_entry: MockConfigEntry
) -> None:
    dev_mode_entry.add_to_hass(hass)
    assert dev_mode_entry.data[CONF_VERIFY_SSL] is False

    result = await dev_mode_entry.start_reconfigure_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_HOST: "http://wardrowbe.test",
            CONF_AUTH_MODE: AUTH_MODE_DEV,
            CONF_VERIFY_SSL: True,
        },
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "dev"

    with patch(
        "custom_components.wardrowbe.config_flow.WardrowbeClient", autospec=True
    ) as ClientCls:
        ClientCls.return_value.async_session_info = AsyncMock(
            return_value={"id": "user-123", "name": "Test User"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_EXTERNAL_ID: "user-123"}
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert dev_mode_entry.data[CONF_VERIFY_SSL] is True


async def test_oidc_pkce_required_without_secret(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A public client (no secret) can't opt out of PKCE."""
    aioclient_mock.get(f"http://wardrowbe.test{API_AUTH_CONFIG}", status=404)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_HOST: "http://wardrowbe.test",
            CONF_AUTH_MODE: AUTH_MODE_OIDC,
            CONF_VERIFY_SSL: True,
        },
    )
    assert result["step_id"] == "oidc"

    with patch(
        "custom_components.wardrowbe.config_flow.discover_oidc_endpoints",
        new=AsyncMock(
            return_value={
                "authorization_endpoint": "http://issuer.test/authorize",
                "token_endpoint": "http://issuer.test/token",
            }
        ),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_ISSUER_URL: "http://issuer.test",
                CONF_CLIENT_ID: "my-client",
                CONF_CLIENT_SECRET: "",
                CONF_USE_PKCE: False,
                CONF_SCOPES: "openid",
            },
        )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "oidc"
    assert result["errors"] == {"base": "pkce_required_without_secret"}


async def test_dev_mode_invalid_host(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_HOST: "not-a-url",
            CONF_AUTH_MODE: AUTH_MODE_DEV,
            CONF_VERIFY_SSL: True,
        },
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_host"}
