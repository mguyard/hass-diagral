---
name: python-homeassistant
description: Architecture, entity patterns, testing, and conventions for the hass-diagral Home Assistant custom integration.
user-invocable: false
---

# Skill: Python — Home Assistant Integration (hass-diagral)

Use this skill for any implementation, review, or debugging task in the `custom_components/diagral/` codebase.

---

## 1. Project Stack

- **Language**: Python 3.12+, `async`/`await` everywhere for I/O
- **Framework**: Home Assistant custom component (no frontend, no database)
- **External library**: `pydiagral` (pinned in `manifest.json`) — all Diagral API calls go through this library exclusively
  - Documentation: [https://mguyard.github.io/pydiagral/](https://mguyard.github.io/pydiagral/)
  - Always query via **Context7** or a web search on the URL above before using any pydiagral class, method, or model — do not assume the API is stable
- **Linter**: `flake8 --max-line-length=150`
- **Tests**: `pytest` with `asyncio_mode = "auto"` (see `pyproject.toml`)

---

## 2. Module Map

```
custom_components/diagral/
├── __init__.py              # Entry setup/teardown, webhook registration, DiagralConfigEntry alias
├── coordinator.py           # DiagralDataUpdateCoordinator — polls every 300 s
├── models.py                # DiagralData, DiagralConfigData, DiagralOptionsData
├── const.py                 # All constants (DOMAIN, service names, config keys)
├── config_flow.py           # UI config flow + options flow
├── entity.py                # DiagralEntity base class (extends CoordinatorEntity)
├── alarm_control_panel.py   # AlarmControlPanel platform
├── sensor.py                # Sensor platform
├── webhook.py               # Webhook handler (push updates from Diagral cloud)
├── diagnostics.py           # HA diagnostics endpoint
├── services.yaml            # Custom service definitions
├── manifest.json            # Integration metadata (pydiagral version pinned)
└── translations/            # en.json, fr.json — all entity human names
```

---

## 3. Key Patterns and Invariants

### 3.1 Typed Config Entry

Always use `DiagralConfigEntry` (defined in `__init__.py`) instead of raw `ConfigEntry`:

```python
from . import DiagralConfigEntry
# NOT: from homeassistant.config_entries import ConfigEntry
```

`DiagralConfigEntry = ConfigEntry[DiagralData]`

### 3.2 Runtime Data Access

```python
coordinator: DiagralDataUpdateCoordinator = entry.runtime_data.coordinator
api: DiagralAPI = entry.runtime_data.api
config: DiagralConfigData = entry.runtime_data.config
webhook_id: str = entry.runtime_data.webhook_id
```

### 3.3 Coordinator Data Keys

```python
coordinator.data["alarm_config"]    # AlarmConfiguration
coordinator.data["devices_infos"]   # DeviceInfos
coordinator.data["groups"]          # list[Group]
coordinator.data["system_status"]   # SystemStatus
coordinator.data["anomalies"]       # Anomalies
```

Access with `.get()` and safe fallbacks when the key may be absent:
```python
status: SystemStatus = coordinator.data.get("system_status")
```

### 3.4 Entity Base Class

All entities extend `DiagralEntity`:

```python
from .entity import DiagralEntity

class DiagralMySensor(DiagralEntity, SensorEntity):
    pass
```

`DiagralEntity` already sets `_attr_has_entity_name = True` and provides `device_info`.

### 3.5 EntityDescription Pattern

```python
@dataclass(frozen=True)
class DiagralSensorEntityDescription(SensorEntityDescription):
    exists_fn: Callable[..., bool] = lambda _: True
```

### 3.6 unique_id Pattern

```python
self._attr_unique_id = (
    f"{config_entry.entry_id}_{DOMAIN}"
    f"_{coordinator.data['alarm_config'].alarm.central.serial}"
    f"_{description.key}"
)
```

### 3.7 Translation Keys

Every entity needs `translation_key` on the description. Add the key to **both** `translations/en.json` and `translations/fr.json`:

```json
"entity": {
    "sensor": {
        "my_key": { "name": "Human Readable Name" }
    }
}
```

### 3.8 Webhook Pattern

- Webhook supports **Nabu Casa cloud** (`.nabu.casa` domain) and direct HA webhook
- `HA_CLOUD_DOMAIN = ".nabu.casa"` constant used for detection
- Webhook data is parsed via `pydiagral.models.WebHookNotification.from_dict()`
- Push update triggers `coordinator.async_request_refresh()`

### 3.9 API Error Handling

```python
from pydiagral.exceptions import DiagralAPIError

try:
    await api.some_call()
except DiagralAPIError as err:
    raise UpdateFailed(f"Error communicating with API: {err}") from err
```

Never call the Diagral API directly — always go through `pydiagral`.

### 3.10 Async Rules

- All I/O must use `async`/`await`
- Use `@callback` decorator on `_handle_coordinator_update`
- Never use blocking calls (no `time.sleep`, no synchronous HTTP) in async context
- Use `_LOGGER = logging.getLogger(__name__)` — never `print()`

---

## 4. Testing

See `../testing-hass-diagral/SKILL.md` for the full project-specific test setup:
- Directory structure and test file map
- Tier 1 (pure constants, runs anywhere) vs Tier 2 (HA dependency, devcontainer only)
- Environment detection and `pytest` run commands (devcontainer / `docker exec`)
- Shared fixtures from `conftest.py`
- Test rules: what to test per entity, flake8 gate

For generic testing principles, see `../testing-qa/SKILL.md`.

---

## 5. New Entity — Full Guide

### 5.1 Required Information (clarify before implementing)

If any of the following is unclear, gather the information via `vscode_askQuestions` before starting implementation.

1. **Entity type** — `sensor`, `binary_sensor`, or `alarm_control_panel`
2. **Key** — snake_case, unique within the platform (e.g. `battery_level`)
3. **What it represents** — what data or state does it expose?
4. **Unit of measurement** — if sensor (e.g. `%`, `°C`); omit for binary or alarm
5. **Conditional** — does it require specific coordinator data to exist? If yes, define `exists_fn`

### 5.2 Implementation Steps (all required, in one pass)

1. `@dataclass(frozen=True)` EntityDescription subclass with `exists_fn`
2. `unique_id` following the `{entry_id}_{DOMAIN}_{serial}_{key}` pattern
3. `translation_key` added to both `en.json` and `fr.json`
4. Row added to `docs/integration/entities.mdx`
5. Tests in `tests/test_<platform>.py` — at minimum: `unique_id` format, entity state, `exists_fn` if defined
6. Commit message: `feat(<platform>): ✨ Add <entity_name> entity`

### 5.3 EntityDescription Pattern (full example)

```python
@dataclass(frozen=True)
class DiagralSensorEntityDescription(SensorEntityDescription):
    """Sensor entity description for Diagral."""

    exists_fn: Callable[..., bool] = lambda _: True


SENSORS: tuple[DiagralSensorEntityDescription, ...] = (
    DiagralSensorEntityDescription(
        key="my_sensor",              # snake_case, unique within the platform
        translation_key="my_sensor",  # must match the key in en.json / fr.json
        icon="mdi:...",
        native_unit_of_measurement="unit",
        # exists_fn=lambda coordinator: coordinator.some_condition,
    ),
)
```

### 5.4 Entity Class and `async_setup_entry`

```python
class DiagralMySensor(DiagralEntity, SensorEntity):
    def __init__(
        self,
        coordinator: DiagralDataUpdateCoordinator,
        description: DiagralSensorEntityDescription,
        config_entry: DiagralConfigEntry,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._entry_id = config_entry.entry_id
        self._alarm_config = coordinator.data.get("alarm_config", {})
        self._attr_unique_id = (
            f"{self._entry_id}_{DOMAIN}"
            f"_{self._alarm_config.alarm.central.serial}"
            f"_{description.key}"
        )


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DiagralConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data.coordinator
    async_add_entities(
        DiagralMySensor(coordinator, description, entry)
        for description in SENSORS
        if description.exists_fn(coordinator)
    )
```

### 5.5 Coordinator Data Keys

| Key | Type | Description |
|-----|------|-------------|
| `alarm_config` | `AlarmConfiguration` | Full alarm configuration |
| `system_status` | `SystemStatus` | Current system status |
| `anomalies` | `Anomalies` | Current anomalies list |
| `groups` | `list[Group]` | Active arming groups |
| `devices_infos` | `DeviceInfos` | All registered devices |

### 5.6 Translation Format

Add under `entity.<platform>.<translation_key>` in **both** `translations/en.json` and `translations/fr.json`:

```json
"entity": {
    "sensor": {
        "my_sensor": {
            "name": "Human Readable Name"
        }
    }
}
```

### 5.7 Documentation Review on Every Code Change

Whenever a feature, service, entity, or behavior is **added or modified**, apply this process before considering the task complete:

1. **Read the relevant `docs/` pages** — scan `docs/integration/` to identify pages that cover the area being changed (entities, actions, events, webhook, setup, etc.).
2. **Identify what needs documenting** — new behavior, changed defaults, added options, new entities, removed capabilities, updated configuration steps, etc.
3. **Preserve the existing style** — match the tone, structure, table format, and MDX components already used on the target page. Do not introduce new formatting patterns.
4. **When in doubt, ask the developer** — if it is unclear whether a change warrants a documentation update, ask via `vscode_askQuestions` (mandatory — see global rule in `copilot-instructions.md`) before writing or skipping it:

   > "Should I update the documentation for this change? If yes, which page(s)?"

---

## 6. CI Checks (non-local)

| Check | Tool | What it validates |
|-------|------|-------------------|
| `hassfest` | GitHub Actions | `manifest.json`, translations, `quality_scale.yaml` |
| `hacs/action` | GitHub Actions | HACS compatibility |
| `CodeQL` | GitHub Actions | Python security analysis |

---

## 7. Commit, PR, and Pre-commit Gate

See `../git-conventions/SKILL.md` for the full rules:
- Commit message format (type, gitmoji, scope, `Tests:` line)
- Pre-commit test gate — mandatory before every commit
- PR title, description template, branch rules, and prepare-PR workflow

---

## 8. HA Code Review Checklist

Use this checklist when reviewing any file in `custom_components/diagral/`.

### 8.1 Flake8 Compliance

- Max line length: **150 characters** — flag any line exceeding this
- No unused imports, undefined names, or bare `except:` clauses
- Run: `flake8 --max-line-length=150 <file>`

### 8.2 Home Assistant Patterns

- `async`/`await` for all I/O-bound operations (no blocking calls in async context)
- `_LOGGER = logging.getLogger(__name__)` — no `print()` statements
- `CoordinatorEntity` / `DiagralEntity` as base class for entities
- `DiagralConfigEntry` used instead of raw `ConfigEntry`
- `entry.runtime_data.coordinator` to access the coordinator
- `@callback` decorator on `_handle_coordinator_update`
- Constants from `const.py` — no magic strings or numbers inline

### 8.3 Entity Conventions (when applicable)

- `_attr_unique_id` follows `{entry_id}_{DOMAIN}_{serial}_{key}` pattern
- `_attr_has_entity_name = True` is set (already in `DiagralEntity`)
- `translation_key` set on the `EntityDescription`
- `exists_fn` defined if the entity is conditional

### 8.4 Security

- No secrets or credentials logged
- No direct Diagral API calls (must go through `pydiagral`)
- No hardcoded URLs or tokens
- Webhook / external input not trusted without validation

### 8.5 Error Handling

- Exceptions caught at the appropriate level, logged with `_LOGGER.error` or `_LOGGER.warning`
- Coordinator data access uses `.get()` with safe fallbacks when a key may be absent
- No silent `except: pass` blocks

### 8.6 Test Coverage Assessment

Report what is **not yet tested** in `tests/test_<module>.py`:
- Untested public methods or properties
- Untested error paths
- Missing edge-case coverage

### 8.7 Review Output Format

```markdown
### Issues (must fix)
- `<file>:<line>` — description

### Suggestions (nice to have)
- description

### Test gaps
- description
```

---

## 9. Investigating HA Behavior Changes

**Trigger:** When the user mentions that a behavior changed since a specific HA version (e.g., "this worked in HA 2024.3 but broke in 2024.4"). Always perform this investigation **before** modifying integration code, to understand the root cause rather than patching symptoms.

### Step 1 — Identify suspect HA files

Based on the integration code that changed behavior, identify the HA modules likely involved. Common locations:

- `homeassistant/components/<platform>/` — platform base classes and contracts
- `homeassistant/helpers/entity.py`, `entity_registry.py` — entity lifecycle
- `homeassistant/components/alarm_control_panel/__init__.py` — alarm panel contract

### Step 2 — Analyze via Git (devcontainer)

The devcontainer contains a **git clone** of HA. Use it to inspect history directly.

**Step 2a — Detect environment and locate the HA repo:**
```bash
# Detect environment (see ../testing-hass-diagral/SKILL.md §3)
test -d /workspaces && echo "inside devcontainer" || echo "outside devcontainer"

# Find the HA git repository
find /workspaces -name ".git" -maxdepth 3 2>/dev/null
```

**Step 2b — Browse commit history on a suspected file:**
```bash
# List commits on a file (all history)
git -C <ha_repo_path> log --oneline --follow -- homeassistant/components/alarm_control_panel/__init__.py

# Restrict to a version range
git -C <ha_repo_path> log --oneline v2024.3.0..v2024.4.0 -- <file>

# See the full diff of a commit
git -C <ha_repo_path> show <commit_sha>
```

**Outside devcontainer:** retrieve the container ID first, then prefix with `docker exec <CONTAINER_ID>` (see `../testing-hass-diagral/SKILL.md §3`).

### Step 3 — Analyze via MCP GitHub

Use MCP GitHub tools to search history and context in `home-assistant/core` or `home-assistant/frontend`:

| Goal | Tool | Key parameters |
|------|------|----------------|
| Browse commits on a file | `mcp_github_list_commits` | `owner=home-assistant`, `repo=core`, `path=homeassistant/components/...` |
| Read a specific commit | `mcp_github_get_commit` | `sha` from the list above |
| Search code in HA | `mcp_github_search_code` | `query=MyClass repo:home-assistant/core` |
| Find related issues | `mcp_github_search_issues` | `query=breaking change alarm_control_panel 2024.4` |
| Find related PRs | `mcp_github_search_pull_requests` | `query=alarm_control_panel` in `home-assistant/core` |

Primary repos to check (not exclusively):
- `home-assistant/core` — Python backend, entities, platforms, helpers
- `home-assistant/frontend` — UI components (if the change is visual/frontend)

### Step 4 — Cross-reference with release notes

After finding relevant commits, confirm using HA release blog posts:
- `https://www.home-assistant.io/blog/` — release notes per version
- Look for **Breaking changes** or **Deprecations** sections mentioning the affected platform

### Step 5 — Adapt integration code

Once the HA change is fully understood:
1. Update affected files in `custom_components/diagral/`
2. Adjust tests that reflect the previous (now incorrect) behavior — see `../testing-hass-diagral/SKILL.md §7`
3. Run the test suite (see `../testing-hass-diagral/SKILL.md §3`)
4. Commit with scope and a `Tests:` line (see `../git-conventions/SKILL.md`)
