"""Tests for Wardrowbe's opt-in, lazily-loaded LLM API.

The lazy-loading test must run before any other test in this module
imports `custom_components.wardrowbe.llm` (directly or via a submodule),
since Python caches package imports for the life of the process. Every
other test that needs the platform hook or a tool class imports it
locally, inside the test function, to keep that ordering irrelevant in
practice — but the platform-import test itself stays first for clarity.
"""

from __future__ import annotations

import importlib.util
import sys
from unittest.mock import AsyncMock

import pytest
from homeassistant.core import Context, HomeAssistant
from homeassistant.helpers import llm as ha_llm
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.wardrowbe.api import WardrowbeApiError
from custom_components.wardrowbe.const import DOMAIN

_PLATFORM_MODULE = "custom_components.wardrowbe.llm"

# The isolated phacc test stack may pin an older HA release. Only the
# HA 2026.10+ runtime can exercise the ToolResult contract.
requires_llm_integration = pytest.mark.skipif(
    importlib.util.find_spec("homeassistant.components.llm") is None
    or not hasattr(ha_llm, "ToolResult"),
    reason="needs Home Assistant 2026.10 ToolResult",
)


def _api_id(entry_id: str) -> str:
    return f"{DOMAIN}__{entry_id}"


def _llm_context() -> ha_llm.LLMContext:
    return ha_llm.LLMContext(
        platform=DOMAIN,
        context=Context(),
        language="en",
        assistant="conversation",
        device_id=None,
    )


async def test_setup_does_not_import_llm_platform_eagerly(
    hass: HomeAssistant,
    dev_mode_entry: MockConfigEntry,
    mock_client: AsyncMock,
) -> None:
    """Setting up an entry must not import the llm/ tool platform package."""
    was_imported = _PLATFORM_MODULE in sys.modules

    dev_mode_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(dev_mode_entry.entry_id)
    await hass.async_block_till_done()

    assert (_PLATFORM_MODULE in sys.modules) == was_imported


async def test_setup_registers_per_entry_api_unload_unregisters(
    hass: HomeAssistant,
    dev_mode_entry: MockConfigEntry,
    mock_client: AsyncMock,
) -> None:
    dev_mode_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(dev_mode_entry.entry_id)
    await hass.async_block_till_done()

    apis = {api.id: api for api in ha_llm.async_get_apis(hass)}
    api_id = _api_id(dev_mode_entry.entry_id)
    assert api_id in apis
    assert apis[api_id].name == f"Wardrowbe — {dev_mode_entry.title}"

    assert await hass.config_entries.async_unload(dev_mode_entry.entry_id)
    await hass.async_block_till_done()

    apis_after = {api.id for api in ha_llm.async_get_apis(hass)}
    assert api_id not in apis_after


@requires_llm_integration
async def test_hook_opts_out_of_assist_and_unknown_ids(hass: HomeAssistant) -> None:
    from custom_components.wardrowbe.llm import async_get_tools

    llm_context = _llm_context()
    assert async_get_tools(hass, llm_context, "assist") is None
    assert async_get_tools(hass, llm_context, "some_other_domain__xyz") is None
    assert async_get_tools(hass, llm_context, f"{DOMAIN}__unknown-entry") is None


@requires_llm_integration
async def test_hook_returns_tool_set_for_loaded_entry_none_after_unload(
    hass: HomeAssistant,
    dev_mode_entry: MockConfigEntry,
    mock_client: AsyncMock,
) -> None:
    from custom_components.wardrowbe.llm import async_get_tools

    dev_mode_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(dev_mode_entry.entry_id)
    await hass.async_block_till_done()

    llm_context = _llm_context()
    api_id = _api_id(dev_mode_entry.entry_id)
    result = async_get_tools(hass, llm_context, api_id)
    assert result is not None
    assert {tool.name for tool in result.tools} == {
        "suggest_outfit",
        "get_latest_outfit",
        "get_recent_outfits",
        "accept_latest_outfit",
        "reject_latest_outfit",
        "skip_latest_outfit",
        "get_wardrobe_summary",
        "get_most_worn_items",
        "get_items_to_wash",
        "log_wash",
    }

    assert await hass.config_entries.async_unload(dev_mode_entry.entry_id)
    await hass.async_block_till_done()

    assert async_get_tools(hass, llm_context, api_id) is None


