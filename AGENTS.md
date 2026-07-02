# Repository agent instructions

> `CLAUDE.md` and `GEMINI.md` are local symlinks to this file (gitignored) — edit `AGENTS.md`.

This file is the operating manual for any AI agent (Claude Code, Codex, Copilot, etc.) extending this repository. Read it end-to-end before making changes.

Agent assets live under `.agents/` (the source of truth): `skills/`, `workflows/` (commands), `agents/`, and `memory/` (Claude's per-project memory). Per-tool scaffolding is local-only and untracked: `.claude/` is a real directory with per-item symlinks into `.agents/` (`skills`, `commands` → `workflows`, `agents`) plus Claude-specific `settings.json` / `settings.local.json`, and `.gemini` symlinks to `.agents` wholesale.

## What this project is

A Home Assistant custom component that integrates [Wardrowbe](https://github.com/Anyesh/wardrowbe) — a self-hosted AI wardrobe manager — into Home Assistant 2026.4+ (the first release with Python 3.14 support).

Scope is intentionally narrow:

- **In scope:** wardrobe-level analytics sensors, outfit/notification/wear/wash event entities, services for outfit and item actions, OIDC + dev-mode auth, multi-account.
- **Out of scope:** per-item entities (hundreds of clothes is the wrong shape for HA's entity registry), the Studio canvas UI, family-rating flows beyond what shows up in outfit feedback.

## Repo layout

```
ha_wardrowbe/
├── custom_components/wardrowbe/   ← the HA integration (edit this)
│   ├── __init__.py             # async_setup_entry / unload, runtime_data wiring
│   ├── manifest.json
│   ├── const.py                # all constants — add new ones here
│   ├── api.py                  # WardrowbeClient + TokenProvider implementations
│   ├── oauth2.py               # WardrowbeOAuth2Implementation, OIDCTokenProvider, discovery
│   ├── coordinator.py          # DataUpdateCoordinator, diff → pending_events + bus events
│   ├── config_flow.py          # multi-step flow (host → oidc/dev), reauth
│   ├── entity.py               # WardrowbeEntity base (device + unique_id)
│   ├── sensor.py / binary_sensor.py / event.py
│   ├── services.py / services.yaml
│   ├── strings.json + translations/en.json
│   └── diagnostics.py
├── .devcontainer/devcontainer.json   ← Python 3.14 + VS Code extensions
├── scripts/
│   ├── setup                    # installs HA + test deps + symlinks integration into config/
│   ├── develop                  # runs HA on :8123 from this checkout
│   └── test                     # ruff + mypy + pytest
├── tests/                       # pytest-homeassistant-custom-component
├── config/                      # devcontainer HA runtime (git-ignored except .gitkeep)
├── hacs.json
└── pyproject.toml
```

## Conventions

- **Python 3.14**, async-only, full type hints. `from __future__ import annotations` at the top of every module.
- `entry.runtime_data` is typed as `WardrowbeRuntime`; never store integration state in `hass.data[DOMAIN]` other than truly process-wide singletons.
- `unique_id` for an entry is `f"{host}::{user_id}"`. Entity `unique_id` is `f"{entry_id}_{key}"`. Don't change either without a migration.
- Services are registered once per process, not per entry. They take `config_entry_id` to disambiguate accounts.
- New constants: add to `const.py`. New translatable strings: update both `strings.json` and `translations/en.json`.
- Comments only when the *why* is non-obvious. Don't narrate code.

## How to add things

### A new sensor

1. Add a `WardrowbeSensorDescription` entry to `SENSORS` in `sensor.py` with a `value_fn(WardrowbeData)`.
2. Add `entity.sensor.<key>.name` to `strings.json` + `translations/en.json`.
3. If it needs a fresh API field, extend `WardrowbeClient` (`api.py`) and `WardrowbeCoordinator._async_update_data` (`coordinator.py`).

### A new service

1. Add a method to `WardrowbeClient` if one doesn't exist.
2. Add a constant in `const.py`, a schema + handler in `services.py`, and the YAML field block in `services.yaml`.
3. Register it inside `async_register_services` and tear it down in `async_unregister_services`.
4. Add translation keys under `services.<name>` in both string files.

### A new event type or entity

1. Add the type to the relevant `EVENT_TYPES_*` tuple in `const.py`.
2. Update `coordinator._diff` so it actually emits the type when it sees the matching change.
3. If a brand-new event group: add a `WardrowbeEventDescription` to `EVENTS` in `event.py` + a translation key.

### A new platform

Add it to `PLATFORMS` in `__init__.py` and create the corresponding module. Always extend `WardrowbeEntity` so the device link and unique_id stay consistent.

## Auth model

Wardrowbe issues 7-day JWTs from `POST /api/v1/auth/sync`. The integration manages two flavours of "what to send to /auth/sync":

- `OIDCTokenProvider` (real installs) — wraps an HA `OAuth2Session`; refreshes the OIDC token then forwards `id_token` to /auth/sync.
- `DevTokenProvider` — sends `external_id` (only valid for dev-mode installs).

`WardrowbeClient._ensure_jwt` caches the resulting JWT, refreshes ~1h before expiry, and re-syncs on any 401. Don't bypass this — every authenticated path goes through `_request`.

`StaticIdTokenProvider` exists only to bridge the config-flow's first sync immediately after OAuth completes.

## OIDC implementation registration

Wardrowbe accepts any OIDC issuer, so authorize/token URLs are not known until config-flow time. We:

1. Discover them via `.well-known/openid-configuration` (`oauth2.discover_oidc_endpoints`).
2. Register a `WardrowbeOAuth2Implementation` per host (`config_entry_oauth2_flow.async_register_implementation`) — id is `wardrowbe_<sha1(host)[:10]>`, so multiple accounts on the same host share an impl.
3. After setup, `__init__.async_setup_entry` rebuilds the implementation from `entry.data` and feeds it to `OAuth2Session` for refreshes.

### PKCE (public clients without a secret)

`WardrowbeOAuth2Implementation` switches to PKCE when `client_secret` is empty/None. In that mode it overrides three pieces of `LocalOAuth2Implementation`:

- `async_generate_authorize_url` — generates a fresh `code_verifier` (`secrets.token_urlsafe(64)`), stores it keyed by `flow_id` on the implementation, and appends `code_challenge` (SHA-256, base64url, no padding) + `code_challenge_method=S256` to the authorize URL.
- `async_resolve_external_data` — pops the verifier for the flow and includes it as `code_verifier` in the token request body. The decoded state's `flow_id` keys the lookup, so concurrent flows do not collide.
- `_token_request` — never sends `client_secret` on the PKCE branch (token-exchange and refresh both go through this method).

The PKCE state lives only in process memory on the implementation instance — verifiers are never persisted to disk. If the integration reloads mid-flow, the user re-runs the config flow.

## Local development & testing

The repo is laid out so a fresh devcontainer is the only setup step you need.

### In the devcontainer (preferred)

VS Code → "Reopen in Container" picks up `.devcontainer/devcontainer.json` (Python 3.14 base image). `postCreateCommand` runs `scripts/setup`, which installs Home Assistant 2026.5.x, ruff, mypy, and the test dependencies, then symlinks `custom_components/wardrowbe` into `config/custom_components/wardrowbe` so source edits hot-reload.

```sh
scripts/develop          # boots HA on :8123 with this integration mounted
scripts/test             # ruff + mypy + pytest
scripts/test tests/test_config_flow.py::test_dev_mode_happy_path  # arg passthrough
```

### On the host (no devcontainer)

```sh
python3.14 -m venv .venv && source .venv/bin/activate
scripts/setup            # works outside the container too
scripts/develop          # http://localhost:8123
```

### Live integration verification

1. `scripts/develop`
2. **Settings → Devices & Services → Add Integration → Wardrowbe**
3. Pick **Development mode** with a stub `external_id` against a local Wardrowbe instance, or **OIDC** against your real provider.
4. Watch `config/home-assistant.log` for `custom_components.wardrowbe` lines (DEBUG enabled by `scripts/setup`).

### Unit tests

`pytest-homeassistant-custom-component` provides the `hass` fixture and HA test infrastructure. Use `MockConfigEntry` from `pytest_homeassistant_custom_component.common`. The fixtures in `tests/conftest.py` (`dev_mode_entry`, `mock_client`, `mock_analytics`) are the building blocks for new tests.

OIDC config-flow paths are not yet covered — adding coverage requires `aioclient_mock` + `current_request_with_proxy`. See HA core's `tests/components/spotify` for a worked example.

## Don't

- Don't introduce per-item entities. The user has explicitly opted out.
- Don't add buttons. Use services for actions and event entities for observability.
- Don't store secrets outside `entry.data`. HA encrypts entry storage; ad-hoc files do not.
- Don't bypass `WardrowbeClient` to make raw HTTP calls — JWT refresh logic only runs through `_request`.
- Don't ship features that depend on an upstream Wardrowbe endpoint without verifying the endpoint exists in the version of Wardrowbe you tested against.
- Don't widen the supported HA floor below 2026.4 / Python 3.14 without removing every modern syntax + helper this code uses (PEP 695 `type` aliases, `entry.runtime_data`, etc.).

## Useful upstream references

- Wardrowbe API source (FastAPI): `https://github.com/Anyesh/wardrowbe/tree/main/backend/app/api`
- Wardrowbe Swagger UI: `<your-host>/docs` (best ground-truth for endpoint shapes)
- Home Assistant developer docs:
  - Integration creation: <https://developers.home-assistant.io/docs/creating_integration_manifest>
  - OAuth2 helper: <https://developers.home-assistant.io/docs/auth_api/#oauth2-flow>
  - Event entity: <https://developers.home-assistant.io/docs/core/entity/event>
- HACS docs: <https://hacs.xyz/docs/publish/integration>
