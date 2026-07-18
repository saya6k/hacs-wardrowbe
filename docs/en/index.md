# Wardrowbe — Home Assistant integration

A Home Assistant custom component for [Wardrowbe](https://github.com/Anyesh/wardrowbe), the self-hosted AI-powered wardrobe manager. Surfaces wardrobe analytics, outfit lifecycle, and notification history as sensors and event entities, and exposes outfit/wear/wash actions as services.

> Requires Home Assistant **2026.8.0b0+** (Python 3.14 support; the LLM tools-platform migration needs the `llm` integration added in HA's 2026.8 cycle).

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
