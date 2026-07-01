"""Service handlers for Wardrowbe.

Every service takes a ``config_entry_id`` so multi-account installs can pick
which Wardrowbe account to act against. Services that produce useful output
(``suggest_outfit``, ``submit_feedback``) return a response dict so callers
can use ``response_variable`` in scripts/automations.
"""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
)
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv

from .api import WardrowbeApiError, WardrowbeClient
from .coordinator import WardrowbeCoordinator
from .const import (
    ACTIONABLE_OUTFIT_STATUSES,
    ATTR_CONFIG_ENTRY_ID,
    ATTR_DATE,
    ATTR_EXCLUDE_STATUSES,
    ATTR_INCLUDE_STATUSES,
    ATTR_ITEM_ID,
    ATTR_NOTES,
    ATTR_OCCASION,
    ATTR_OUTFIT_ID,
    ATTR_RATING,
    ATTR_REASON,
    ATTR_SETTING_ID,
    ATTR_TARGET_DATE,
    ATTR_TIME_OF_DAY,
    ATTR_WORE,
    DOMAIN,
    EVENT_GROUP_OUTFIT,
    EVENT_GROUP_WASH,
    EVENT_GROUP_WEAR,
    SERVICE_ACCEPT_OUTFIT,
    SERVICE_ARCHIVE_ITEM,
    SERVICE_LOG_WASH,
    SERVICE_LOG_WEAR,
    SERVICE_REJECT_OUTFIT,
    SERVICE_RESTORE_ITEM,
    SERVICE_SKIP_OUTFIT,
    SERVICE_GET_SUMMARY,
    SERVICE_SUBMIT_FEEDBACK,
    SERVICE_SUGGEST_OUTFIT,
    SERVICE_TEST_NOTIFICATION,
    VALID_OCCASIONS,
    VALID_OUTFIT_STATUSES,
    VALID_TIME_OF_DAY,
)

_LOGGER = logging.getLogger(__name__)

_BASE_SCHEMA = vol.Schema({vol.Required(ATTR_CONFIG_ENTRY_ID): cv.string}, extra=vol.ALLOW_EXTRA)

SCHEMA_SUGGEST = _BASE_SCHEMA.extend(
    {
        vol.Optional(ATTR_OCCASION): vol.In(VALID_OCCASIONS),
        vol.Optional(ATTR_TIME_OF_DAY): vol.In(VALID_TIME_OF_DAY),
        vol.Optional(ATTR_TARGET_DATE): cv.date,
        vol.Optional(ATTR_NOTES): cv.string,
    }
)

SCHEMA_OUTFIT_ACTION = _BASE_SCHEMA.extend(
    {vol.Optional(ATTR_OUTFIT_ID): cv.string}
)

SCHEMA_FEEDBACK = _BASE_SCHEMA.extend(
    {
        vol.Required(ATTR_OUTFIT_ID): cv.string,
        vol.Optional(ATTR_RATING): vol.All(int, vol.Range(min=1, max=5)),
        vol.Optional(ATTR_WORE): cv.boolean,
        vol.Optional(ATTR_NOTES): cv.string,
    }
)

SCHEMA_LOG_WEAR = _BASE_SCHEMA.extend(
    {vol.Required(ATTR_ITEM_ID): cv.string, vol.Optional(ATTR_DATE): cv.date}
)

SCHEMA_LOG_WASH = _BASE_SCHEMA.extend({vol.Required(ATTR_ITEM_ID): cv.string})

SCHEMA_ARCHIVE = _BASE_SCHEMA.extend(
    {vol.Required(ATTR_ITEM_ID): cv.string, vol.Optional(ATTR_REASON): cv.string}
)

SCHEMA_RESTORE = _BASE_SCHEMA.extend({vol.Required(ATTR_ITEM_ID): cv.string})

SCHEMA_TEST_NOTIFICATION = _BASE_SCHEMA.extend(
    {vol.Required(ATTR_SETTING_ID): cv.string}
)

# ``get_summary`` accepts optional include/exclude lists so dashboards can ask
# for "non-rejected outfits only" without doing the filtering in Glance's Go
# template (which is fiddly when the most-recent outfit is the one to skip).
_status_filter = vol.All(cv.ensure_list, [vol.In(VALID_OUTFIT_STATUSES)])
SCHEMA_GET_SUMMARY = _BASE_SCHEMA.extend(
    {
        vol.Optional(ATTR_EXCLUDE_STATUSES): _status_filter,
        vol.Optional(ATTR_INCLUDE_STATUSES): _status_filter,
    }
)


