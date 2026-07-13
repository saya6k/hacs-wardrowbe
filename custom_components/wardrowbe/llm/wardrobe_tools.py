"""Wardrobe-stat / item LLM tools for Wardrowbe."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.core import HomeAssistant
from homeassistant.helpers import llm

from ..api import WardrowbeApiError
from ..const import EVENT_GROUP_WASH
from .base_tool import BaseWardrowbeTool
from .render import extract_image_url, svg_summary


class GetWardrobeSummaryTool(BaseWardrowbeTool):
    name = "get_wardrobe_summary"
    description = (
        "Return overall wardrobe statistics: item counts by status "
        "(ready, processing, archived), total and recent outfit counts, "
        "outfit acceptance rate, average outfit rating, and total wears. "
        "Call this when the user asks general questions about their "
        "wardrobe or outfit habits rather than about one specific outfit "
        "or item."
    )
    parameters = vol.Schema({})

    async def async_call(
        self,
        hass: HomeAssistant,
        tool_input: llm.ToolInput,
        llm_context: llm.LLMContext,
    ) -> dict[str, Any]:
        runtime = self.runtime
        if runtime is None or runtime.coordinator.data is None:
            return self.error("Wardrowbe data is not ready.")
        analytics = runtime.coordinator.data.analytics or {}
        wardrobe = analytics.get("wardrobe") or {}
        items_by_status = wardrobe.get("items_by_status") or {}

        def _num(value: Any) -> str:
            if value is None:
                return "—"
            if isinstance(value, float):
                return f"{value:.1f}"
            return str(value)

        lines: list[tuple[str, str]] = [
            ("Total items", _num(wardrobe.get("total_items"))),
            ("Ready", _num(items_by_status.get("ready"))),
            ("Processing", _num(items_by_status.get("processing"))),
            ("Archived", _num(items_by_status.get("archived"))),
            ("Total outfits", _num(wardrobe.get("total_outfits"))),
            ("This week", _num(wardrobe.get("outfits_this_week"))),
            ("This month", _num(wardrobe.get("outfits_this_month"))),
            ("Acceptance %", _num(wardrobe.get("acceptance_rate"))),
            ("Avg rating", _num(wardrobe.get("average_rating"))),
            ("Total wears", _num(wardrobe.get("total_wears"))),
        ]
        entry = self.entry
        subtitle = entry.title if entry is not None else None
        card = svg_summary("Wardrobe summary", lines, subtitle=subtitle)
        return self.envelope(
            wardrobe=wardrobe,
            featured_image=card,
            results=[],
            auto_display=True,
            instruction=(
                "A summary card is shown. Mention 1-2 stats the user "
                "would most likely care about; keep it short."
            ),
        )


class GetMostWornItemsTool(BaseWardrowbeTool):
    name = "get_most_worn_items"
    description = (
        "List the user's most-worn wardrobe items as an image gallery, "
        "ranked by wear count. Call this when the user asks what they "
        "wear most often or which pieces get the most use. Optional "
        "limit (1-10, default 5) caps how many items are returned."
    )
    parameters = vol.Schema(
        {vol.Optional("limit"): vol.All(int, vol.Range(min=1, max=10))}
    )

    async def async_call(
        self,
        hass: HomeAssistant,
        tool_input: llm.ToolInput,
        llm_context: llm.LLMContext,
    ) -> dict[str, Any]:
        runtime = self.runtime
        if runtime is None or runtime.coordinator.data is None:
            return self.error("Wardrowbe data is not ready.")
        limit = tool_input.tool_args.get("limit") or 5
        analytics = runtime.coordinator.data.analytics or {}
        most_worn = analytics.get("most_worn") or []
        if not isinstance(most_worn, list):
            most_worn = []

        results: list[dict[str, Any]] = []
        for item in most_worn[:limit]:
            if not isinstance(item, dict):
                continue
            img = extract_image_url(item, self.host)
            if not img:
                continue
            title = item.get("name") or item.get("category") or "Item"
            wears = item.get("wear_count") or item.get("wears")
            full_title = f"{title} · {wears}" if wears is not None else str(title)
            results.append(
                {
                    "image_url": img,
                    "thumbnail_url": img,
                    "title": full_title,
                }
            )

        return self.envelope(
            count=len(results),
            most_worn=most_worn[:limit],
            results=results,
            auto_display=True,
            instruction=(
                "Top items are shown as a gallery. Mention the top 1-2 "
                "by name; keep it brief."
            ),
        )


class GetItemsToWashTool(BaseWardrowbeTool):
    name = "get_items_to_wash"
    description = (
        "List wardrobe items the server has flagged as needing a wash "
        "(needs_wash=true), as an image gallery with item ids. Call this "
        "when the user asks what needs washing or laundry. Optional "
        "limit (1-20, default 8). Use the returned item_id with log_wash "
        "once the user says they've washed something."
    )
    parameters = vol.Schema(
        {vol.Optional("limit"): vol.All(int, vol.Range(min=1, max=20))}
    )

    async def async_call(
        self,
        hass: HomeAssistant,
        tool_input: llm.ToolInput,
        llm_context: llm.LLMContext,
    ) -> dict[str, Any]:
        runtime = self.runtime
        if runtime is None or runtime.coordinator.data is None:
            return self.error("Wardrowbe data is not ready.")
        limit = tool_input.tool_args.get("limit") or 8
        items = runtime.coordinator.data.items_to_wash[:limit]

        results: list[dict[str, Any]] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            img = extract_image_url(item, self.host)
            title = item.get("name") or item.get("type") or "Item"
            wears = item.get("wears_since_wash")
            full_title = f"{title} · {wears} wears" if wears is not None else str(title)
            entry: dict[str, Any] = {"title": full_title}
            if img:
                entry["image_url"] = img
                entry["thumbnail_url"] = img
            entry["item_id"] = str(item.get("id")) if item.get("id") is not None else None
            results.append(entry)

        return self.envelope(
            count=len(items),
            items=items,
            results=results,
            auto_display=True,
            instruction=(
                "Items needing wash are shown. Tell the user how many and "
                "name the top 1-2; offer to mark one washed if they ask."
            ),
        )


class LogWashTool(BaseWardrowbeTool):
    name = "log_wash"
    description = (
        "Mark a wardrobe item as washed and reset its wear-since-wash "
        "counter. Call this when the user says they washed, cleaned, or "
        "laundered an item. Pass item_id (preferred, e.g. from "
        "get_items_to_wash) or item_name to match by name against the "
        "current items-to-wash list. Fails if neither is given or no "
        "match is found."
    )
    parameters = vol.Schema(
        {
            vol.Optional("item_id"): str,
            vol.Optional("item_name"): str,
        }
    )

    async def async_call(
        self,
        hass: HomeAssistant,
        tool_input: llm.ToolInput,
        llm_context: llm.LLMContext,
    ) -> dict[str, Any]:
        runtime = self.runtime
        if runtime is None or runtime.coordinator.data is None:
            return self.error("Wardrowbe data is not ready.")
        args = tool_input.tool_args
        item_id = args.get("item_id")
        if not item_id:
            name = (args.get("item_name") or "").strip().lower()
            if not name:
                return self.error("Provide item_id or item_name.")
            for candidate in runtime.coordinator.data.items_to_wash:
                cand_name = str(candidate.get("name") or "").strip().lower()
                if cand_name and (cand_name == name or name in cand_name):
                    item_id = str(candidate.get("id")) if candidate.get("id") is not None else None
                    break
            if not item_id:
                return self.error(
                    f"No item matching '{args.get('item_name')}' in the wash list."
                )

        try:
            result = await runtime.client.async_log_wash(str(item_id), {})
        except WardrowbeApiError as err:
            return self.error(f"log_wash failed: {err}")
        payload: dict[str, Any] = {"item_id": str(item_id)}
        if isinstance(result, dict):
            for key in ("name", "wears_since_wash", "last_washed_at"):
                if key in result:
                    payload[key] = result[key]
        runtime.coordinator.record_local_event(EVENT_GROUP_WASH, "logged", payload)
        await runtime.coordinator.async_request_refresh()
        return self.envelope(
            item_id=str(item_id),
            instruction=(
                "The item was logged as washed. Confirm in one short "
                "sentence."
            ),
        )
