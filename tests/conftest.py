"""Shared pytest fixtures for the Wardrowbe integration."""

from __future__ import annotations

from collections.abc import AsyncGenerator, Generator
from unittest.mock import AsyncMock, patch

import homeassistant.components.http as _ha_http
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.wardrowbe.const import (
    AUTH_MODE_DEV,
    CONF_AUTH_MODE,
    CONF_EXTERNAL_ID,
    CONF_HOST,
    CONF_USER_ID,
    CONF_USER_NAME,
    CONF_VERIFY_SSL,
    DOMAIN,
)

# pytest-homeassistant-custom-component==0.13.346's autouse disable_http_server
# fixture patches homeassistant.components.http.start_http_server_and_save_config
# to stop tests from binding a real HTTP server. HA core removed that name in
# the 2026.8 dev-nightly this repo's devcontainer is pinned to (see AGENTS.md's
# floor note), so the patch() call raises AttributeError before any test body
# runs. No pytest-homeassistant-custom-component release supports the 2026.8
# cycle yet, so restore the attribute as a no-op here; drop this once a
# compatible release ships and tests/requirements_test.txt moves to it.
if not hasattr(_ha_http, "start_http_server_and_save_config"):

    async def _start_http_server_and_save_config(*_args: object, **_kwargs: object) -> None:
        return None

    _ha_http.start_http_server_and_save_config = _start_http_server_and_save_config  # type: ignore[attr-defined]


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Enable loading of the wardrowbe custom integration in tests."""


@pytest.fixture
def mock_session_info() -> dict[str, str]:
    return {"id": "user-123", "external_id": "user-123", "name": "Test User"}


@pytest.fixture
def mock_analytics() -> dict[str, object]:
    return {
        "total_items": 12,
        "items_by_status": {"ready": 10, "processing": 1, "archived": 1},
        "total_outfits": 4,
        "outfits_this_week": 2,
        "outfits_this_month": 4,
        "acceptance_rate": 75.0,
        "average_rating": 4.2,
        "total_wears": 17,
        "color_distribution": [{"color": "navy", "percentage": 30}],
        "most_worn_items": [{"name": "Blue jeans", "wear_count": 5}],
    }


@pytest.fixture
def dev_mode_entry() -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        unique_id="http://wardrowbe.test::user-123",
        title="Wardrowbe (Test User)",
        data={
            CONF_HOST: "http://wardrowbe.test",
            CONF_VERIFY_SSL: False,
            CONF_AUTH_MODE: AUTH_MODE_DEV,
            CONF_EXTERNAL_ID: "user-123",
            CONF_USER_ID: "user-123",
            CONF_USER_NAME: "Test User",
        },
    )


@pytest.fixture
async def mock_client(
    mock_session_info: dict[str, str], mock_analytics: dict[str, object]
) -> AsyncGenerator[AsyncMock, None]:
    """Patch WardrowbeClient with an AsyncMock that returns canned data."""
    with patch(
        "custom_components.wardrowbe.WardrowbeClient", autospec=True
    ) as ClientCls:
        instance = ClientCls.return_value
        instance.async_health = AsyncMock(return_value=True)
        instance.async_session_info = AsyncMock(return_value=mock_session_info)
        instance.async_analytics = AsyncMock(return_value=mock_analytics)
        instance.async_recent_outfits = AsyncMock(return_value=[])
        instance.async_recent_notifications = AsyncMock(return_value=[])
        instance.host = "http://wardrowbe.test"
        yield instance