async def async_register_services(hass: HomeAssistant) -> None:
    """Register Wardrowbe services exactly once across the integration."""
    if hass.services.has_service(DOMAIN, SERVICE_SUGGEST_OUTFIT):
        return

    hass.services.async_register(
        DOMAIN,
        SERVICE_SUGGEST_OUTFIT,
        _guard(_make_suggest_handler(hass)),
        schema=SCHEMA_SUGGEST,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_ACCEPT_OUTFIT,
        _guard(_make_outfit_action_handler(hass, "accept")),
        schema=SCHEMA_OUTFIT_ACTION,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_REJECT_OUTFIT,
        _guard(_make_outfit_action_handler(hass, "reject")),
        schema=SCHEMA_OUTFIT_ACTION,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SKIP_OUTFIT,
        _guard(_make_outfit_action_handler(hass, "skip")),
        schema=SCHEMA_OUTFIT_ACTION,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SUBMIT_FEEDBACK,
        _guard(_make_feedback_handler(hass)),
        schema=SCHEMA_FEEDBACK,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_LOG_WEAR, _guard(_make_log_wear_handler(hass)), schema=SCHEMA_LOG_WEAR
    )
    hass.services.async_register(
        DOMAIN, SERVICE_LOG_WASH, _guard(_make_log_wash_handler(hass)), schema=SCHEMA_LOG_WASH
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_ARCHIVE_ITEM,
        _guard(_make_archive_handler(hass)),
        schema=SCHEMA_ARCHIVE,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_RESTORE_ITEM,
        _guard(_make_restore_handler(hass)),
        schema=SCHEMA_RESTORE,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_TEST_NOTIFICATION,
        _guard(_make_test_notification_handler(hass)),
        schema=SCHEMA_TEST_NOTIFICATION,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_GET_SUMMARY,
        _guard(_make_get_summary_handler(hass)),
        schema=SCHEMA_GET_SUMMARY,
        supports_response=SupportsResponse.ONLY,
    )


async def async_unregister_services(hass: HomeAssistant) -> None:
    for service in (
        SERVICE_SUGGEST_OUTFIT,
        SERVICE_ACCEPT_OUTFIT,
        SERVICE_REJECT_OUTFIT,
        SERVICE_SKIP_OUTFIT,
        SERVICE_SUBMIT_FEEDBACK,
        SERVICE_LOG_WEAR,
        SERVICE_LOG_WASH,
        SERVICE_ARCHIVE_ITEM,
        SERVICE_RESTORE_ITEM,
        SERVICE_TEST_NOTIFICATION,
        SERVICE_GET_SUMMARY,
    ):
        if hass.services.has_service(DOMAIN, service):
            hass.services.async_remove(DOMAIN, service)


def _resolve_runtime(
    hass: HomeAssistant, call: ServiceCall
) -> tuple[WardrowbeClient, WardrowbeCoordinator]:
    entry_id = call.data[ATTR_CONFIG_ENTRY_ID]
    entry: ConfigEntry | None = hass.config_entries.async_get_entry(entry_id)
    if entry is None or entry.domain != DOMAIN:
        raise ServiceValidationError(f"Unknown Wardrowbe config entry: {entry_id}")
    runtime = getattr(entry, "runtime_data", None)
    if runtime is None:
        raise HomeAssistantError(
            f"Wardrowbe entry {entry_id} is not loaded; cannot run service."
        )
    return runtime.client, runtime.coordinator


def _guard(handler):
    """Wrap a service handler to prevent ServiceValidationError from reaching aiohttp.

    When a config entry is removed while automations/scripts still reference it,
    ``_resolve_runtime`` raises ``ServiceValidationError``.  Without this guard
    that error reaches aiohttp's top-level handler and is logged at ERROR level
    on every service call — potentially hundreds of times.  Catching it here
    keeps it at WARNING and returns ``None`` so HA can respond gracefully.
    """

    async def _wrapped(call: ServiceCall):
        try:
            return await handler(call)
        except ServiceValidationError as err:
            _LOGGER.warning("Service call skipped: %s", err)
            return None

    return _wrapped


def _resolve_client(hass: HomeAssistant, call: ServiceCall) -> WardrowbeClient:
    return _resolve_runtime(hass, call)[0]


