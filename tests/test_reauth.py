"""Coordinator auth-failure handling: a periodic refresh failure must start reauth."""

from __future__ import annotations

from unittest.mock import AsyncMock

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.wardrowbe.api import WardrowbeAuthError


async def test_periodic_auth_failure_starts_reauth(
    hass: HomeAssistant,
    dev_mode_entry: MockConfigEntry,
    mock_client: AsyncMock,
) -> None:
    dev_mode_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(dev_mode_entry.entry_id)
    await hass.async_block_till_done()
    assert dev_mode_entry.state is ConfigEntryState.LOADED
    assert not hass.config_entries.flow.async_progress()

    mock_client.async_health.side_effect = WardrowbeAuthError("refresh token invalid")

    coordinator = dev_mode_entry.runtime_data.coordinator
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert coordinator.last_update_success is False
    reauth_flows = [
        flow
        for flow in hass.config_entries.flow.async_progress()
        if flow["context"].get("source") == "reauth"
        and flow["context"].get("entry_id") == dev_mode_entry.entry_id
    ]
    assert len(reauth_flows) == 1
