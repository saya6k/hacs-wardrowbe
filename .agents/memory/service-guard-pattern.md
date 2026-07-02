---
name: service-guard-pattern
description: All service handlers must be wrapped with _guard to prevent ERROR log spam from stale config entries
metadata: 
  node_type: memory
  type: project
  originSessionId: e88bf81a-82e3-4de3-908b-02dd0b289b76
---

New service handlers registered in `async_register_services` must be wrapped with `_guard()` so `ServiceValidationError` from stale/deleted config entries doesn't propagate to aiohttp's top-level error handler.

`_guard` lives in `custom_components/wardrowbe/services.py` and catches only `ServiceValidationError` — `HomeAssistantError` (entry not loaded) still propagates.

Related: `_resolve_latest_pending_outfit` raises `HomeAssistantError` (not `ServiceValidationError`) for "no actionable outfit" so the guard doesn't swallow business-logic validation errors. See [[strings-json-parity]] for the companion i18n requirement.
