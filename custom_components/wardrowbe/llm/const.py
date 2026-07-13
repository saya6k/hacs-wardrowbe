"""Constants for the Wardrowbe LLM API."""

from __future__ import annotations

SOURCE = "wardrowbe"

# Shared context only; per-tool "when to call" guidance lives on each
# Tool's own `description`, and per-call rendering/reply guidance lives on
# each async_call's returned `instruction` field.
API_PROMPT = (
    "Wardrowbe manages the user's wardrobe: outfit suggestions, wear/wash "
    "history, and item stats."
)
