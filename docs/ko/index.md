# Wardrowbe — Home Assistant 통합

셀프호스팅 AI 옷장 관리자 [Wardrowbe](https://github.com/Anyesh/wardrowbe)용 Home Assistant 커스텀 컴포넌트. 옷장 분석, 아웃핏 수명주기, 알림 이력을 sensor·event 엔티티로 노출하고, 아웃핏/착용/세탁 액션을 서비스로 제공합니다.

> Home Assistant **2026.8.0b0+** (Python 3.14 지원; LLM 툴 플랫폼 마이그레이션이 HA 2026.8 사이클에서 추가된 `llm` 통합을 필요로 함) 필요.

## 기능

- **OIDC / SSO** — Wardrowbe가 지원하는 모든 프로바이더(PocketID, Authentik, Keycloak, Auth0 등)로 인증.
- **개발 모드** 인증 — SSO를 설정하지 않은 셀프호스터용.
- **다중 계정** — Wardrowbe 사용자(또는 Wardrowbe 인스턴스)마다 별도 config entry를 만들어 엔티티 셋을 분리.
- **120초**마다 폴링.

### 엔티티 (계정당)

| 플랫폼 | 엔티티 |
|---|---|
| `sensor` | `total_items`, `items_ready`, `items_processing`, `items_archived`, `total_outfits`, `outfits_this_week`, `outfits_this_month`, `acceptance_rate`, `average_rating`, `total_wears`, `most_worn_item`, `top_color`, `last_outfit_status`, `notifications_last_24h` |
| `binary_sensor` | `api_healthy`, `has_pending_outfit` |
| `event` | `outfit` (suggested / accepted / rejected / skipped / feedback_submitted), `notification` (sent / failed), `wear` (logged), `wash` (logged) |

### 서비스

모든 서비스는 `config_entry_id`를 받으므로 다중 계정 설정에서 어느 Wardrowbe 계정에 대해 동작할지 선택할 수 있습니다.

- `wardrowbe.suggest_outfit` — 새 아웃핏 추천 생성 (응답 변수로 아웃핏 반환).
- `wardrowbe.accept_outfit` / `reject_outfit` / `skip_outfit` — `outfit_id` 선택적; 기본값은 해당 계정의 최신 pending 아웃핏.
- `wardrowbe.submit_feedback` — 평점, 착용 여부, 메모.
- `wardrowbe.log_wear` / `log_wash`.
- `wardrowbe.archive_item` / `restore_item`.
- `wardrowbe.test_notification`.

### 버스 이벤트

각 엔티티 이벤트는 Home Assistant 이벤트 버스에도 미러링됩니다 (엔티티에 `trigger: state` 대신 `trigger: event` 사용 가능):

`wardrowbe_outfit_suggested`, `wardrowbe_outfit_accepted`, `wardrowbe_outfit_rejected`, `wardrowbe_outfit_skipped`, `wardrowbe_outfit_feedback_submitted`, `wardrowbe_notification_sent`, `wardrowbe_notification_failed`, `wardrowbe_wear_logged`, `wardrowbe_wash_logged`.

모든 페이로드에 원본 `config_entry_id`가 포함됩니다.

## 설치

### HACS (권장)

1. HACS → Integrations → Custom repositories에서 `https://github.com/saya6k/ha_wardrowbe`를 **Integration** 타입으로 추가.
2. HACS에서 **Wardrowbe** 설치.
3. Home Assistant 재시작.
4. **설정 → 기기 및 서비스 → 통합 추가 → Wardrowbe**.

### 수동

`custom_components/wardrowbe/`를 Home Assistant의 `config/custom_components/`에 복사 후 재시작.

### 로컬 개발

repo에는 Python 3.14 devcontainer가 포함되어 있어 이 체크아웃에 대해 Home Assistant를 실행합니다:

```sh
scripts/develop          # 통합을 symlink한 채 HA를 :8123에서 실행
scripts/test             # ruff + mypy + pytest
```

전체 개발/테스트 워크플로는 [`AGENTS.md`](AGENTS.md) 참조.

## 구성

### OIDC

Home Assistant용 OIDC 클라이언트를 프로바이더에 등록해야 합니다. HA의 redirect URL은 `https://<your-ha-host>/auth/external/callback`. 통합은 **confidential client**(client_id + client_secret)와 **public client + PKCE**(client_id만 — code_challenge/code_verifier 자동 처리) 모두 지원합니다.

통합 config flow에서:

1. Wardrowbe URL(예: `https://wardrowbe.example.com`) 입력 후 **OIDC / SSO** 선택.
2. **OIDC issuer URL** (가능하면 `/api/v1/auth/config`에서 자동 추천), **client ID**, 클라이언트에 시크릿이 있다면 **client secret** 입력 — public/PKCE 클라이언트라면 비워두세요. Scope 기본값은 `openid profile email offline_access`.
3. 프로바이더의 로그인 + consent 플로 완료.
4. 통합이 받은 `id_token`을 Wardrowbe JWT로 교환하여 둘 다 저장합니다. 토큰은 자동 갱신되며, 갱신 실패 시에만 재인증을 요청합니다.

### 개발 모드

1단계에서 **Development mode** 선택 후 로컬에서 로그인하는 `external_id`를 입력. dev auth 모드로 실행 중인 Wardrowbe 인스턴스에서만 동작.

### 다중 계정

계정마다 **통합 추가** 플로를 한 번씩 실행. 각 entry는 자체 device, sensor, event 엔티티를 만들고, 서비스 호출의 `config_entry_id` 선택지에 나타납니다.

### 재구성

기존 entry의 **Settings → Devices & Services → Wardrowbe → ⋮ → Reconfigure**에서 host, `verify_ssl`, 인증 모드, (OIDC의 경우) issuer/client ID/client secret/scope를 삭제 후 재등록 없이 변경할 수 있습니다. client secret을 비워두면 기존에 저장된 값이 유지되며, 원래 secret이 없던 entry에서만 PKCE로 전환됩니다.

## 자동화

#### 새 아웃핏 제안 시 알림

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

또는 버스를 통해:

```yaml
trigger:
  - platform: event
    event_type: wardrowbe_outfit_suggested
action:
  - service: notify.mobile_app_phone
    data:
      message: "{{ trigger.event.data.name }}"
```

#### 매일 아침 아웃핏 제안 트리거

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

## 라이선스

MIT.
