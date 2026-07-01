"""Diagnostics support for Wardrowbe."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from . import WardrowbeConfigEntry

REDACT_KEYS = {
    "client_secret",
    "external_id",
    "token",
    "id_token",
    "access_token",
    "refresh_token",
    "user_id",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: WardrowbeConfigEntry
) -> dict[str, Any]:
    runtime = entry.runtime_data
    coordinator = runtime.coordinator
    data = coordinator.data
    return {
        "entry": async_redact_data(dict(entry.data), REDACT_KEYS),
        "options": dict(entry.options),
        "healthy": getattr(data, "healthy", None),
        "capabilities": getattr(data, "capabilities", None),
        "analytics": getattr(data, "analytics", None),
        "outfits_count": len(getattr(data, "outfits", []) or []),
        "notifications_count": len(getattr(data, "notifications", []) or []),
    }
