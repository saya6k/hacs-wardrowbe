# Wardrowbe — Home Assistant integration

[![Built with Claude Code](https://img.shields.io/badge/Built%20with%20Claude%20Code-D97757?style=for-the-badge&logo=claude&logoColor=white)](https://claude.ai/code)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-41BDF5?style=for-the-badge&logo=homeassistant&logoColor=white)](https://www.home-assistant.io/)
[![HACS](https://img.shields.io/badge/HACS-Custom-41BDF5?style=for-the-badge&logo=homeassistantcommunitystore&logoColor=white)](https://hacs.xyz/)
[![Python](https://img.shields.io/badge/Python%203.14-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![Shell](https://img.shields.io/badge/Shell-4EAA25?style=for-the-badge&logo=gnubash&logoColor=white)](https://www.gnu.org/software/bash/)
[![GitHub Actions](https://img.shields.io/badge/GitHub%20Actions-2088FF?style=for-the-badge&logo=githubactions&logoColor=white)](.github/workflows/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green?style=for-the-badge)](#license)
[![Buy Me a Coffee](https://img.shields.io/badge/Buy%20Me%20a%20Coffee-FFDD00?style=for-the-badge&logo=buymeacoffee&logoColor=black)](https://buymeacoffee.com/saya6k)

A Home Assistant custom component for [Wardrowbe](https://github.com/Anyesh/wardrowbe), the self-hosted AI-powered wardrobe manager. Surfaces wardrobe analytics, outfit lifecycle, and notification history as sensors and event entities, and exposes outfit/wear/wash actions as services.

> Requires Home Assistant **2026.8.0b0+** (Python 3.14 support; the opt-in LLM API needs the `llm` integration added in HA's 2026.8 cycle).

## Features

- **OIDC / SSO** authentication against any provider Wardrowbe supports (PocketID, Authentik, Keycloak, Auth0, …).
- **Development mode** authentication for self-hosters who haven't wired up SSO.
- **Multiple accounts** — each Wardrowbe user (or each Wardrowbe install) is its own config entry, with an isolated entity set.
- Polling every **120 seconds**.

### Entities (per account)

| Platform | Entities |
|---|---|
| `sensor` | `total_items`, `items_ready`, `items_processing`, `items_archived`, `total_outfits`, `outfits_this_week`, `outfits_this_month`, `acceptance_rate`, `average_rating`, `total_wears`, `most_worn_item`, `top_color`, `last_outfit_status`, `notifications_last_24h` |
| `binary_sensor` | `api_healthy`, `has_pending_outfit` |
| `event` | `outfit` (suggested / accepted / rejected / skipped / feedback_submitted), `notification` (sent / failed), `wear` (logged), `wash` (logged) |

### Services

All services accept a `config_entry_id` so multi-account setups can pick which Wardrowbe account to act on.

- `wardrowbe.suggest_outfit` — generate a new outfit recommendation (returns the outfit as a response variable).
- `wardrowbe.accept_outfit` / `reject_outfit` / `skip_outfit` — `outfit_id` optional; defaults to the latest pending outfit on that account.
- `wardrowbe.submit_feedback` — rating, wore flag, notes.
- `wardrowbe.log_wear` / `log_wash`.
- `wardrowbe.archive_item` / `restore_item`.
- `wardrowbe.test_notification`.

### Bus events

Each entity event is mirrored on the Home Assistant event bus (so you can use `trigger: event` instead of `trigger: state` on the entity):

`wardrowbe_outfit_suggested`, `wardrowbe_outfit_accepted`, `wardrowbe_outfit_rejected`, `wardrowbe_outfit_skipped`, `wardrowbe_outfit_feedback_submitted`, `wardrowbe_notification_sent`, `wardrowbe_notification_failed`, `wardrowbe_wear_logged`, `wardrowbe_wash_logged`.

Every payload includes the originating `config_entry_id`.

## Installation

### HACS (recommended)

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=saya6k&repository=hacs-wardrowbe&category=integration)

1. In HACS → Integrations → Custom repositories, add `https://github.com/saya6k/ha_wardrowbe` as type **Integration**.
2. Install **Wardrowbe** from HACS.
3. Restart Home Assistant.
4. **Settings → Devices & Services → Add Integration → Wardrowbe**.

### Manual

Copy `custom_components/wardrowbe/` into your Home Assistant `config/custom_components/` directory and restart.

### Local development

The repo ships with a Python 3.14 devcontainer that runs Home Assistant against this checkout:

```sh
scripts/develop          # HA on :8123 with the integration symlinked in
scripts/test             # ruff + mypy + pytest
```

See [`AGENTS.md`](AGENTS.md) for the full dev/test workflow.

## Configuration

### OIDC

You'll need an OIDC client registered with your provider for Home Assistant. Use HA's redirect URL: `https://<your-ha-host>/auth/external/callback`. The integration supports both **confidential clients** (client_id + client_secret) and **public clients** (client_id only — code_challenge/code_verifier handled automatically). PKCE is a separate toggle from having a secret: a public client must use it, but a confidential client can opt into it too if your provider supports PKCE alongside a secret.

In the integration config flow:

1. Enter your Wardrowbe URL (e.g. `https://wardrowbe.example.com`) and pick **OIDC / SSO**.
2. Enter the **OIDC issuer URL** (auto-suggested from `/api/v1/auth/config` when available), **client ID**, **client secret** if your client has one (leave blank for a public client), and whether to **use PKCE** (on by default; required if the secret is blank). Scopes default to `openid profile email offline_access`.
3. Complete the provider's login + consent flow.
4. The integration exchanges the resulting `id_token` for a Wardrowbe JWT and stores both. Tokens refresh automatically; reauthentication is prompted only if refresh fails.

### Development mode

Pick **Development mode** in step 1 and enter the `external_id` you log in with locally. Only works against Wardrowbe installs running in dev auth mode.

### Multiple accounts

Run the **Add Integration** flow once per account. Each entry creates its own device, sensors, event entities, and shows up in the `config_entry_id` selector for service calls.

### Reconfiguring

Open **Settings → Devices & Services → Wardrowbe → ⋮ → Reconfigure** on an existing entry to change its host, `verify_ssl`, auth mode, or (for OIDC) issuer/client ID/client secret/scopes — no need to remove and re-add it. Leaving the client secret blank keeps whatever was already stored; it only switches to PKCE if the entry didn't have a secret to begin with.

### Voice assistant / LLM tools

Each Wardrowbe account registers its own LLM API — **Wardrowbe — `<account title>`** — that you attach explicitly to a conversation agent; it's never enabled automatically. In **Settings → Voice assistants**, edit an agent, and pick it from the LLM API selector to give that agent ten tools covering outfit suggestions, wardrobe stats, and wash tracking. With multiple accounts, each gets its own selectable API. It's also reachable over MCP at `/api/mcp/wardrowbe__<entry_id>` with an HA admin access token, if you're driving Wardrowbe from an external MCP client instead of HA's own conversation agents.

## Automations

#### Notify when a new outfit is suggested

```yaml
trigger:
  - platform: state
    entity_id: event.wardrowbe_test_user_outfit_lifecycle
    attribute: event_type
    to: suggested
action:
  - service: notify.mobile_app_phone
    data:
      title: New outfit ready
      message: "{{ trigger.to_state.attributes.name }}"
```

Or via the bus:

```yaml
trigger:
  - platform: event
    event_type: wardrowbe_outfit_suggested
action:
  - service: notify.mobile_app_phone
    data:
      message: "{{ trigger.event.data.name }}"
```

#### Trigger a suggestion every morning

```yaml
trigger:
  - platform: time
    at: "07:00:00"
action:
  - service: wardrowbe.suggest_outfit
    data:
      config_entry_id: <your-entry-id>
      occasion: work
      target_date: "{{ now().date() }}"
    response_variable: suggestion
  - service: notify.mobile_app_phone
    data:
      message: "Today's outfit: {{ suggestion.name }}"
```

## License

MIT.
