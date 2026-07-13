"""LLM tools platform for Wardrowbe.

Discovered lazily by Home Assistant's `llm` integration (HA 2026.8+) the
first time any LLM API collects tools
(home-assistant/architecture#1412). This module answers only for
Wardrowbe's own per-entry API ids — never `assist` or any other
integration's API — so Wardrowbe tools only ever surface through the
user-selected "Wardrowbe — <account>" API (see `..llm_api`), not the
shared Assist API.
"""

from __future__ import annotations

from homeassistant.components.llm import LLMTools
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.llm import LLMContext

from ..const import DOMAIN
from .const import API_PROMPT
from .tools import TOOL_FACTORIES

_API_ID_PREFIX = f"{DOMAIN}__"


@callback
def async_get_tools(
    hass: HomeAssistant, llm_context: LLMContext, api_id: str
) -> LLMTools | None:
    """Return this entry's Wardrowbe tools, or None for any other API id."""
    if not api_id.startswith(_API_ID_PREFIX):
        return None

    entry_id = api_id[len(_API_ID_PREFIX) :]
    entry = hass.config_entries.async_get_entry(entry_id)
    if entry is None or entry.state is not ConfigEntryState.LOADED:
        # Unknown id, or the entry was unloaded since the API was requested.
        return None

    tools = [factory(hass, entry_id) for factory in TOOL_FACTORIES]
    return LLMTools(tools=tools, prompt=API_PROMPT)
