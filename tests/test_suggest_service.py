"""Tests for the suggest_outfit AI-capability gating and 503 handling.

`suggest_outfit` is registered wrapped in ``_guard``, which catches
``ServiceValidationError`` (returning None) but lets ``HomeAssistantError``
propagate. That asymmetry is the lever these tests use:

* fail-fast / 503-deferred → ServiceValidationError → call returns None
* any other API error → HomeAssistantError → call raises
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.wardrowbe.api import WardrowbeApiError
from custom_components.wardrowbe.const import (
    ATTR_CONFIG_ENTRY_ID,
    DOMAIN,
    SERVICE_SUGGEST_OUTFIT,
)
from custom_components.wardrowbe.services import _text_ai_disabled


@pytest.mark.parametrize(
    ("capabilities", "expected"),
    [
        ({"ai": {"text": False}}, True),  # explicitly off → disabled
        ({"ai": {"text": True}}, False),  # explicitly on
        ({"ai": {"vision": False}}, False),  # text unknown → assume enabled
        ({"ai": {}}, False),
        ({}, False),
        (None, False),  # not polled / server < 1.4.0 → assume enabled
        ("garbage", False),  # malformed → assume enabled
    ],
)
def test_text_ai_disabled(capabilities: object, expected: bool) -> None:
    coordinator = SimpleNamespace(data=SimpleNamespace(capabilities=capabilities))
    assert _text_ai_disabled(coordinator) is expected


async def _setup(
    hass: HomeAssistant, entry: MockConfigEntry
) -> None:
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def _call(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    """Fire the service without requesting a response.

    ``return_response=True`` makes HA core raise when the handler yields
    None — which is exactly what ``_guard`` does after swallowing a
    ServiceValidationError — so the deferred/fail-fast paths must be
    exercised without it.
    """
    await hass.services.async_call(
        DOMAIN,
        SERVICE_SUGGEST_OUTFIT,
        {ATTR_CONFIG_ENTRY_ID: entry.entry_id},
        blocking=True,
    )


async def _call_with_response(hass: HomeAssistant, entry: MockConfigEntry) -> object:
    return await hass.services.async_call(
        DOMAIN,
        SERVICE_SUGGEST_OUTFIT,
        {ATTR_CONFIG_ENTRY_ID: entry.entry_id},
        blocking=True,
        return_response=True,
    )


async def test_suggest_fails_fast_when_text_ai_disabled(
    hass: HomeAssistant,
    dev_mode_entry: MockConfigEntry,
    mock_client: AsyncMock,
) -> None:
    """With text AI reported off, the doomed POST is never attempted."""
    mock_client.async_capabilities = AsyncMock(return_value={"ai": {"text": False}})
    mock_client.async_suggest_outfit = AsyncMock(return_value={"id": "o1"})
    await _setup(hass, dev_mode_entry)

    await _call(hass, dev_mode_entry)

    mock_client.async_suggest_outfit.assert_not_called()


async def test_suggest_503_is_deferred_not_error(
    hass: HomeAssistant,
    dev_mode_entry: MockConfigEntry,
    mock_client: AsyncMock,
) -> None:
    """A server-side 503 (AI off) maps to ServiceValidationError → swallowed."""
    mock_client.async_capabilities = AsyncMock(return_value={"ai": {"text": True}})
    mock_client.async_suggest_outfit = AsyncMock(
        side_effect=WardrowbeApiError("deferred", status=503)
    )
    await _setup(hass, dev_mode_entry)

    # Guard swallows the mapped ServiceValidationError → no exception raised.
    await _call(hass, dev_mode_entry)

    mock_client.async_suggest_outfit.assert_called_once()


async def test_suggest_non_503_error_propagates(
    hass: HomeAssistant,
    dev_mode_entry: MockConfigEntry,
    mock_client: AsyncMock,
) -> None:
    """A generic API failure stays a HomeAssistantError (not swallowed)."""
    mock_client.async_capabilities = AsyncMock(return_value={"ai": {"text": True}})
    mock_client.async_suggest_outfit = AsyncMock(
        side_effect=WardrowbeApiError("boom", status=500)
    )
    await _setup(hass, dev_mode_entry)

    with pytest.raises(HomeAssistantError):
        await _call(hass, dev_mode_entry)


async def test_suggest_happy_path_returns_result(
    hass: HomeAssistant,
    dev_mode_entry: MockConfigEntry,
    mock_client: AsyncMock,
) -> None:
    mock_client.async_capabilities = AsyncMock(return_value={"ai": {"text": True}})
    mock_client.async_suggest_outfit = AsyncMock(return_value={"id": "o1"})
    await _setup(hass, dev_mode_entry)

    result = await _call_with_response(hass, dev_mode_entry)

    assert result == {"id": "o1"}
    mock_client.async_suggest_outfit.assert_called_once()