@requires_llm_integration
async def test_api_instance_end_to_end(
    hass: HomeAssistant,
    dev_mode_entry: MockConfigEntry,
    mock_client: AsyncMock,
) -> None:
    assert await async_setup_component(hass, "llm", {})

    dev_mode_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(dev_mode_entry.entry_id)
    await hass.async_block_till_done()

    instance = await ha_llm.async_get_api(
        hass, _api_id(dev_mode_entry.entry_id), _llm_context()
    )

    # 10 wardrowbe tools + HA core's own built-in GetDateTimeTool, which
    # async_get_api injects into every API instance.
    assert len(instance.tools) == 11
    assert "wardrobe" in instance.api_prompt.lower()


@requires_llm_integration
async def test_suggest_outfit_tool_happy_path_and_error(
    hass: HomeAssistant,
    dev_mode_entry: MockConfigEntry,
    mock_client: AsyncMock,
) -> None:
    from custom_components.wardrowbe.llm.outfit_tools import (
        SuggestOutfitTool,
    )

    dev_mode_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(dev_mode_entry.entry_id)
    await hass.async_block_till_done()

    tool = SuggestOutfitTool(hass, dev_mode_entry.entry_id)
    llm_context = _llm_context()

    mock_client.async_suggest_outfit = AsyncMock(
        return_value={"id": "outfit-1", "occasion": "work"}
    )
    result = await tool.async_call(
        hass, ha_llm.ToolInput(tool_name=tool.name, tool_args={}), llm_context
    )
    assert isinstance(result, ha_llm.ToolResult)
    assert not result.error
    assert result.data["source"] == "wardrowbe"
    assert "error" not in result.data
    assert result.data["outfit"]["id"] == "outfit-1"

    mock_client.async_suggest_outfit = AsyncMock(side_effect=WardrowbeApiError("boom"))
    error_result = await tool.async_call(
        hass, ha_llm.ToolInput(tool_name=tool.name, tool_args={}), llm_context
    )
    assert error_result.error
    assert "boom" in error_result.data["error"]


@requires_llm_integration
async def test_tool_metadata_distinguishes_reads_and_writes(hass: HomeAssistant) -> None:
    from custom_components.wardrowbe.llm.tools import TOOL_FACTORIES

    for factory in TOOL_FACTORIES:
        tool = factory(hass, "test-entry")
        assert tool.integration == DOMAIN
        assert tool.title
        assert tool.annotations.read_only == tool.name.startswith("get_")
        assert tool.annotations.open_world == (not tool.name.startswith("get_"))
        if not tool.name.startswith("get_"):
            assert not tool.annotations.idempotent


@requires_llm_integration
async def test_no_outfit_is_successful_empty_result(hass: HomeAssistant) -> None:
    from types import SimpleNamespace
    from unittest.mock import PropertyMock, patch

    from custom_components.wardrowbe.llm.outfit_tools import GetLatestOutfitTool

    tool = GetLatestOutfitTool(hass, "test-entry")
    runtime = SimpleNamespace(coordinator=SimpleNamespace(data=SimpleNamespace(outfits=[])))
    with patch.object(GetLatestOutfitTool, "runtime", new_callable=PropertyMock) as prop:
        prop.return_value = runtime
        result = await tool.async_call(
            hass, ha_llm.ToolInput(tool_name=tool.name, tool_args={}), _llm_context()
        )
    assert not result.error
    assert result.data["outfit"] is None
    assert result.data["results"] == []
