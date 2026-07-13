"""Constants for the Wardrowbe integration."""

from __future__ import annotations

from datetime import timedelta
from typing import Final

DOMAIN: Final = "wardrowbe"

LLM_API_NAME: Final = "Wardrowbe"

DEFAULT_SCAN_INTERVAL: Final = timedelta(seconds=120)
DEFAULT_TIMEOUT: Final = 30

# Config keys
CONF_HOST: Final = "host"
CONF_VERIFY_SSL: Final = "verify_ssl"
CONF_AUTH_MODE: Final = "auth_mode"
CONF_EXTERNAL_ID: Final = "external_id"
CONF_ISSUER_URL: Final = "issuer_url"
CONF_AUTHORIZE_URL: Final = "authorize_url"
CONF_TOKEN_URL: Final = "token_url"
CONF_CLIENT_ID: Final = "client_id"
CONF_CLIENT_SECRET: Final = "client_secret"
CONF_SCOPES: Final = "scopes"
CONF_USER_ID: Final = "user_id"
CONF_USER_NAME: Final = "user_name"

AUTH_MODE_OIDC: Final = "oidc"
AUTH_MODE_DEV: Final = "dev"

DEFAULT_OIDC_SCOPES: Final = "openid profile email offline_access"

# API paths
API_BASE: Final = "/api/v1"
API_HEALTH: Final = f"{API_BASE}/health"
API_CAPABILITIES: Final = f"{API_BASE}/capabilities"
API_AUTH_CONFIG: Final = f"{API_BASE}/auth/config"
API_AUTH_SYNC: Final = f"{API_BASE}/auth/sync"
API_AUTH_SESSION: Final = f"{API_BASE}/auth/session"
API_ANALYTICS: Final = f"{API_BASE}/analytics"
API_OUTFITS: Final = f"{API_BASE}/outfits"
API_OUTFIT_SUGGEST: Final = f"{API_BASE}/outfits/suggest"
API_NOTIFICATIONS_HISTORY: Final = f"{API_BASE}/notifications/history"
API_NOTIFICATIONS_SETTINGS: Final = f"{API_BASE}/notifications/settings"
API_ITEMS: Final = f"{API_BASE}/items"

# Event entity groups (one entity per group, multiple event_types each)
EVENT_GROUP_OUTFIT: Final = "outfit"
EVENT_GROUP_NOTIFICATION: Final = "notification"
EVENT_GROUP_WEAR: Final = "wear"
EVENT_GROUP_WASH: Final = "wash"

EVENT_TYPES_OUTFIT: Final = (
    "suggested",
    "accepted",
    "rejected",
    "skipped",
    "feedback_submitted",
)
EVENT_TYPES_NOTIFICATION: Final = ("sent", "failed")
EVENT_TYPES_WEAR: Final = ("logged",)
EVENT_TYPES_WASH: Final = ("logged",)

# HA bus events (mirror entity events for users who prefer event triggers)
BUS_EVENT_PREFIX: Final = "wardrowbe"


def bus_event_name(group: str, event_type: str) -> str:
    """Return the canonical hass.bus event name for a group/type."""
    return f"{BUS_EVENT_PREFIX}_{group}_{event_type}"


# Service names
SERVICE_SUGGEST_OUTFIT: Final = "suggest_outfit"
SERVICE_ACCEPT_OUTFIT: Final = "accept_outfit"
SERVICE_REJECT_OUTFIT: Final = "reject_outfit"
SERVICE_SKIP_OUTFIT: Final = "skip_outfit"
SERVICE_SUBMIT_FEEDBACK: Final = "submit_feedback"
SERVICE_LOG_WEAR: Final = "log_wear"
SERVICE_LOG_WASH: Final = "log_wash"
SERVICE_ARCHIVE_ITEM: Final = "archive_item"
SERVICE_RESTORE_ITEM: Final = "restore_item"
SERVICE_TEST_NOTIFICATION: Final = "test_notification"
SERVICE_GET_SUMMARY: Final = "get_summary"

ATTR_CONFIG_ENTRY_ID: Final = "config_entry_id"
ATTR_OUTFIT_ID: Final = "outfit_id"
ATTR_ITEM_ID: Final = "item_id"
ATTR_OCCASION: Final = "occasion"
ATTR_TIME_OF_DAY: Final = "time_of_day"
ATTR_TARGET_DATE: Final = "target_date"
ATTR_NOTES: Final = "notes"
ATTR_RATING: Final = "rating"
ATTR_WORE: Final = "wore"
ATTR_REASON: Final = "reason"
ATTR_DATE: Final = "date"
ATTR_SETTING_ID: Final = "setting_id"
ATTR_EXCLUDE_STATUSES: Final = "exclude_statuses"
ATTR_INCLUDE_STATUSES: Final = "include_statuses"

# Valid persistent outfit statuses (rendered in entities, dashboards, …).
# Note: ``feedback_submitted`` is an *event type*, not a status.
#
# ``sent`` is an intermediate state set by the upstream API once the suggestion
# notification has been dispatched but before the user has interacted with it.
# Practically it's "pending" from the integration's point of view — actionable
# but unresolved — so the action services and the latest-actionable resolver
# treat it the same.
VALID_OUTFIT_STATUSES: Final = ("sent", "pending", "accepted", "rejected", "skipped")

# Statuses that are awaiting user input (reject / accept / skip operate on
# these). Kept narrower than VALID_OUTFIT_STATUSES on purpose: terminal
# states like ``rejected`` are not actionable.
ACTIONABLE_OUTFIT_STATUSES: Final = ("sent", "pending")

# Wardrowbe accepts a fixed set of occasions (case-insensitive) per
# backend/app/api/outfits.py:VALID_OCCASIONS. Mirrored here so the service
# selector can render a dropdown.
VALID_OCCASIONS: Final = (
    "beach",
    "brunch",
    "business-casual",
    "casual",
    "date",
    "dinner",
    "formal",
    "gym",
    "hiking",
    "interview",
    "lounge",
    "office",
    "outdoor",
    "party",
    "running",
    "smart-casual",
    "sport",
    "sporty",
    "travel",
    "wedding",
    "weekend",
    "work",
)

VALID_TIME_OF_DAY: Final = (
    "morning",
    "afternoon",
    "evening",
    "night",
    "full_day",
)
