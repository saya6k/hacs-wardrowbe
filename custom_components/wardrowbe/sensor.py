"""Wardrowbe sensors derived from /analytics + recent outfits."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import WardrowbeConfigEntry
from .coordinator import WardrowbeData
from .entity import WardrowbeEntity


@dataclass(frozen=True, kw_only=True, slots=True)
class WardrowbeSensorDescription(SensorEntityDescription):
    """Describes a Wardrowbe sensor."""

    value_fn: Callable[[WardrowbeData], Any]
    attrs_fn: Callable[[WardrowbeData], dict[str, Any]] | None = None


def _stat(data: WardrowbeData, *path: str) -> Any:
    cur: Any = data.analytics
    for key in path:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
    return cur


def _last_outfit(data: WardrowbeData) -> dict[str, Any] | None:
    return data.outfits[0] if data.outfits else None


def _most_worn(data: WardrowbeData) -> dict[str, Any] | None:
    items = _stat(data, "most_worn") or []
    if isinstance(items, list) and items:
        first = items[0]
        if isinstance(first, dict):
            return first
    return None


def _top_color(data: WardrowbeData) -> dict[str, Any] | None:
    dist = _stat(data, "color_distribution") or []
    if isinstance(dist, list) and dist:
        first = dist[0]
        if isinstance(first, dict):
            return first
    return None


TOP_COLOR_OPTIONS: tuple[str, ...] = (
    "beige",
    "black",
    "blue",
    "brown",
    "cream",
    "gold",
    "gray",
    "green",
    "khaki",
    "maroon",
    "mixed",
    "multicolor",
    "navy",
    "olive",
    "orange",
    "pink",
    "purple",
    "red",
    "silver",
    "tan",
    "teal",
    "white",
    "yellow",
)

_TOP_COLOR_ALIASES: dict[str, str] = {
    "grey": "gray",
    "multi": "multicolor",
    "multi-color": "multicolor",
    "multi_color": "multicolor",
    "multicolour": "multicolor",
    "multi-colour": "multicolor",
}


def _normalize_top_color(data: WardrowbeData) -> str | None:
    raw = (_top_color(data) or {}).get("color") or (_top_color(data) or {}).get("name")
    if not raw:
        return None
    key = str(raw).strip().lower()
    key = _TOP_COLOR_ALIASES.get(key, key)
    return key if key in TOP_COLOR_OPTIONS else None


def _count_recent_notifications(data: WardrowbeData) -> int:
    cutoff = datetime.now(UTC) - timedelta(hours=24)
    count = 0
    for note in data.notifications:
        ts = note.get("created_at") or note.get("sent_at") or note.get("timestamp")
        if not ts:
            continue
        try:
            parsed = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        except ValueError:
            continue
        if parsed >= cutoff:
            count += 1
    return count


SENSORS: tuple[WardrowbeSensorDescription, ...] = (
    WardrowbeSensorDescription(
        key="total_items",
        translation_key="total_items",
        icon="mdi:hanger",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: _stat(d, "wardrobe", "total_items"),
    ),
    WardrowbeSensorDescription(
        key="items_ready",
        translation_key="items_ready",
        icon="mdi:check-circle-outline",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: _stat(d, "wardrobe", "items_by_status", "ready"),
    ),
    WardrowbeSensorDescription(
        key="items_processing",
        translation_key="items_processing",
        icon="mdi:progress-clock",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: _stat(d, "wardrobe", "items_by_status", "processing"),
    ),
    WardrowbeSensorDescription(
        key="items_archived",
        translation_key="items_archived",
        icon="mdi:archive-outline",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: _stat(d, "wardrobe", "items_by_status", "archived"),
    ),
    WardrowbeSensorDescription(
        key="total_outfits",
        translation_key="total_outfits",
        icon="mdi:tshirt-crew-outline",
        state_class=SensorStateClass.TOTAL,
        value_fn=lambda d: _stat(d, "wardrobe", "total_outfits"),
    ),
    WardrowbeSensorDescription(
        key="outfits_this_week",
        translation_key="outfits_this_week",
        icon="mdi:calendar-week",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: _stat(d, "wardrobe", "outfits_this_week"),
    ),
    WardrowbeSensorDescription(
        key="outfits_this_month",
        translation_key="outfits_this_month",
        icon="mdi:calendar-month",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: _stat(d, "wardrobe", "outfits_this_month"),
    ),
    WardrowbeSensorDescription(
        key="acceptance_rate",
        translation_key="acceptance_rate",
        icon="mdi:thumb-up-outline",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: _stat(d, "wardrobe", "acceptance_rate"),
    ),
    WardrowbeSensorDescription(
        key="average_rating",
        translation_key="average_rating",
        icon="mdi:star-outline",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: _stat(d, "wardrobe", "average_rating"),
    ),
    WardrowbeSensorDescription(
        key="total_wears",
        translation_key="total_wears",
        icon="mdi:counter",
        state_class=SensorStateClass.TOTAL,
        value_fn=lambda d: _stat(d, "wardrobe", "total_wears"),
    ),
    WardrowbeSensorDescription(
        key="most_worn_item",
        translation_key="most_worn_item",
        icon="mdi:trophy-outline",
        value_fn=lambda d: (_most_worn(d) or {}).get("name"),
        attrs_fn=lambda d: _most_worn(d) or {},
    ),
    WardrowbeSensorDescription(
        key="top_color",
        translation_key="top_color",
        icon="mdi:palette-outline",
        device_class=SensorDeviceClass.ENUM,
        options=list(TOP_COLOR_OPTIONS),
        value_fn=_normalize_top_color,
        attrs_fn=lambda d: {
            "raw": (_top_color(d) or {}).get("color")
            or (_top_color(d) or {}).get("name"),
            "distribution": _stat(d, "color_distribution") or [],
        },
    ),
    WardrowbeSensorDescription(
        key="last_outfit_status",
        translation_key="last_outfit_status",
        icon="mdi:hanger",
        value_fn=lambda d: (_last_outfit(d) or {}).get("status"),
        attrs_fn=lambda d: _last_outfit(d) or {},
    ),
    WardrowbeSensorDescription(
        key="notifications_last_24h",
        translation_key="notifications_last_24h",
        icon="mdi:bell-outline",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_count_recent_notifications,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: WardrowbeConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data.coordinator
    async_add_entities(
        WardrowbeSensor(coordinator, description) for description in SENSORS
    )


class WardrowbeSensor(WardrowbeEntity, SensorEntity):
    """Coordinator-backed sensor."""

    entity_description: WardrowbeSensorDescription

    def __init__(
        self,
        coordinator: Any,
        description: WardrowbeSensorDescription,
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> Any:
        if self.coordinator.data is None:
            return None
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self.entity_description.attrs_fn is None or self.coordinator.data is None:
            return None
        attrs = self.entity_description.attrs_fn(self.coordinator.data)
        return {k: v for k, v in attrs.items() if not isinstance(v, (bytes, bytearray))}
