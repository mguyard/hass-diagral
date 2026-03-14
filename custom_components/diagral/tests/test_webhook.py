"""Tests for enrich_data_alert_anomaly() in webhook.py (Tier 2).

Tests the pure data-enrichment function without any HTTP calls
or Home Assistant event bus interaction.
"""
from datetime import datetime, timezone

import pytest
from pydiagral.models import (
    DeviceInfos,
    DeviceList,
    WebHookNotification,
    WebHookNotificationDetail,
)

from custom_components.diagral.webhook import enrich_data_alert_anomaly


def make_notification(device_type: str | None, device_index: str | None) -> WebHookNotification:
    """Build a minimal WebHookNotification for testing enrich_data_alert_anomaly()."""
    detail = WebHookNotificationDetail(
        device_type=device_type,
        device_index=device_index,
        device_label=None,
    )
    return WebHookNotification(
        transmitter_id="TX001",
        alarm_type="ALERT",
        alarm_code="123",
        alarm_description="Test alert",
        group_index="1",
        detail=detail,
        user=None,
        date_time=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )


def make_device_list(**kwargs) -> DeviceList:
    """Build a DeviceList with the provided device type lists."""
    defaults = dict(cameras=[], commands=[], sensors=[], sirens=[], transmitters=[])
    defaults.update(kwargs)
    return DeviceList(**defaults)


class TestEnrichDataAlertAnomaly:
    """Tests for enrich_data_alert_anomaly()."""

    def test_device_type_none_skips_enrichment(self):
        """When device_type is None, data must be returned unchanged."""
        data = make_notification(device_type=None, device_index="1")
        result = enrich_data_alert_anomaly(data, make_device_list(), {})
        assert result is data
        assert result.detail.device_label is None

    def test_device_index_none_skips_enrichment(self):
        """When device_index is None, data must be returned unchanged."""
        data = make_notification(device_type="sensor", device_index=None)
        result = enrich_data_alert_anomaly(data, make_device_list(), {})
        assert result is data
        assert result.detail.device_label is None

    def test_matching_device_sets_label(self):
        """When a matching device is found, device_label must be set."""
        data = make_notification(device_type="sensor", device_index="5")
        devices = make_device_list(sensors=[DeviceInfos(index=5, label="Front Door")])
        result = enrich_data_alert_anomaly(data, devices, {})
        assert result.detail.device_label == "Front Door"

    def test_no_matching_device_leaves_label_none(self):
        """When no device matches the index, device_label must remain None."""
        data = make_notification(device_type="sensor", device_index="99")
        devices = make_device_list(sensors=[DeviceInfos(index=5, label="Front Door")])
        result = enrich_data_alert_anomaly(data, devices, {})
        assert result.detail.device_label is None

    def test_unknown_device_type_leaves_label_none(self):
        """When device_type doesn't match any DeviceList attribute, label stays None."""
        data = make_notification(device_type="unknowndevice", device_index="1")
        devices = make_device_list(sensors=[DeviceInfos(index=1, label="Sensor A")])
        result = enrich_data_alert_anomaly(data, devices, {})
        assert result.detail.device_label is None

    def test_device_type_is_lowercased_and_pluralized(self):
        """device_type 'SENSOR' must match 'sensors' attribute on DeviceList."""
        data = make_notification(device_type="SENSOR", device_index="3")
        devices = make_device_list(sensors=[DeviceInfos(index=3, label="Back Door")])
        result = enrich_data_alert_anomaly(data, devices, {})
        assert result.detail.device_label == "Back Door"
