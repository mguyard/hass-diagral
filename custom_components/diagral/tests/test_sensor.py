"""Tests for pure logic methods of DiagralSensor (Tier 2).

Tests _update_anomalies() and _update_active_groups() without making
real API calls. dt_util is patched to avoid time-dependent output.
"""

from datetime import UTC, datetime
import json
import logging
import pathlib
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.diagral.const import WEBHOOK_STATUSES
from custom_components.diagral.sensor import (
    HEALTH_SENSORS,
    SENSORS,
    DiagralHealthSensor,
    DiagralSensor,
)
from pydiagral.models import Anomalies, AnomalyDetail, AnomalyName, DeviceList
import pytest

from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.const import EntityCategory
from homeassistant.helpers.update_coordinator import CoordinatorEntity

# An empty DeviceList with explicit empty lists to avoid iteration errors
# (vars(MagicMock()) would contain non-iterable sentinel objects)
EMPTY_DEVICE_LIST = DeviceList(
    cameras=[], commands=[], sensors=[], sirens=[], transmitters=[]
)


TRANSLATIONS = pathlib.Path(__file__).parent.parent / "translations"


def make_sensor_mock() -> DiagralSensor:
    """Return a DiagralSensor with mocked dependencies.

    Bypasses __init__ and sets the minimal attributes needed to test
    _update_anomalies() and _update_active_groups().
    """
    sensor = object.__new__(DiagralSensor)
    sensor._attr_native_value = None
    sensor._attr_extra_state_attributes = {}
    return sensor


class TestUpdateAnomalies:
    """Tests for _update_anomalies()."""

    def test_no_anomalies_sets_value_to_zero(self):
        """None anomalies must set native_value to 0 and clear attributes."""
        sensor = make_sensor_mock()
        sensor._update_anomalies(None, [], MagicMock())
        assert sensor._attr_native_value == 0
        assert sensor._attr_extra_state_attributes == {}

    def test_empty_anomalies_object_sets_value_to_zero(self):
        """Anomalies object with all None lists must count as 0."""
        sensor = make_sensor_mock()
        anomalies = Anomalies(created_at=datetime(2024, 1, 1, tzinfo=UTC))
        with patch("custom_components.diagral.sensor.dt_util") as mock_dt:
            mock_dt.as_local.return_value.isoformat.return_value = (
                "2024-01-01T00:00:00+00:00"
            )
            mock_dt.now.return_value.isoformat.return_value = "2024-01-01T00:00:00"
            sensor._update_anomalies(anomalies, [], EMPTY_DEVICE_LIST)
        assert sensor._attr_native_value == 0

    def test_anomalies_count_is_correct(self):
        """Anomalies with 2 sensors must set native_value to 2."""
        sensor = make_sensor_mock()
        anomaly1 = AnomalyDetail(anomaly_names=[AnomalyName(id=1, name="Low battery")])
        anomaly2 = AnomalyDetail(anomaly_names=[AnomalyName(id=2, name="Tamper")])
        anomalies = Anomalies(
            created_at=datetime(2024, 1, 1, tzinfo=UTC),
            sensors=[anomaly1, anomaly2],
        )
        with patch("custom_components.diagral.sensor.dt_util") as mock_dt:
            mock_dt.as_local.return_value.isoformat.return_value = (
                "2024-01-01T00:00:00+00:00"
            )
            mock_dt.now.return_value.isoformat.return_value = "2024-01-01T00:00:00"
            sensor._update_anomalies(anomalies, [], EMPTY_DEVICE_LIST)
        assert sensor._attr_native_value == 2

    def test_anomalies_updated_at_is_set(self):
        """updated_at attribute must always be set when anomalies exist."""
        sensor = make_sensor_mock()
        anomaly = AnomalyDetail(anomaly_names=[AnomalyName(id=1, name="Fault")])
        anomalies = Anomalies(
            created_at=datetime(2024, 1, 1, tzinfo=UTC),
            sensors=[anomaly],
        )
        with patch("custom_components.diagral.sensor.dt_util") as mock_dt:
            mock_dt.as_local.return_value.isoformat.return_value = (
                "2024-01-01T00:00:00+00:00"
            )
            mock_dt.now.return_value.isoformat.return_value = "2024-01-01T12:00:00"
            sensor._update_anomalies(anomalies, [], EMPTY_DEVICE_LIST)
        assert (
            sensor._attr_extra_state_attributes.get("updated_at")
            == "2024-01-01T12:00:00"
        )


