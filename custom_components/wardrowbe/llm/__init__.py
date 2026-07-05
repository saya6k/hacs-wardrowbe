"""LLM tools platform for Wardrowbe.

Follows the LLM Tool Platform architecture
(home-assistant/architecture#1412, HA 2026.8+): rather than registering a
separate, user-selectable ``llm.API``, this module contributes tools
directly into the shared Assist API via the ``async_get_tools`` hook that
the core ``llm`` integration discovers and calls automatically. No manual
registration/unregistration per config entry is needed anymore.

Multi-account installs get one full tool set per exposed config entry in a
single call; tool names are suffixed with the entry's slug only when more
than one entry is loaded, so the common single-account case keeps short,
stable names.
"""

from __future__ import annotations

from homeassistant.components.homeassistant import async_should_expose
from homeassistant.components.llm import LLMTools
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.llm import LLM_API_ASSIST, LLMContext, Tool
from homeassistant.util import slugify

from ..const import DOMAIN
from .const import API_PROMPT
from .tools import TOOL_FACTORIES


@callback
def async_get_tools(
    hass: HomeAssistant, llm_context: LLMContext, api_id: str
) -> LLMTools | None:
    """Return Wardrowbe tools for every exposed config entry."""
    if api_id != LLM_API_ASSIST or not llm_context.assistant:
        return None

    entries = [
        entry
        for entry in hass.config_entries.async_entries(DOMAIN)
        if entry.state is ConfigEntryState.LOADED
        and _entry_is_exposed(hass, entry.entry_id, llm_context.assistant)
    ]
    if not entries:
        return None

    suffix_needed = len(entries) > 1
    tools: list[Tool] = []
    for entry in entries:
        suffix = f"_{slugify(entry.title)}" if suffix_needed else ""
        tools.extend(
            factory(hass, entry.entry_id, suffix) for factory in TOOL_FACTORIES
        )
    return LLMTools(tools=tools, prompt=API_PROMPT)


def _entry_is_exposed(hass: HomeAssistant, entry_id: str, assistant: str) -> bool:
    """Whether any entity from this config entry is exposed to the assistant."""
    registry = er.async_get(hass)
    return any(
        async_should_expose(hass, assistant, entity.entity_id)
        for entity in er.async_entries_for_config_entry(registry, entry_id)
    )
