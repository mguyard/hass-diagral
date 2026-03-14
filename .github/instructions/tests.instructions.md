---
applyTo: "tests/**"
description: "Use when writing, updating, or reviewing tests for the hass-diagral integration. Covers pytest setup, Home Assistant mock patterns, config entry helpers, and test structure conventions."
---

# Test Writing Guidelines — hass-diagral

## Directory Structure

```
tests/
├── __init__.py         # Empty, marks as package
├── conftest.py         # Shared fixtures (MockConfigEntry, mock coordinator)
├── test_sensor.py
├── test_alarm_control_panel.py
├── test_coordinator.py
└── test_webhook.py
```

Create `tests/__init__.py` and `tests/conftest.py` when writing the first test.

## Dependencies

Use `pytest-homeassistant-custom-component` for Home Assistant fixtures.

```bash
pip install pytest-homeassistant-custom-component
```

## conftest.py Bootstrap

```python
"""Shared test fixtures for hass-diagral."""
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.diagral.const import DOMAIN


@pytest.fixture
def mock_config_entry():
    """Return a mock config entry."""
    return MockConfigEntry(
        domain=DOMAIN,
        data={
            "username": "test@example.com",
            "password": "testpassword",
            "serial_id": "DIAG123456",
            "pin_code": "1234",
        },
        entry_id="test_entry_id",
    )
```

## Mocking the Coordinator

Patch `_async_update_data` to avoid real `pydiagral` API calls:

```python
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture
def mock_coordinator_data():
    """Return fake coordinator data matching the expected schema."""
    alarm_config = MagicMock()
    alarm_config.alarm.central.serial = "SERIAL123"
    return {
        "alarm_config": alarm_config,
        "system_status": MagicMock(),
        "anomalies": MagicMock(),
        "groups": [],
        "devices_infos": MagicMock(),
    }


@pytest.fixture
def patch_coordinator(mock_coordinator_data):
    with patch(
        "custom_components.diagral.coordinator.DiagralDataUpdateCoordinator._async_update_data",
        new_callable=AsyncMock,
        return_value=mock_coordinator_data,
    ):
        yield
```

## Key Rules

- **Never make real HTTP calls** — always mock at the `pydiagral` library boundary
- Mock `pydiagral` API objects using `unittest.mock.MagicMock` / `AsyncMock`
- Test both the happy path and error handling (API exceptions, missing/invalid data)
- Use `@pytest.mark.asyncio` for async test functions (or configure `asyncio_mode = "auto"`)
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
pytest tests/
```