class TestUpdateActiveGroups:
    """Tests for _update_active_groups()."""

    def _make_group(self, index: int, name: str) -> MagicMock:
        """Return a mock Group object."""
        group = MagicMock()
        group.index = index
        group.name = name
        return group

    def test_group_mode_counts_activated_groups(self):
        """non-PRESENCE mode must count activated_groups from system_status."""
        sensor = make_sensor_mock()

        system_status = MagicMock()
        system_status.status = "group"
        system_status.activated_groups = [1, 2]

        groups = [
            self._make_group(1, "Group 1"),
            self._make_group(2, "Group 2"),
            self._make_group(3, "Group 3"),
        ]
        alarm_config = MagicMock()

        with patch("custom_components.diagral.sensor.dt_util") as mock_dt:
            mock_dt.now.return_value.isoformat.return_value = "2024-01-01T00:00:00"
            sensor._update_active_groups(system_status, groups, alarm_config)

        assert sensor._attr_native_value == 2

    def test_logs_no_alarm_configuration(self, caplog):
        """The alarm configuration, with its serial and name, stays out of logs."""
        caplog.set_level(logging.DEBUG, logger="custom_components.diagral")
        sensor = make_sensor_mock()
        system_status = SimpleNamespace(status="group", activated_groups=[1])
        alarm_config = SimpleNamespace(
            presence_group=[],
            alarm=SimpleNamespace(
                name="Fake home", central=SimpleNamespace(serial="FAKECENTRAL01")
            ),
        )

        with patch("custom_components.diagral.sensor.dt_util"):
            sensor._update_active_groups(
                system_status, [self._make_group(1, "Group 1")], alarm_config
            )

        assert "FAKECENTRAL01" not in caplog.text
        assert "Fake home" not in caplog.text

    def test_presence_mode_uses_presence_group(self):
        """PRESENCE mode must use alarm_config.presence_group for the count."""
        sensor = make_sensor_mock()

        system_status = MagicMock()
        system_status.status = "PRESENCE"
        alarm_config = MagicMock()
        alarm_config.presence_group = [1]

        groups = [self._make_group(1, "Group 1"), self._make_group(2, "Group 2")]

        with patch("custom_components.diagral.sensor.dt_util") as mock_dt:
            mock_dt.now.return_value.isoformat.return_value = "2024-01-01T00:00:00"
            sensor._update_active_groups(system_status, groups, alarm_config)

        assert sensor._attr_native_value == 1

    def test_groups_info_active_flag_is_correct(self):
        """Groups attribute must correctly flag active vs inactive groups."""
        sensor = make_sensor_mock()

        system_status = MagicMock()
        system_status.status = "group"
        system_status.activated_groups = [1]

        groups = [self._make_group(1, "Group 1"), self._make_group(2, "Group 2")]
        alarm_config = MagicMock()

        with patch("custom_components.diagral.sensor.dt_util") as mock_dt:
            mock_dt.now.return_value.isoformat.return_value = "2024-01-01T00:00:00"
            sensor._update_active_groups(system_status, groups, alarm_config)

        groups_info = sensor._attr_extra_state_attributes["groups"]
        assert groups_info[0] == {"index": 1, "name": "Group 1", "active": True}
        assert groups_info[1] == {"index": 2, "name": "Group 2", "active": False}

    def test_no_active_groups_sets_value_to_zero(self):
        """No activated groups must set native_value to 0."""
        sensor = make_sensor_mock()

        system_status = MagicMock()
        system_status.status = "off"
        system_status.activated_groups = []

        groups = [self._make_group(1, "Group 1")]
        alarm_config = MagicMock()

        with patch("custom_components.diagral.sensor.dt_util") as mock_dt:
            mock_dt.now.return_value.isoformat.return_value = "2024-01-01T00:00:00"
            sensor._update_active_groups(system_status, groups, alarm_config)

        assert sensor._attr_native_value == 0


