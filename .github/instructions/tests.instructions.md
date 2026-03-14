---
applyTo: "tests/**"
description: "Use when writing, updating, or reviewing tests for the hass-diagral integration. Covers pytest setup, Home Assistant mock patterns, config entry helpers, and test structure conventions."
---

# Test Writing Guidelines — hass-diagral

## Directory Structure

Tests live **inside** the integration folder, which is the only directory mounted into the HA devcontainer:

```
custom_components/diagral/
├── pyproject.toml       # pytest config (pythonpath, asyncio_mode, filterwarnings)
└── tests/
    ├── __init__.py      # Empty, marks as package
    ├── conftest.py      # Shared fixtures (mock_hass, coordinator_mock, etc.)
    ├── test_const.py    # Tier 1: pure constant tests (no HA dependency)
    ├── test_config_flow_validation.py
    ├── test_sensor.py
    ├── test_alarm_control_panel.py
    └── test_webhook.py
```

Create `tests/__init__.py` and `tests/conftest.py` when writing the first test.

## Test Tiers

| Tier | What | HA dependency | Where to run |
|------|------|--------------|------------|
| Tier 1 | Pure constants (`const.py`) loaded via `importlib` | None | Local or Docker |
| Tier 2 | Any file that imports HA (sensor, alarm_control_panel, config_flow…) | Yes | Docker devcontainer only |

For **Tier 1 tests**, load `const.py` directly to bypass the package `__init__.py` which imports HA:

## Running Tests

Before running tests, detect the execution environment automatically:

### Step 1 — Detect if running inside the devcontainer

Check for the presence of the `/workspaces` directory **or** the `REMOTE_CONTAINERS` / `CODESPACES` environment variables:

```bash
# Quick check
test -d /workspaces && echo "inside devcontainer" || echo "outside devcontainer"
```

**If inside the devcontainer**, run pytest directly from the integration working directory:

```bash
cd /workspaces/home-assistant-dev/config/custom_components/diagral
pytest tests/ -v
```

### Step 2 — If NOT inside the devcontainer

List running Docker containers and present the result to the developer:

```bash
docker ps --format "table {{.ID}}\t{{.Image}}\t{{.Names}}"
```

Present the output to the developer and ask:
> "Which container ID should I use to run the tests?"

**If no container is running**, inform the developer:
> "No running container found. Please start the HA devcontainer first, then provide the container ID."

### Step 3 — Once the container ID is known

```bash
docker exec -w /workspaces/home-assistant-dev/config/custom_components/diagral <CONTAINER_ID> pytest tests/ -v
```

Replace `<CONTAINER_ID>` with the value provided by the developer (e.g., `f5ea139decbd`).

> **Note:** The container ID changes every time the devcontainer is restarted. Always retrieve it fresh via `docker ps`.
```python
import importlib.util, pathlib
spec = importlib.util.spec_from_file_location(
    "diagral_const",
    pathlib.Path(__file__).parent.parent / "const.py",  # tests/ -> diagral/ -> const.py
)
const = importlib.util.module_from_spec(spec)
spec.loader.exec_module(const)
```

## Dependencies

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

`pythonpath = ["../.."` adds `/workspaces/home-assistant-dev/config` to sys.path so that `from custom_components.diagral.xxx import ...` resolves correctly.

## conftest.py Bootstrap

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

## Mocking Strategy

- Use `MagicMock(spec=HomeAssistant)` for the HA instance
- **Never make real HTTP calls** — always mock at the `pydiagral` library boundary
- Mock `pydiagral` API objects using `unittest.mock.MagicMock` / `AsyncMock`
- Patch module-level utilities: `@patch("custom_components.diagral.sensor.dt_util")`
- Use `DeviceList(cameras=[], commands=[], sensors=[], sirens=[], transmitters=[])` (not `MagicMock()`) when `vars(devices_infos)` is iterated in the code under test — `MagicMock().__dict__` contains non-iterable sentinel objects that cause `TypeError`

## Key Rules

- **Never make real HTTP calls** — always mock at the `pydiagral` library boundary
- Test both the happy path and error handling (API exceptions, missing/invalid data)
- Use `asyncio_mode = "auto"` (configured in `pyproject.toml`) — no `@pytest.mark.asyncio` needed
- Assert on entity states, attributes, and unique IDs

## Test Impact Analysis

**Every time a file in `custom_components/diagral/*.py` is created or modified**, you MUST perform the following analysis before finishing the task:

1. **Identify** the corresponding test file: `tests/test_<module>.py`
   (e.g., modifying `sensor.py` → check `tests/test_sensor.py`)
2. **Read** the existing tests in that file (if it exists)
3. **For each function or class that was added, changed, or removed**, decide:
   - `CREATE` — new behaviour needs a new test
   - `UPDATE` — existing test no longer reflects the new logic
   - `DELETE` — function was removed and its test is now dead code
4. **Apply** all required test changes immediately — never skip silently
5. **Run** the test suite (see [Running Tests](#running-tests)) to validate no regression

> This rule applies to ALL code changes: features, bug fixes, refactors, and deletions.
> If the test file does not exist yet, create it with the standard `tests/__init__.py` + `conftest.py` bootstrap.

## Test Naming Convention

```
test_<module>_<scenario>
```

Examples:
- `test_sensor_anomalies_returns_count`
- `test_coordinator_update_retains_data_on_api_error`
- `test_alarm_panel_arm_away_calls_api`

## Running Tests

```bash
# All tests (from the integration directory in the container):
docker exec -w /workspaces/home-assistant-dev/config/custom_components/diagral <container_id> pytest tests/ -v

# Single file:
docker exec -w /workspaces/home-assistant-dev/config/custom_components/diagral <container_id> pytest tests/test_sensor.py -v
```
