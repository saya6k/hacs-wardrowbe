"""DataUpdateCoordinator for Wardrowbe.

Polls analytics + recent outfits/notifications, diffs against the previous
snapshot, and surfaces changes both as ``hass.bus`` events (for automations)
and as a list of pending entity events that ``event.py`` consumes.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import WardrowbeApiError, WardrowbeAuthError, WardrowbeClient
from .const import (
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    EVENT_GROUP_NOTIFICATION,
    EVENT_GROUP_OUTFIT,
    EVENT_GROUP_WASH,
    bus_event_name,
)

_LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class PendingEvent:
    group: str
    event_type: str
    payload: dict[str, Any]


@dataclass(slots=True)
class WardrowbeData:
    healthy: bool = False
    analytics: dict[str, Any] = field(default_factory=dict)
    outfits: list[dict[str, Any]] = field(default_factory=list)
    notifications: list[dict[str, Any]] = field(default_factory=list)
    items_to_wash: list[dict[str, Any]] = field(default_factory=list)
    pending_events: list[PendingEvent] = field(default_factory=list)
    capabilities: dict[str, Any] | None = None


class WardrowbeCoordinator(DataUpdateCoordinator[WardrowbeData]):
    """Polls Wardrowbe and emits change events."""

    config_entry: ConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: WardrowbeClient,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{entry.entry_id}",
            update_interval=DEFAULT_SCAN_INTERVAL,
            config_entry=entry,
        )
        self.client = client
        self._known_outfit_status: dict[str, str] = {}
        self._known_outfit_feedback: dict[str, tuple[Any, ...]] = {}
        self._known_notification_ids: set[str] = set()
        self._known_wash_item_ids: set[str] = set()
        self._known_wash_item_meta: dict[str, dict[str, Any]] = {}
        # Suppression markers: ids the integration just acted on locally,
        # so the next diff skips the matching server-state inference and
        # we don't double-fire alongside the immediate record_local_event.
        self._recent_local_wash_ids: set[str] = set()
        self._recent_local_feedback_ids: set[str] = set()
        self._primed = False

    async def _async_update_data(self) -> WardrowbeData:
        try:
            healthy = await self.client.async_health()
            analytics = await self.client.async_analytics()
            outfits = await self.client.async_recent_outfits(limit=20)
            notifications = await self.client.async_recent_notifications(limit=50)
            items_to_wash = await self.client.async_items_needing_wash(limit=100)
        except WardrowbeAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except WardrowbeApiError as err:
            raise UpdateFailed(str(err)) from err

        # Public, unauthenticated, and non-fatal — returns None on older
        # servers or transport errors, so it never fails the whole update.
        capabilities = await self.client.async_capabilities()

        events = self._diff(outfits, notifications, items_to_wash)
        for ev in events:
            self.hass.bus.async_fire(
                bus_event_name(ev.group, ev.event_type),
                {"config_entry_id": self.config_entry.entry_id, **ev.payload},
            )

        return WardrowbeData(
            healthy=healthy,
            analytics=analytics,
            outfits=outfits,
            notifications=notifications,
            items_to_wash=items_to_wash,
            pending_events=events,
            capabilities=capabilities,
        )

    @callback
    def record_local_event(
        self, group: str, event_type: str, payload: dict[str, Any]
    ) -> None:
        """Synthesise a PendingEvent for an HA-side action.

        Wash and wear are pure counter updates — they don't show up as
        notifications or outfit-status changes, so the diff loop never
        emits them. Callers that perform such actions (todo entity,
        services, LLM tools) should call this so the matching event
        entity refreshes and a hass.bus event fires for automations.
        """
        self.hass.bus.async_fire(
            bus_event_name(group, event_type),
            {"config_entry_id": self.config_entry.entry_id, **payload},
        )
        if group == EVENT_GROUP_WASH and payload.get("item_id") is not None:
            self._recent_local_wash_ids.add(str(payload["item_id"]))
        elif (
            group == EVENT_GROUP_OUTFIT
            and event_type == "feedback_submitted"
            and payload.get("outfit_id") is not None
        ):
            self._recent_local_feedback_ids.add(str(payload["outfit_id"]))
        if self.data is not None:
            self.data.pending_events = [PendingEvent(group, event_type, dict(payload))]
            self.async_update_listeners()

    def _diff(
        self,
        outfits: list[dict[str, Any]],
        notifications: list[dict[str, Any]],
        items_to_wash: list[dict[str, Any]],
    ) -> list[PendingEvent]:
        events: list[PendingEvent] = []

        outfit_status_now: dict[str, str] = {}
        outfit_feedback_now: dict[str, tuple[Any, ...]] = {}
        for outfit in outfits:
            oid = _stringify_id(outfit)
            if oid is None:
                continue
            status = str(outfit.get("status") or "")
            outfit_status_now[oid] = status
            feedback = _outfit_feedback_signature(outfit)
            outfit_feedback_now[oid] = feedback
            if not self._primed:
                continue
            previous = self._known_outfit_status.get(oid)
            # ``sent`` is the initial state set by the upstream API when a
            # suggestion notification has just gone out — treat it the same as
            # ``pending`` for the "suggested" event so the user gets a hit
            # regardless of which state the API happens to be in when our
            # coordinator first sees the outfit.
            if previous is None and status in {"sent", "pending"}:
                events.append(PendingEvent(EVENT_GROUP_OUTFIT, "suggested", outfit))
            elif previous is not None and previous != status and status:
                if status in {"accepted", "rejected", "skipped"}:
                    events.append(PendingEvent(EVENT_GROUP_OUTFIT, status, outfit))
            previous_feedback = self._known_outfit_feedback.get(oid)
            if (
                previous_feedback is not None
                and previous_feedback != feedback
                and any(v is not None for v in feedback)
            ):
                if oid in self._recent_local_feedback_ids:
                    self._recent_local_feedback_ids.discard(oid)
                else:
                    events.append(
                        PendingEvent(EVENT_GROUP_OUTFIT, "feedback_submitted", outfit)
                    )

        wash_ids_now: set[str] = set()
        new_wash_meta: dict[str, dict[str, Any]] = {}
        for item in items_to_wash:
            iid = _stringify_id(item)
            if iid is None:
                continue
            wash_ids_now.add(iid)
            new_wash_meta[iid] = {
                "item_id": iid,
                "name": item.get("name"),
                "type": item.get("type"),
            }
        if self._primed:
            for old_id in self._known_wash_item_ids - wash_ids_now:
                if old_id in self._recent_local_wash_ids:
                    self._recent_local_wash_ids.discard(old_id)
                    continue
                payload = self._known_wash_item_meta.get(
                    old_id, {"item_id": old_id}
                )
                events.append(
                    PendingEvent(EVENT_GROUP_WASH, "logged", payload)
                )

        notification_ids_now: set[str] = set()
        for note in notifications:
            nid = _stringify_id(note)
            if nid is None:
                continue
            notification_ids_now.add(nid)
            if not self._primed or nid in self._known_notification_ids:
                continue
            ev_type = "failed" if note.get("status") == "failed" else "sent"
            events.append(PendingEvent(EVENT_GROUP_NOTIFICATION, ev_type, note))

        self._known_outfit_status = outfit_status_now
        self._known_outfit_feedback = outfit_feedback_now
        self._known_notification_ids = notification_ids_now
        self._known_wash_item_ids = wash_ids_now
        self._known_wash_item_meta = new_wash_meta
        self._primed = True
        return events


def _stringify_id(item: dict[str, Any]) -> str | None:
    raw = item.get("id")
    if raw is None:
        return None
    return str(raw)


def _outfit_feedback_signature(outfit: dict[str, Any]) -> tuple[Any, ...]:
    """Return a stable tuple of user-controlled feedback fields.

    Tracks rating, wore, and notes-style fields. If any change between
    refreshes (and at least one is non-None now), the diff infers a
    server-side feedback submission.
    """
    return (
        outfit.get("rating"),
        outfit.get("wore"),
        outfit.get("user_notes"),
        outfit.get("feedback_notes"),
    )