def _resolve_latest_pending_outfit(hass: HomeAssistant, call: ServiceCall) -> str:
    entry_id = call.data[ATTR_CONFIG_ENTRY_ID]
    entry = hass.config_entries.async_get_entry(entry_id)
    if entry is None:
        raise ServiceValidationError(f"Unknown Wardrowbe config entry: {entry_id}")
    runtime = getattr(entry, "runtime_data", None)
    if runtime is None or runtime.coordinator.data is None:
        raise HomeAssistantError("Wardrowbe coordinator has no data yet.")
    for outfit in runtime.coordinator.data.outfits:
        if outfit.get("status") in ACTIONABLE_OUTFIT_STATUSES and "id" in outfit:
            return str(outfit["id"])
    raise HomeAssistantError(
        "No actionable outfit available; pass outfit_id explicitly."
    )


_AI_DISABLED_MSG = (
    "Wardrowbe internal AI is disabled on this server; outfit suggestions are "
    "deferred to an external agent."
)


def _text_ai_disabled(coordinator: WardrowbeCoordinator) -> bool:
    """Return True only when the server explicitly reports text AI as off.

    An unknown state (no capabilities polled yet, or a server predating the
    endpoint) is treated as enabled so we never block a call that would work.
    """
    caps = getattr(coordinator.data, "capabilities", None)
    if not isinstance(caps, dict):
        return False
    ai = caps.get("ai")
    return isinstance(ai, dict) and ai.get("text") is False


def _make_suggest_handler(hass: HomeAssistant):
    async def _handle(call: ServiceCall) -> ServiceResponse:
        client, coordinator = _resolve_runtime(hass, call)
        if _text_ai_disabled(coordinator):
            raise ServiceValidationError(_AI_DISABLED_MSG)
        payload: dict[str, Any] = {}
        if (occasion := call.data.get(ATTR_OCCASION)) is not None:
            payload["occasion"] = occasion
        if (time_of_day := call.data.get(ATTR_TIME_OF_DAY)) is not None:
            payload["time_of_day"] = time_of_day
        if (target := call.data.get(ATTR_TARGET_DATE)) is not None:
            payload["target_date"] = target.isoformat()
        if (notes := call.data.get(ATTR_NOTES)) is not None:
            payload["notes"] = notes
        try:
            result = await client.async_suggest_outfit(payload)
        except WardrowbeApiError as err:
            if err.status == 503:
                raise ServiceValidationError(_AI_DISABLED_MSG) from err
            raise HomeAssistantError(f"suggest_outfit failed: {err}") from err
        await coordinator.async_request_refresh()
        return result

    return _handle


def _make_outfit_action_handler(hass: HomeAssistant, action: str):
    async def _handle(call: ServiceCall) -> None:
        client, coordinator = _resolve_runtime(hass, call)
        outfit_id = call.data.get(ATTR_OUTFIT_ID) or _resolve_latest_pending_outfit(
            hass, call
        )
        try:
            await client.async_outfit_action(outfit_id, action)
        except WardrowbeApiError as err:
            raise HomeAssistantError(f"{action}_outfit failed: {err}") from err
        await coordinator.async_request_refresh()

    return _handle


def _make_feedback_handler(hass: HomeAssistant):
    async def _handle(call: ServiceCall) -> ServiceResponse:
        client, coordinator = _resolve_runtime(hass, call)
        outfit_id = call.data[ATTR_OUTFIT_ID]
        payload = {
            k: v
            for k, v in {
                "rating": call.data.get(ATTR_RATING),
                "wore": call.data.get(ATTR_WORE),
                "notes": call.data.get(ATTR_NOTES),
            }.items()
            if v is not None
        }
        try:
            result = await client.async_post_outfit_feedback(outfit_id, payload)
        except WardrowbeApiError as err:
            raise HomeAssistantError(f"submit_feedback failed: {err}") from err
        event_payload: dict[str, Any] = {"outfit_id": outfit_id, **payload}
        if isinstance(result, dict):
            event_payload.setdefault("status", result.get("status"))
        coordinator.record_local_event(
            EVENT_GROUP_OUTFIT, "feedback_submitted", event_payload
        )
        await coordinator.async_request_refresh()
        return result

    return _handle


