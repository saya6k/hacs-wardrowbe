"""Opt-in LLM API registration for Wardrowbe.

One ``llm.API`` is registered per config entry, so multi-account installs
each appear as a discrete, user-selectable tool source in a conversation
agent's LLM API settings — Wardrowbe tools are never contributed to the
shared Assist API automatically.

This module must stay a thin shell and never import the ``llm/`` platform
package (or any tool module) at module level: the setup path imports this
file, and pulling `llm/` in here would defeat its lazy loading (see
`llm/__init__.py`). The one call that needs
`homeassistant.components.llm` — the platform aggregator — is deferred
into `async_get_api_instance`, which only ever runs once a conversation
agent has resolved this API instance, by which point HA's own `llm`
integration is already loaded and the import is a cache hit.
"""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import llm

from .const import DOMAIN, LLM_API_NAME

_LOGGER = logging.getLogger(__name__)


class WardrowbeAPI(llm.API):
    """An ``llm.API`` bound to a single Wardrowbe config entry."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass=hass,
            id=f"{DOMAIN}__{entry.entry_id}",
            name=f"{LLM_API_NAME} — {entry.title}",
        )

    async def async_get_api_instance(
        self, llm_context: llm.LLMContext
    ) -> llm.APIInstance:
        """Return the instance of the API."""
        from homeassistant.components.llm import (  # noqa: PLC0415
            async_get_tools as async_get_platform_tools,
        )

        llm_tools = await async_get_platform_tools(self.hass, llm_context, self.id)
        return llm.APIInstance(
            api=self,
            api_prompt=llm_tools.prompt or "",
            llm_context=llm_context,
            tools=llm_tools.tools,
        )


def async_register_llm_api(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Register this entry's Wardrowbe LLM API; auto-unregisters on unload."""
    api = WardrowbeAPI(hass, entry)
    entry.async_on_unload(llm.async_register_api(hass, api))
    _LOGGER.debug("Registered Wardrowbe LLM API %s", api.id)
