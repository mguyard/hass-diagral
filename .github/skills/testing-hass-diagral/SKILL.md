---
name: testing-hass-diagral
description: Project-specific test setup for hass-diagral — directory structure, test tiers, devcontainer/docker environment detection, running pytest, and shared fixtures.
user-invocable: false
---

# Testing — hass-diagral Project Setup

Use this skill for any task that requires running, writing, or understanding tests in the `custom_components/diagral/` codebase.

For generic testing principles (behavior-based, determinism, unit vs integration strategy), see `../testing-qa/SKILL.md`.

---

## 1. Directory Structure

Tests live **inside** the integration folder, which is the only directory mounted into the HA devcontainer:

```
custom_components/diagral/
├── pyproject.toml       # pytest config (asyncio_mode=auto, pythonpath=["../.."])
└── tests/
    ├── __init__.py      # Empty, marks as package
    ├── conftest.py      # Shared fixtures
    ├── test_const.py
    ├── test_config_flow_validation.py
    ├── test_sensor.py
    ├── test_alarm_control_panel.py
    └── test_webhook.py
```

Create `tests/__init__.py` and `tests/conftest.py` when writing the first test.

---

## 2. Test Tiers

| Tier | Scope | HA dependency | Run where |
|------|-------|--------------|-----------|
| Tier 1 | Pure constants (`const.py` via `importlib`) | None | Anywhere |
| Tier 2 | Files that import HA (sensor, alarm_control_panel…) | Yes | Devcontainer only |

For Tier 1, load `const.py` directly to bypass `__init__.py` (which imports HA):
```python
import importlib.util, pathlib
spec = importlib.util.spec_from_file_location(
    "diagral_const",
    pathlib.Path(__file__).parent.parent / "const.py",  # tests/ -> diagral/ -> const.py
)
const = importlib.util.module_from_spec(spec)
spec.loader.exec_module(const)
```

---

## 3. Running Tests

**Step 1 — Detect environment:**
```bash
test -d /workspaces && echo "inside devcontainer" || echo "outside devcontainer"
```

**Step 2a — Inside devcontainer:**
```bash
cd /workspaces/home-assistant-dev/config/custom_components/diagral
pytest tests/ -v
```

**Step 2b — Outside devcontainer** (get container ID first):
```bash
docker ps --format "table {{.ID}}\t{{.Image}}\t{{.Names}}"
```

Present the output and ask the developer which container ID to use. Then:
```bash
docker exec -w /workspaces/home-assistant-dev/config/custom_components/diagral <CONTAINER_ID> pytest tests/ -v
```

> The container ID changes every time the devcontainer is restarted — always retrieve it fresh via `docker ps`.

> **This section is the canonical source for running tests.** `git-conventions/SKILL.md §3` (pre-commit gate) references this section — do not duplicate the commands elsewhere.

---

## 4. Dependencies and pytest Configuration

`homeassistant` is installed as a regular pip package in the devcontainer.
**No `pytest-homeassistant-custom-component` is required.**

Test dependencies (`requirements_test.txt`):
```
pytest
pytest-asyncio
pytest-mock
```

pytest is configured via `custom_components/diagral/pyproject.toml`:
```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
pythonpath = ["../.."]
testpaths = ["tests"]
filterwarnings = [
    "ignore:Setting custom ClientSession.close attribute is discouraged:DeprecationWarning:homeassistant.helpers.aiohttp_client",
    "ignore:Unclosed client session:ResourceWarning",
]
```

`asyncio_mode = "auto"` means **no `@pytest.mark.asyncio` decorator is needed** on async tests.
`pythonpath = ["../.."]` adds `/workspaces/home-assistant-dev/config` to `sys.path` so `from custom_components.diagral.xxx import ...` resolves correctly.

---

## 5. Shared Fixtures (conftest.py)

Full bootstrap:

```python
"""Shared test fixtures for hass-diagral."""
import pytest
from unittest.mock import MagicMock
from homeassistant.core import HomeAssistant


@pytest.fixture
def mock_hass():
    """Return a mock Home Assistant instance."""
    return MagicMock(spec=HomeAssistant)


@pytest.fixture
def alarm_config_mock():
    """Return a mock AlarmConfiguration."""
    mock = MagicMock()
    mock.alarm.central.serial = "SERIAL123"
    return mock


@pytest.fixture
def system_status_mock():
    """Return a mock SystemStatus in disarmed state."""
    mock = MagicMock()
    mock.status = "off"
    return mock


@pytest.fixture
def coordinator_mock(alarm_config_mock, system_status_mock):
    """Return a fully populated coordinator mock."""
    mock = MagicMock()
    mock.data = {
        "alarm_config": alarm_config_mock,
        "system_status": system_status_mock,
        "anomalies": None,
        "groups": [],
        "devices_infos": MagicMock(),
    }
    return mock


@pytest.fixture
def diagral_config():
    """Return a mock DiagralConfigData with default options."""
    from custom_components.diagral.const import (
        CONF_ALARMPANEL_ACTIONTYPE_CODE,
        CONF_ALARMPANEL_CODE,
    )
    config = MagicMock()
    config.options.alarmpanel_options = {
        CONF_ALARMPANEL_ACTIONTYPE_CODE: "never",
        CONF_ALARMPANEL_CODE: None,
    }
    return config
```

---

## 6. Mocking Strategy

- Use `MagicMock(spec=HomeAssistant)` for the HA instance
- **Never make real HTTP calls** — always mock at the `pydiagral` library boundary
- Mock `pydiagral` API objects using `unittest.mock.MagicMock` / `AsyncMock`
- Patch module-level utilities: `@patch("custom_components.diagral.sensor.dt_util")`
- Use `DeviceList(cameras=[], commands=[], sensors=[], sirens=[], transmitters=[])` (not `MagicMock()`) when `vars(devices_infos)` is iterated in the code under test — `MagicMock().__dict__` contains non-iterable sentinel objects that cause `TypeError`

---

## 7. Test Impact Analysis (Mandatory)

Every time a file in `custom_components/diagral/*.py` is created or modified, perform this analysis **before finishing the task**:

1. **Identify** the corresponding test file: `tests/test_<module>.py`
2. **Read** the existing tests in that file (if it exists)
3. **For each function or class that was added, changed, or removed**, decide:
   - `CREATE` — new behaviour needs a new test
   - `UPDATE` — existing test no longer reflects the new logic
   - `DELETE` — function was removed and its test is now dead code
4. **Apply** all required test changes immediately — never skip silently
5. **Run** the test suite (§3) to validate no regression

> This rule applies to ALL code changes: features, bug fixes, refactors, and deletions.
> If the test file does not exist yet, create it with the standard `__init__.py` + `conftest.py` bootstrap.

---

## 8. Test Rules and Naming

- Minimum coverage per entity: `unique_id` format, entity state value, `exists_fn` if defined, coordinator error path
- Test both happy path and error handling (API exceptions, missing/invalid data)
- Assert on entity states, attributes, and unique IDs
- Run `flake8 --max-line-length=150 custom_components/diagral/` after changes

**Naming convention:** `test_<module>_<scenario>`

Examples:
- `test_sensor_anomalies_returns_count`
- `test_coordinator_update_retains_data_on_api_error`
- `test_alarm_panel_arm_away_calls_api`