def _make_log_wear_handler(hass: HomeAssistant):
    async def _handle(call: ServiceCall) -> None:
        client, coordinator = _resolve_runtime(hass, call)
        payload: dict[str, Any] = {}
        if (date := call.data.get(ATTR_DATE)) is not None:
            payload["date"] = date.isoformat()
        item_id = call.data[ATTR_ITEM_ID]
        try:
            result = await client.async_log_wear(item_id, payload)
        except WardrowbeApiError as err:
            raise HomeAssistantError(f"log_wear failed: {err}") from err
        coordinator.record_local_event(
            EVENT_GROUP_WEAR, "logged", _wash_wear_event_payload(item_id, result)
        )
        await coordinator.async_request_refresh()

    return _handle


def _make_log_wash_handler(hass: HomeAssistant):
    async def _handle(call: ServiceCall) -> None:
        client, coordinator = _resolve_runtime(hass, call)
        item_id = call.data[ATTR_ITEM_ID]
        try:
            result = await client.async_log_wash(item_id, {})
        except WardrowbeApiError as err:
            raise HomeAssistantError(f"log_wash failed: {err}") from err
        coordinator.record_local_event(
            EVENT_GROUP_WASH, "logged", _wash_wear_event_payload(item_id, result)
        )
        await coordinator.async_request_refresh()

    return _handle


def _wash_wear_event_payload(item_id: str, result: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {"item_id": item_id}
    if isinstance(result, dict):
        for key in (
            "name",
            "wears_since_wash",
            "last_washed_at",
            "last_worn_at",
            "wear_count",
        ):
            if key in result:
                payload[key] = result[key]
    return payload


def _make_archive_handler(hass: HomeAssistant):
    async def _handle(call: ServiceCall) -> None:
        client, coordinator = _resolve_runtime(hass, call)
        try:
            await client.async_archive_item(
                call.data[ATTR_ITEM_ID], call.data.get(ATTR_REASON)
            )
        except WardrowbeApiError as err:
            raise HomeAssistantError(f"archive_item failed: {err}") from err
        await coordinator.async_request_refresh()

    return _handle


def _make_restore_handler(hass: HomeAssistant):
    async def _handle(call: ServiceCall) -> None:
        client, coordinator = _resolve_runtime(hass, call)
        try:
            await client.async_restore_item(call.data[ATTR_ITEM_ID])
        except WardrowbeApiError as err:
            raise HomeAssistantError(f"restore_item failed: {err}") from err
        await coordinator.async_request_refresh()

    return _handle


def _make_get_summary_handler(hass: HomeAssistant):
    async def _handle(call: ServiceCall) -> ServiceResponse:
        _, coordinator = _resolve_runtime(hass, call)
        data = coordinator.data
        if data is None:
            return {
                "healthy": False,
                "analytics": {},
                "outfits": [],
                "notifications": [],
                "items_to_wash": [],
            }
        outfits = _filter_outfits(
            data.outfits,
            include=call.data.get(ATTR_INCLUDE_STATUSES),
            exclude=call.data.get(ATTR_EXCLUDE_STATUSES),
        )
        return {
            "healthy": data.healthy,
            "analytics": data.analytics,
            "outfits": outfits,
            "notifications": data.notifications,
            "items_to_wash": data.items_to_wash,
        }

    return _handle


def _filter_outfits(
    outfits: list[dict[str, Any]],
    *,
    include: list[str] | None,
    exclude: list[str] | None,
) -> list[dict[str, Any]]:
    """Apply optional include/exclude status filters.

    ``include`` and ``exclude`` are independent: ``include`` keeps only the
    matching statuses, ``exclude`` removes the matching statuses. When both
    are given, ``include`` runs first and ``exclude`` strips from the result.
    """
    if not include and not exclude:
        return outfits
    include_set = set(include) if include else None
    exclude_set = set(exclude) if exclude else set()
    result: list[dict[str, Any]] = []
    for outfit in outfits:
        status = str(outfit.get("status") or "")
        if include_set is not None and status not in include_set:
            continue
        if status in exclude_set:
            continue
        result.append(outfit)
    return result


def _make_test_notification_handler(hass: HomeAssistant):
    async def _handle(call: ServiceCall) -> None:
        client = _resolve_client(hass, call)
        try:
            await client.async_test_notification(call.data[ATTR_SETTING_ID])
        except WardrowbeApiError as err:
            raise HomeAssistantError(f"test_notification failed: {err}") from err

    return _handle
