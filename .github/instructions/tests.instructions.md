---
applyTo: "tests/**"
description: "Use when writing, updating, or reviewing tests for the hass-diagral integration. Covers pytest setup, Home Assistant mock patterns, config entry helpers, and test structure conventions."
---

# Test Writing Guidelines — hass-diagral

## Directory Structure

```
tests/
├── __init__.py         # Empty, marks as package
├── conftest.py         # Shared fixtures (mock_hass, coordinator_mock, etc.)
├── test_const.py       # Tier 1: pure constant tests (no HA dependency)
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
```python
import importlib.util, pathlib
spec = importlib.util.spec_from_file_location(
    "diagral_const",
    pathlib.Path(__file__).parent.parent / "custom_components/diagral/const.py",
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

pytest is configured via `pyproject.toml`:
```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
pythonpath = ["."]
testpaths = ["tests"]
```

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
- Use `SimpleNamespace` (not `MagicMock`) when attribute assignment is needed:
  ```python
  from types import SimpleNamespace
  detail = SimpleNamespace(device_type="detector", device_index="1", device_label=None)
  ```

## Key Rules

- **Never make real HTTP calls** — always mock at the `pydiagral` library boundary
- Test both the happy path and error handling (API exceptions, missing/invalid data)
- Use `asyncio_mode = "auto"` (configured in `pyproject.toml`) — no `@pytest.mark.asyncio` needed
- Assert on entity states, attributes, and unique IDs

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
# In Docker devcontainer (required for Tier 2 tests):
docker exec -w /workspaces/hass-diagral <container_id> pytest tests/ -v

# Single file:
docker exec -w /workspaces/hass-diagral <container_id> pytest tests/test_sensor.py -v
```
