"""Base class for Wardrowbe LLM tools."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import llm

from ..const import CONF_HOST
from .const import SOURCE


class BaseWardrowbeTool(llm.Tool):
    """Resolves the bound config entry's runtime_data on demand."""

    service: str = "wardrowbe"

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        super().__init__()
        self.hass = hass
        self.entry_id = entry_id

    @property
    def entry(self) -> ConfigEntry | None:
        return self.hass.config_entries.async_get_entry(self.entry_id)

    @property
    def runtime(self) -> Any:
        entry = self.entry
        return getattr(entry, "runtime_data", None) if entry is not None else None

    @property
    def host(self) -> str:
        entry = self.entry
        if entry is None:
            return ""
        return str(entry.data.get(CONF_HOST, "")).rstrip("/")

    def envelope(self, **fields: Any) -> dict[str, Any]:
        return {"source": SOURCE, "service": self.service, **fields}

    def error(self, message: str) -> dict[str, Any]:
        return {"source": SOURCE, "service": self.service, "error": message}
