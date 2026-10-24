"""Sensors must render the first successful snapshot immediately after setup."""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import Mock, patch

from custom_components.diagral.sensor import SENSORS, DiagralSensor, async_setup_entry
from pydiagral.models import Anomalies, AnomalyDetail, AnomalyName, DeviceList


def initial_context():
    """Use complete cloud model data and no HA server or network operations."""
    observed = datetime(2026, 10, 22, 10, 0, tzinfo=UTC)
    config = SimpleNamespace(
        alarm=SimpleNamespace(central=SimpleNamespace(serial="fake-serial")),
        presence_group=[1],
    )
    coordinator = SimpleNamespace(
        data={
            "alarm_config": config,
            "groups": [
                SimpleNamespace(index=1, name="Entry"),
                SimpleNamespace(index=2, name="Upstairs"),
            ],
            "system_status": SimpleNamespace(status="GROUP", activated_groups=[1, 2]),
            "anomalies": Anomalies(
                created_at=observed,
                sensors=[
                    AnomalyDetail(anomaly_names=[AnomalyName(id=1, name="Battery")])
                ],
            ),
            "devices_infos": DeviceList(
                cameras=[], commands=[], sensors=[], sirens=[], transmitters=[]
            ),
        },
        last_update_success=True,
        communication_status="connected",
        last_success=observed,
    )
    entry = SimpleNamespace(
        entry_id="test-entry",
        data={},
        runtime_data=SimpleNamespace(
            coordinator=coordinator,
            webhook_status="pending",
            webhook_last_received=None,
        ),
    )
    return coordinator, entry


def test_constructor_initializes_sensor_without_state_write():
    """Populate initial values before the entity can write a Home Assistant state."""
    coordinator, entry = initial_context()
    with patch.object(DiagralSensor, "async_write_ha_state") as state_write:
        sensors = [
            DiagralSensor(coordinator, description, entry) for description in SENSORS
        ]
    assert [sensor.native_value for sensor in sensors] == [1, 2]
    assert sensors[1].extra_state_attributes["groups"][0]["active"] is True
    state_write.assert_not_called()


async def test_setup_adds_six_sensors_with_initial_values():
    """All sensor values are ready for HA's first state write."""
    _, entry = initial_context()
    entities = []
    await async_setup_entry(None, entry, entities.extend)
    values = {entity.entity_description.key: entity.native_value for entity in entities}
    assert values == {
        "anomalies": 1,
        "active_groups": 2,
        "cloud_connection": "connected",
        "last_success": entry.runtime_data.coordinator.last_success,
        "webhook_status": "pending",
        "webhook_last_received": None,
    }


def test_failed_poll_preserves_value_and_timestamp_but_updates_availability():
    """Publish unavailability without assigning a new timestamp to stale data."""
    coordinator, entry = initial_context()
    sensor = DiagralSensor(coordinator, SENSORS[1], entry)
    previous_attributes = dict(sensor.extra_state_attributes)
    coordinator.last_update_success = False
    sensor.async_write_ha_state = Mock()
    with patch.object(sensor, "_update_value_from_coordinator") as calculate:
        sensor._handle_coordinator_update()
    calculate.assert_not_called()
    sensor.async_write_ha_state.assert_called_once()
    assert sensor.available is False
    assert sensor.native_value == 2
    assert sensor.extra_state_attributes == previous_attributes