def make_health_sensor(key: str, coordinator: MagicMock):
    """Return the diagnostic sensor of the given key, bound to a coordinator."""
    description = next(d for d in HEALTH_SENSORS if d.key == key)
    entry = MagicMock(entry_id="entry1")
    coordinator.data = {
        "alarm_config": SimpleNamespace(
            alarm=SimpleNamespace(central=SimpleNamespace(serial="FAKECENTRAL01"))
        )
    }
    return DiagralHealthSensor(coordinator, description, entry)


class TestHealthSensors:
    """The webhook diagnostic sensors."""

    def test_webhook_status_survives_a_polling_outage(self):
        """The webhook state stays readable while Diagral cannot be polled."""
        coordinator = MagicMock(webhook_status="owned_elsewhere")
        coordinator.last_update_success = False
        sensor = make_health_sensor("webhook_status", coordinator)

        assert sensor.native_value == "owned_elsewhere"
        assert sensor.available is True
        assert sensor.unique_id == "entry1_diagral_FAKECENTRAL01_webhook_status"

    def test_webhook_status_is_an_enabled_enum(self):
        """Every webhook state is an option, shown by default."""
        description = next(d for d in HEALTH_SENSORS if d.key == "webhook_status")

        assert description.device_class == SensorDeviceClass.ENUM
        assert description.options == list(WEBHOOK_STATUSES)
        assert description.entity_category == EntityCategory.DIAGNOSTIC
        assert description.entity_registry_enabled_default is True

    def test_last_webhook_is_a_hidden_timestamp(self):
        """The last notification time is a timestamp, hidden until enabled."""
        received = datetime(2026, 10, 25, 0, 30, tzinfo=UTC)
        sensor = make_health_sensor("last_webhook", MagicMock(last_webhook=received))
        description = sensor.entity_description

        assert sensor.native_value == received
        assert description.device_class == SensorDeviceClass.TIMESTAMP
        assert description.entity_category == EntityCategory.DIAGNOSTIC
        assert description.entity_registry_enabled_default is False

    @pytest.mark.parametrize("language", ["en", "fr"])
    def test_every_state_is_translated(self, language):
        """Both languages name the sensors and every webhook state."""
        translations = json.loads(
            (TRANSLATIONS / f"{language}.json").read_text(encoding="utf-8")
        )["entity"]["sensor"]

        assert set(translations["webhook_status"]["state"]) == set(WEBHOOK_STATUSES)
        assert translations["last_webhook"]["name"]


def make_live_sensor(key: str, data: dict) -> DiagralSensor:
    """Return the sensor of the given key, reading the given coordinator data."""
    sensor = make_sensor_mock()
    sensor.entity_description = next(d for d in SENSORS if d.key == key)
    sensor.coordinator = MagicMock(data=data)
    sensor._attr_name = "Anomalies"
    sensor.async_write_ha_state = MagicMock()
    return sensor


class TestInitialValue:
    """The sensors show a value as soon as they are added."""

    async def test_value_is_set_when_added(self):
        """The first refresh ran before the entity existed: use its data."""
        sensor = make_live_sensor(
            "anomalies",
            {
                "alarm_config": MagicMock(),
                "anomalies": None,
                "groups": [],
                "system_status": MagicMock(),
                "devices_infos": EMPTY_DEVICE_LIST,
            },
        )
        with patch.object(CoordinatorEntity, "async_added_to_hass", AsyncMock()):
            await sensor.async_added_to_hass()

        assert sensor._attr_native_value == 0

    def test_state_is_written_without_alarm_config(self):
        """Missing data still publishes the state, so availability follows."""
        sensor = make_live_sensor("anomalies", {"alarm_config": None})
        sensor._handle_coordinator_update()

        sensor.async_write_ha_state.assert_called_once()
