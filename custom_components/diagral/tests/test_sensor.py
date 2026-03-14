"""Tests for pure logic methods of DiagralSensor (Tier 2).

Tests _update_anomalies() and _update_active_groups() without making
real API calls. dt_util is patched to avoid time-dependent output.
"""
from datetime import datetime, timezone

import pytest
from unittest.mock import MagicMock, patch
from pydiagral.models import Anomalies, AnomalyDetail, AnomalyName, DeviceList

from custom_components.diagral.sensor import DiagralSensor


# An empty DeviceList with explicit empty lists to avoid iteration errors
# (vars(MagicMock()) would contain non-iterable sentinel objects)
EMPTY_DEVICE_LIST = DeviceList(cameras=[], commands=[], sensors=[], sirens=[], transmitters=[])


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
        anomalies = Anomalies(created_at=datetime(2024, 1, 1, tzinfo=timezone.utc))
        with patch("custom_components.diagral.sensor.dt_util") as mock_dt:
            mock_dt.as_local.return_value.isoformat.return_value = "2024-01-01T00:00:00+00:00"
            mock_dt.now.return_value.isoformat.return_value = "2024-01-01T00:00:00"
            sensor._update_anomalies(anomalies, [], EMPTY_DEVICE_LIST)
        assert sensor._attr_native_value == 0

    def test_anomalies_count_is_correct(self):
        """Anomalies with 2 sensors must set native_value to 2."""
        sensor = make_sensor_mock()
        anomaly1 = AnomalyDetail(anomaly_names=[AnomalyName(id=1, name="Low battery")])
        anomaly2 = AnomalyDetail(anomaly_names=[AnomalyName(id=2, name="Tamper")])
        anomalies = Anomalies(
            created_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
            sensors=[anomaly1, anomaly2],
        )
        with patch("custom_components.diagral.sensor.dt_util") as mock_dt:
            mock_dt.as_local.return_value.isoformat.return_value = "2024-01-01T00:00:00+00:00"
            mock_dt.now.return_value.isoformat.return_value = "2024-01-01T00:00:00"
            sensor._update_anomalies(anomalies, [], EMPTY_DEVICE_LIST)
        assert sensor._attr_native_value == 2

    def test_anomalies_updated_at_is_set(self):
        """updated_at attribute must always be set when anomalies exist."""
        sensor = make_sensor_mock()
        anomaly = AnomalyDetail(anomaly_names=[AnomalyName(id=1, name="Fault")])
        anomalies = Anomalies(
            created_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
            sensors=[anomaly],
        )
        with patch("custom_components.diagral.sensor.dt_util") as mock_dt:
            mock_dt.as_local.return_value.isoformat.return_value = "2024-01-01T00:00:00+00:00"
            mock_dt.now.return_value.isoformat.return_value = "2024-01-01T12:00:00"
            sensor._update_anomalies(anomalies, [], EMPTY_DEVICE_LIST)
        assert sensor._attr_extra_state_attributes.get("updated_at") == "2024-01-01T12:00:00"


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

        groups = [self._make_group(1, "Group 1"), self._make_group(2, "Group 2"), self._make_group(3, "Group 3")]
        alarm_config = MagicMock()

        with patch("custom_components.diagral.sensor.dt_util") as mock_dt:
            mock_dt.now.return_value.isoformat.return_value = "2024-01-01T00:00:00"
            sensor._update_active_groups(system_status, groups, alarm_config)

        assert sensor._attr_native_value == 2

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
        """groups attribute must correctly flag active vs inactive groups."""
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
