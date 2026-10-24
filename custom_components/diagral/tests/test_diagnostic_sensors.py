"""Keep operational health readable when the cloud is unavailable."""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

from custom_components.diagral import async_migrate_entry
from custom_components.diagral.const import CONFIG_MINOR_VERSION, CONFIG_VERSION
from custom_components.diagral.sensor import DIAGNOSTIC_SENSORS, DiagralDiagnosticSensor
import pytest


def test_diagnostic_values_remain_available_during_outage():
    """Expose cloud and webhook health even when alarm data is unavailable."""
    last_success = datetime(2026, 10, 22, tzinfo=UTC)
    coordinator = MagicMock()
    coordinator.data = {}
    coordinator.last_update_success = False
    coordinator.communication_status = "unavailable"
    coordinator.last_success = last_success
    coordinator.consecutive_failures = 2
    coordinator.last_error = "timeout"
    entry = SimpleNamespace(
        entry_id="test-entry",
        runtime_data=SimpleNamespace(
            webhook_status="retrying",
            webhook_last_received=None,
            webhook_retry_attempts=2,
            webhook_last_error="ServerError",
        ),
    )
    sensors = {
        item.key: DiagralDiagnosticSensor(coordinator, item, entry)
        for item in DIAGNOSTIC_SENSORS
    }
    assert all(sensor.available for sensor in sensors.values())
    assert sensors["cloud_connection"].native_value == "unavailable"
    assert sensors["cloud_connection"].extra_state_attributes == {
        "consecutive_failures": 2,
        "last_error": "timeout",
    }
    assert sensors["last_success"].native_value == last_success
    assert sensors["webhook_status"].native_value == "retrying"
    assert sensors["webhook_last_received"].native_value is None
    assert len({sensor.unique_id for sensor in sensors.values()}) == 4


@pytest.mark.asyncio
@pytest.mark.parametrize("version,minor,pin", [(1, 1, 1234), (1, 3, "001234")])
async def test_migrate_old_entries_to_current_version(version, minor, pin):
    """Upgrade old entry versions while preserving any stored PIN zeros."""
    hass = MagicMock()
    entry = SimpleNamespace(
        version=version, minor_version=minor, data={"pin_code": pin}
    )
    assert await async_migrate_entry(hass, entry)
    hass.config_entries.async_update_entry.assert_called_once_with(
        entry,
        data={"pin_code": str(pin)},
        version=CONFIG_VERSION,
        minor_version=CONFIG_MINOR_VERSION,
    )


@pytest.mark.asyncio
async def test_current_entry_needs_no_migration():
    """Leave entries at the current config version unchanged."""
    hass = MagicMock()
    entry = SimpleNamespace(version=CONFIG_VERSION, minor_version=CONFIG_MINOR_VERSION)
    assert await async_migrate_entry(hass, entry)
    hass.config_entries.async_update_entry.assert_not_called()
