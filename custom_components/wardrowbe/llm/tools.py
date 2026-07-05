"""Tool registry for the Wardrowbe LLM API."""

from __future__ import annotations

from collections.abc import Callable

from homeassistant.core import HomeAssistant
from homeassistant.helpers import llm

from .outfit_tools import (
    AcceptLatestOutfitTool,
    GetLatestOutfitTool,
    GetRecentOutfitsTool,
    RejectLatestOutfitTool,
    SkipLatestOutfitTool,
    SuggestOutfitTool,
)
from .wardrobe_tools import (
    GetItemsToWashTool,
    GetMostWornItemsTool,
    GetWardrobeSummaryTool,
    LogWashTool,
)

ToolFactory = Callable[[HomeAssistant, str, str], llm.Tool]


def _factory(cls: type) -> ToolFactory:
    def make(hass: HomeAssistant, entry_id: str, name_suffix: str) -> llm.Tool:
        return cls(hass, entry_id, name_suffix)

    return make


TOOL_FACTORIES: list[ToolFactory] = [
    _factory(SuggestOutfitTool),
    _factory(GetLatestOutfitTool),
    _factory(GetRecentOutfitsTool),
    _factory(AcceptLatestOutfitTool),
    _factory(RejectLatestOutfitTool),
    _factory(SkipLatestOutfitTool),
    _factory(GetWardrobeSummaryTool),
    _factory(GetMostWornItemsTool),
    _factory(GetItemsToWashTool),
    _factory(LogWashTool),
]
