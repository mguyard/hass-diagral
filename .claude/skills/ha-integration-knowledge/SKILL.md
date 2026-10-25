---
name: ha-integration-knowledge
description: Everything needed to build, test and review the hass-diagral integration — architecture, data flow, entity patterns, webhook mechanics, invariants, Home Assistant expectations, and the deliberate deviations this project has taken. Primary reference for any work in custom_components/diagral/.
---

# Home Assistant Integration Knowledge — hass-diagral

Use this skill for any implementation, review, or debugging task in the `custom_components/diagral/` codebase. Sections 1 to 9 cover this project; §10 covers what Home Assistant expects of any integration, and §11 the places where this project departs from it.

The rules themselves — invariants, commit format, branches — are in `AGENTS.md`. This skill explains the code they apply to.

---

## 1. Project Stack

- **Language**: Python 3.14 (required by Home Assistant since 2026.3), `async`/`await` everywhere for I/O
- **Framework**: Home Assistant custom component, `integration_type: hub`, `iot_class: cloud_polling`
- **Dependencies**: `pydiagral` (pinned in `manifest.json`); HA `alarm_control_panel` and `cloud` (declared in `dependencies`)
  - Documentation: [mguyard.github.io/pydiagral](https://mguyard.github.io/pydiagral/), or Context7. Source: [github.com/mguyard/pydiagral](https://github.com/mguyard/pydiagral).
  - Check the installed version's API before using a class, method or model — do not assume it.
- **Linter**: `ruff` — `ruff check` and `ruff format --check`, configured in `custom_components/diagral/pyproject.toml`. Line length 88, `E501` deliberately ignored. CI pins `ruff==0.16.1`.
- **Tests**: `pytest` with `asyncio_mode = "auto"` — see `testing-hass-diagral`

---

## 2. Data Flow

### 2.1 Setup (`__init__.py`)

1. `DiagralConfigData.from_config_entry(entry)` builds typed config from `entry.data` + `entry.options`.
2. `DiagralAPI(username, password, serial_id, apikey, secret_key, pincode, request_timeout=..., session=async_get_clientsession(hass))` is created. It uses Home Assistant's shared HTTP session, which pydiagral never closes, so there is no `__aenter__`/`__aexit__` to pair. The config flow and `async_remove_entry` pass the same session.
3. `DiagralDataUpdateCoordinator(hass, api)` runs `async_config_entry_first_refresh()`.
4. `register_webhook(...)` runs (see §2.3) and returns a webhook id, or `None` when no suitable URL exists.
5. `entry.runtime_data = DiagralData(config, coordinator, api, webhook_id)`, then platforms are forwarded.

`DiagralAPIError` during setup becomes `ConfigEntryNotReady`.

### 2.2 Polling (`coordinator.py`)

Every 300 s (`DEFAULT_SCAN_INTERVAL`) the coordinator calls `get_configuration`, `get_devices_info`, `get_system_status`, `get_anomalies`, and stores a dict:

```python
coordinator.data["alarm_config"]    # AlarmConfiguration (groups, presence_group, alarm.central.serial/firmwares…)
coordinator.data["devices_infos"]   # DeviceList (cameras, commands, sensors, sirens, transmitters)
coordinator.data["groups"]          # list[Group] — alarm_config.groups
coordinator.data["system_status"]   # SystemStatus (status, activated_groups)
coordinator.data["anomalies"]       # Anomalies, or a falsy value when there are none
```

`DiagralAPIError` becomes `UpdateFailed`. After each successful poll the device registry `sw_version` is updated if the central's firmware changed.

### 2.3 Webhook registration (`__init__.py`)

- The webhook id is kept in `entry.data[CONF_WEBHOOK_ID]` (redacted in diagnostics), so the URL survives restarts and a subscription already pointing to it is not rewritten. A new id is generated only for an entry that has none.
- The URL comes from `get_url(require_ssl=True, allow_internal=False, allow_cloud=True, prefer_external=True)` (`_async_webhook_url`).
- **Failures raise `WebhookUnavailable(reason)`**, never return `None` silently: `webhook_no_url` (no external HTTPS URL, or no active Nabu Casa subscription) or `webhook_registration_failed` (a Diagral or cloud error). At setup, `report_webhook_unavailable` turns it into a repair issue of that key and setup continues, polling only; the `register_webhook` action turns it into a translated `HomeAssistantError`.
- The local handler is registered **before** the subscription, so no event is lost once Diagral points here, and removed again if the subscription fails or is left to another installation.
- If it ends with `HA_CLOUD_DOMAIN` (`.nabu.casa`) and a Nabu Casa subscription is active, a **cloudhook** is created; otherwise the URL is `<external_url>/api/webhook/<webhook_id>`.
- **Ownership.** Each entry stores `webhook_url_hash` in `entry.data`: the SHA-256 of the URL it registered (never the URL, which carries the secret webhook id). The central's subscription is "ours" when its URL hashes to that value; an entry without a stored hash (set up before ownership was tracked) falls back once to comparing scheme and host.
- `api.get_webhook()` → no subscription: **register** one. Our subscription: **update** it. Someone else's: leave it untouched, log a warning with the host only, and raise the fixable repair issue `webhook_owned_elsewhere_<entry_id>` (severity ERROR: intrusion alerts only arrive by webhook). `take_over=True` — passed by the repair's fix flow (`repairs.py`) and by the `register_webhook` action — updates a foreign subscription anyway.
- After a successful register or update, the hash and the webhook id are stored and the three webhook repair issues deleted. Subscriptions cover anomaly, alert and state.
- `unregister_webhook` deletes the subscription only when its hash matches, then forgets the hash; it deletes our cloudhook if the subscription was one, always unregisters the local webhook, and clears `runtime_data.webhook_id`. It returns `False` when the subscription could not be read or deleted; the `unregister_webhook` action then raises. The stored webhook id is kept for the next registration.
- Two installations behind Nabu Casa share the `hooks.nabu.casa` host: only the hash tells their subscriptions apart. See `AGENTS.md` → Validation.

### 2.4 Incoming webhook (`webhook.py`)

1. Parse the JSON into `WebHookNotification.from_dict(...)`.
2. Find the entry whose `runtime_data.webhook_id` matches.
3. `STATUS` and `ANOMALY` → `coordinator.async_request_refresh()`.
4. `ALERT` and `ANOMALY` → `enrich_data_alert_anomaly` fills `detail.device_label` from `devices_infos` (device type lower-cased + `s`, matched on index).
5. `publish_event` pops `alarm_type`, sends the dispatcher signals `signal-diagral-webhook-<TYPE>` (global, kept for existing listeners) and `signal-diagral-<entry_id>-webhook-<TYPE>` (what the panel listens to), and fires `DIAGRAL_EVENT` on the bus with `{"type", "data", "entry_id", "entity_id"}`. `logbook.py` describes it in the activity log.

### 2.5 Alarm panel (`alarm_control_panel.py`)

- State mapping from `system_status.status`: `off` → `DISARMED`, `group` → `ARMED_AWAY`, `tempo_group` → `ARMING`, `presence` → `ARMED_HOME`.
- `TRIGGERED` is set by an `ALERT` webhook with alarm code 1130 (intrusion), 1139 (intrusion confirmed) or 1141 (pre-alarm confirmed), and adds a `trigger` attribute (group name and id). It **sticks** until a poll reports `DISARMED`.
- `STATUS` webhooks set `changed_by` from the notification's user.
- Code requirement follows the `alarmpanel_actiontype_code` option: `never`, `disarm` (code only to disarm, or when armed), `always`.
- Entity services: `arm_groups`, `disarm_groups` (`group_ids`: int or list of ints), `register_webhook`, `unregister_webhook`.

### 2.6 Sensors (`sensor.py`)

- `anomalies` (translation `alarm_anomalies`): count of `AnomalyDetail` across all lists of `Anomalies`; attributes list each anomaly with group and device labels resolved, plus `created_at` / `updated_at` in local time.
- `active_groups`: number of active groups — `alarm_config.presence_group` in `PRESENCE` mode, else `system_status.activated_groups`; attribute `groups` lists every group with an `active` flag.

### 2.7 Config flow (`config_flow.py`)

- `user` (serial id) → `account` (e-mail, password, PIN; validated with an **ephemeral** API key, created then deleted) → `options` (alarm panel code options; validated **non-ephemeral**, the API key and secret key are stored in the entry). Unique id is the serial.
- `reconfigure` updates credentials, revalidating only if they changed.
- The options flow schedules a reload when options change.
- `async_remove_entry` logs in and deletes the stored API key from the Diagral cloud.
- `CONFIG_VERSION = 2`, `CONFIG_MINOR_VERSION = 1`; `async_migrate_entry` handles version 1.

---

## 3. Key Patterns

### 3.1 Typed config entry

```python
from . import DiagralConfigEntry
# NOT: from homeassistant.config_entries import ConfigEntry
```

### 3.2 Entity base class and description

```python
@dataclass(frozen=True)
class DiagralSensorEntityDescription(SensorEntityDescription):
    """Sensor entity description for Diagral."""

    exists_fn: Callable[..., bool] = lambda _: True


class DiagralSensor(DiagralEntity, SensorEntity):
    ...
```

`DiagralEntity` sets `_attr_has_entity_name = True` and returns `coordinator.get_alarm_central_device()` as `device_info`.

### 3.3 unique_id

```python
self._attr_unique_id = (
    f"{entry_id}_{DOMAIN}_{alarm_config.alarm.central.serial}_{description.key}"
)
```

### 3.4 API errors

```python
from pydiagral.exceptions import DiagralAPIError

try:
    await api.some_call()
except DiagralAPIError as err:
    raise UpdateFailed(f"Error communicating with API: {err}") from err
```

### 3.5 Async rules

- All I/O uses `async`/`await`; no `time.sleep`, no synchronous HTTP
- `@callback` on `_handle_coordinator_update` and on dispatcher handlers
- Subscriptions made in `async_added_to_hass` are wrapped in `self.async_on_remove(...)`

---

## 4. Testing

See `testing-hass-diagral` for environments, fixtures, mocking strategy and the mandatory test impact analysis. To prove behaviour on a running Home Assistant without touching the production central, see `live-validation-hass-diagral`.

---

## 5. New Entity — Full Guide

### 5.1 Required information (clarify before implementing)

If any of the following is unclear, ask with `AskUserQuestion` before starting.

1. **Entity type** — `sensor`, `binary_sensor`, or another platform (a new platform must be added to `PLATFORMS` in `__init__.py`)
2. **Key** — snake_case, unique within the platform; it becomes part of the unique id and cannot be renamed later
3. **What it represents** — which coordinator data it reads
4. **Unit of measurement**, device class, entity category
5. **Conditional** — if it only exists for some installations, define `exists_fn`

### 5.2 Implementation steps (all required, in one pass)

1. Description in the platform's `tuple[...EntityDescription, ...]`, with `translation_key`
2. `unique_id` following §3.3
3. `translation_key` in both `en.json` and `fr.json`
4. Row in `docs/integration/entities.mdx`
5. Tests in `tests/test_<platform>.py` — `unique_id` format, state value, `exists_fn` if defined, missing-data path
6. Commit: `feat(<platform>): ✨ Add <entity_name> entity`

### 5.3 Translation format

```json
"entity": {
    "sensor": {
        "my_sensor": { "name": "Human Readable Name" }
    }
}
```

### 5.4 Documentation review on every code change

1. Scan `docs/integration/` for pages covering the changed area (entities, actions, events, webhook, setup).
2. Update only what changed, in the existing style — see `docs-hass-diagral`.
3. When unsure whether docs need updating, ask with `AskUserQuestion`.

---

## 6. CI Checks (non-local)

| Check | Where | What it validates |
|-------|-------|-------------------|
| pytest | `tests.yaml`, on `dev` | Suite on HA stable and newer beta |
| ruff | `lint.yaml`, on `dev` | `ruff check` + `ruff format --check` |
| `hassfest` | `home-assistant.yaml`, on `main`/`beta` | `manifest.json`, translations, `services.yaml`, `quality_scale.yaml` |
| `hacs/action` | `home-assistant.yaml`, on `main`/`beta` | HACS compatibility |
| CodeQL | `codeql.yaml`, weekly | Python security analysis |

hassfest does not run on `dev`. When a change touches `manifest.json`, `services.yaml`, `icons.json` or a translation file, check the structure by hand against an existing integration.

---

## 7. Commit, PR, and Pre-commit Gate

See `AGENTS.md` → Commits for the format, and `git-conventions` for the gate and the PR workflow.

---

## 8. HA Code Review Checklist

Use with the `ha-review` skill.

### 8.1 Home Assistant patterns

- `async`/`await` for all I/O; no blocking calls in async context
- `_LOGGER = logging.getLogger(__name__)`; no `print()`
- `DiagralEntity` as base class; `DiagralConfigEntry` instead of `ConfigEntry`
- `@callback` on `_handle_coordinator_update` and dispatcher handlers
- Constants from `const.py`

### 8.2 Entity conventions

- `unique_id` per §3.3, `key` unchanged for existing entities
- `translation_key` on the description, present in `en.json` and `fr.json`
- `exists_fn` when the entity is conditional

### 8.3 Security

- No credential, API key, secret key, PIN, webhook id or URL in a log line at any level, in an event payload or in diagnostics
- No direct Diagral API call — through `pydiagral` only
- Webhook input is external and untrusted: parse it through `WebHookNotification.from_dict`, and tolerate missing fields

### 8.4 Webhook safety

- A change to `register_webhook` / `unregister_webhook` can break event delivery for another Home Assistant sharing the central. Check what happens when the existing subscription points elsewhere.

### 8.5 Error handling

- `DiagralAPIError` caught at the right level: `UpdateFailed` in the coordinator, `ConfigEntryNotReady` in setup
- No silent `except: pass`

### 8.6 Test coverage

Report what is not tested in `tests/test_<module>.py`: public methods, error paths, edge cases.

---

## 9. Investigating HA Behavior Changes

**Trigger:** the user says a behaviour changed with a given HA version. Investigate **before** modifying integration code.

### Step 1 — Identify suspect HA files

- `homeassistant/components/alarm_control_panel/` — alarm panel contract
- `homeassistant/components/webhook/`, `homeassistant/components/cloud/` — webhook and cloudhook
- `homeassistant/helpers/network.py` — `get_url`
- `homeassistant/helpers/entity.py`, `entity_registry.py`, `update_coordinator.py`

### Step 2 — Git history in the devcontainer

A Home Assistant core devcontainer **is** a git checkout of core. Run these from its workspace root (inside the container, or on the host where it is cloned):

```bash
git log --oneline --follow -- homeassistant/components/alarm_control_panel/__init__.py
git log --oneline 2026.3.0..2026.4.0 -- <file>
git show <sha>
```

### Step 3 — GitHub CLI

```bash
gh api repos/home-assistant/core/commits -X GET -f path=homeassistant/components/alarm_control_panel/__init__.py
gh search code 'AlarmControlPanelState repo:home-assistant/core'
gh search issues 'alarm_control_panel breaking change' --repo home-assistant/core
gh pr list --repo home-assistant/core --search 'alarm_control_panel' --state merged
```

A merged upstream PR body usually states the intent and whether a breaking change was declared — often faster than the diff.

### Step 4 — Release notes

Confirm with [home-assistant.io/blog](https://www.home-assistant.io/blog/) — **Breaking changes** and **Deprecations** sections.

### Step 5 — Adapt

Update the code, adjust tests that encoded the old behaviour, run the suite, commit with a `Tests:` line.

---

## 10. Home Assistant Expectations

These apply to any integration and come from upstream review practice.

### 10.1 Configuration

- **Polling intervals are not user-configurable.** `DEFAULT_SCAN_INTERVAL` in `const.py` is the single source.
- **Do not let users name the config entry.** The title is derived from the alarm name and serial.

### 10.2 Entities

- `async_added_to_hass()` subscriptions are torn down symmetrically — `self.async_on_remove(...)`.
- Do not redeclare what the base class already provides, and do not guard against the parent's behaviour changing.

### 10.3 Validation and defensive code

- Do not re-validate what a service schema or selector already validated. Guard only where data bypasses those validators — the webhook payload is the main such input here.
- Where validation guarantees a key exists, index it directly rather than `.get()`, so a contract violation surfaces.

### 10.4 Libraries

Do not work around a `pydiagral` bug or gap in the integration — fix `pydiagral` (same maintainer), release it, then bump the pin in `manifest.json`. When Home Assistant changes behaviour, adapt to the new contract after investigating it (§9).

### 10.5 Diagnostics and repairs

- `diagnostics.py` must never expose credentials, keys, the PIN or the webhook id. Extend `TO_REDACT` whenever a new secret enters the payload.
- `repairs.py` holds the fix flows of the webhook issues (§2.3): `webhook_owned_elsewhere` (take over) and `webhook_registration_failed` (retry, without taking over). `webhook_no_url` is not fixable: its description says what to configure. Every issue must stay actionable: what is happening, why it matters, the exact steps to resolve it — in both `en.json` and `fr.json`, under `issues`. Scope issue ids per config entry.

### 10.6 Finding examples

Prefer core integrations with a `platinum` or `gold` quality scale when looking for a pattern.

### 10.7 Tests

Test observable behaviour — entity states, published events, service calls, config entry state — rather than internals.

---

## 11. Deliberate Deviations and Known Context

### 11.1 Webhook management lives in the integration

Registering the central's webhook, choosing between a cloudhook and the external URL, and exposing `register_webhook` / `unregister_webhook` as entity services is integration logic, not a library concern. Do not propose moving it into `pydiagral`.

### 11.2 `quality_scale.yaml` is a declaration, not a verified fact

`manifest.json` declares `bronze` and `quality_scale.yaml` lists statuses up to platinum. Several were set without an audit, and some contradict the code (for instance `diagnostics: todo` while `diagnostics.py` exists, `test-coverage` commented "all tests missing" while a suite exists). hassfest does not enforce the file for custom integrations. Treat each status as unverified until checked with `ha-quality-scale-verify`.
