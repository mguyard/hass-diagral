"""Tests for webhook.py.

enrich_data_alert_anomaly() is tested as a pure function; handle_webhook()
with a mocked Home Assistant, request and coordinator.
"""

from datetime import UTC, datetime
import logging
from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.diagral.webhook import enrich_data_alert_anomaly, handle_webhook
from pydiagral.models import (
    DeviceInfos,
    DeviceList,
    WebHookNotification,
    WebHookNotificationDetail,
)
import pytest


def make_notification(
    device_type: str | None, device_index: str | None
) -> WebHookNotification:
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
        date_time=datetime(2024, 1, 1, tzinfo=UTC),
    )


def make_device_list(**kwargs) -> DeviceList:
    """Build a DeviceList with the provided device type lists."""
    defaults = {
        "cameras": [],
        "commands": [],
        "sensors": [],
        "sirens": [],
        "transmitters": [],
    }
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


WEBHOOK_ID = "webhook-of-the-loaded-entry"


def make_hass_with_entries() -> tuple[MagicMock, MagicMock]:
    """Return a hass mock with a disabled diagral entry before a loaded one.

    The disabled entry has no runtime_data, as in Home Assistant.
    """
    disabled = MagicMock(spec=["entry_id", "state"])
    disabled.entry_id = "disabled"
    loaded = MagicMock()
    loaded.entry_id = "loaded"
    loaded.runtime_data.webhook_id = WEBHOOK_ID
    loaded.runtime_data.config.serial_id = "FAKECENTRAL01"
    loaded.runtime_data.coordinator.data = {"devices_infos": None, "groups": []}
    loaded.runtime_data.coordinator.async_request_refresh = AsyncMock()

    hass = MagicMock()
    hass.config_entries.async_entries.return_value = [disabled, loaded]
    hass.config_entries.async_loaded_entries.return_value = [loaded]
    hass.config_entries.async_get_entry.side_effect = {
        "disabled": disabled,
        "loaded": loaded,
    }.get
    return hass, loaded


def make_request(payload: dict) -> MagicMock:
    """Return an aiohttp request mock whose JSON body is the payload."""
    request = MagicMock()
    request.json = AsyncMock(return_value=payload)
    return request


class TestHandleWebhook:
    """Tests for handle_webhook()."""

    async def test_disabled_entry_does_not_block_loaded_one(self):
        """A STATUS webhook reaches the loaded entry despite a disabled sibling."""
        hass, loaded = make_hass_with_entries()
        request = make_request(
            {
                "transmitter_id": "FAKECENTRAL01",
                "alarm_code": "3401",
                "alarm_description": "Total system arming",
                "group_index": "01",
                "detail": {},
                "user": {"username": "Fake User", "user_type": "owner"},
                "date_time": "2026-01-01T12:00:00Z",
            }
        )

        with patch("custom_components.diagral.webhook.async_dispatcher_send"):
            await handle_webhook(hass, WEBHOOK_ID, request)

        loaded.runtime_data.coordinator.async_request_refresh.assert_awaited_once()
        hass.bus.async_fire.assert_called_once()
        assert hass.bus.async_fire.call_args.args[0] == "DIAGRAL_EVENT"

    async def test_unknown_webhook_id_is_ignored(self):
        """A webhook id matching no loaded entry publishes nothing."""
        hass, loaded = make_hass_with_entries()
        request = make_request(
            {
                "transmitter_id": "FAKECENTRAL01",
                "alarm_code": "3401",
                "date_time": "2026-01-01T12:00:00Z",
            }
        )

        await handle_webhook(hass, "unknown-webhook", request)

        loaded.runtime_data.coordinator.async_request_refresh.assert_not_awaited()
        hass.bus.async_fire.assert_not_called()

    async def test_unknown_webhook_id_not_logged(self, caplog):
        """The error for an unknown webhook does not echo its id."""
        caplog.set_level(logging.DEBUG, logger="custom_components.diagral")
        hass, _ = make_hass_with_entries()
        request = make_request(
            {
                "transmitter_id": "FAKECENTRAL01",
                "alarm_code": "3401",
                "date_time": "2026-01-01T12:00:00Z",
            }
        )

        await handle_webhook(hass, "SECRETUNKNOWNID", request)

        assert "matches no loaded Diagral entry" in caplog.text
        assert "SECRETUNKNOWNID" not in caplog.text


# A production STATUS notification, serial and user name anonymised: no
# `detail`, an `alarm_family` the model does not know, a group code instead
# of an index, and eight fractional digits in `date_time`.
PRODUCTION_STATUS = {
    "transmitter_id": "FAKECENTRAL01",
    "alarm_code": "3407",
    "alarm_description": "REMOTE-ARMING-OF-GROUP",
    "group_index": "PRESENCE_GROUP_CODE",
    "alarm_family": "ON_OFF",
    "date_time": "2026-10-24T23:22:47.59959433Z",
    "user": {"username": "Fake User", "user_type": "owner"},
}


class TestTransmitterCheck:
    """A notification is only accepted from the entry's own central."""

    @pytest.mark.parametrize(
        "transmitter_id",
        ["FAKECENTRAL01", " fakecentral01 "],
        ids=["same-serial", "case-and-spaces"],
    )
    async def test_own_central_is_accepted(self, transmitter_id):
        """The production payload of the entry's central is handled."""
        hass, loaded = make_hass_with_entries()
        payload = {**PRODUCTION_STATUS, "transmitter_id": transmitter_id}

        with patch("custom_components.diagral.webhook.async_dispatcher_send"):
            await handle_webhook(hass, WEBHOOK_ID, make_request(payload))

        loaded.runtime_data.coordinator.async_request_refresh.assert_awaited_once()
        hass.bus.async_fire.assert_called_once()

    async def test_other_transmitter_is_ignored(self, caplog):
        """A notification from another central drives nothing, logs no id."""
        hass, loaded = make_hass_with_entries()
        payload = {**PRODUCTION_STATUS, "transmitter_id": "OTHERCENTRAL99"}

        with patch(
            "custom_components.diagral.webhook.async_dispatcher_send"
        ) as dispatch:
            await handle_webhook(hass, WEBHOOK_ID, make_request(payload))

        loaded.runtime_data.coordinator.async_request_refresh.assert_not_awaited()
        dispatch.assert_not_called()
        hass.bus.async_fire.assert_not_called()
        assert "OTHERCENTRAL99" not in caplog.text
        assert "FAKECENTRAL01" not in caplog.text


class TestPublishedEvent:
    """DIAGRAL_EVENT names the config entry it belongs to."""

    async def test_event_names_its_entry_and_panel(self):
        """Automations tell two centrals apart; the panel's logbook lists it."""
        hass, _ = make_hass_with_entries()
        entities = [
            MagicMock(domain="sensor", entity_id="sensor.fake_home_anomalies"),
            MagicMock(domain="alarm_control_panel", entity_id="alarm_control_panel.x"),
        ]

        with (
            patch("custom_components.diagral.webhook.async_dispatcher_send"),
            patch(
                "custom_components.diagral.webhook.er.async_entries_for_config_entry",
                return_value=entities,
            ),
        ):
            await handle_webhook(hass, WEBHOOK_ID, make_request(PRODUCTION_STATUS))

        event_type, event_data = hass.bus.async_fire.call_args.args
        assert event_type == "DIAGRAL_EVENT"
        assert event_data["entry_id"] == "loaded"
        assert event_data["entity_id"] == "alarm_control_panel.x"
        assert event_data["type"] == "STATUS"

    async def test_signals_are_sent_per_entry(self):
        """Each panel hears its own central; the global signal is kept."""
        hass, _ = make_hass_with_entries()

        with patch("custom_components.diagral.webhook.async_dispatcher_send") as send:
            await handle_webhook(hass, WEBHOOK_ID, make_request(PRODUCTION_STATUS))

        assert {call.args[1] for call in send.call_args_list} == {
            "signal-diagral-webhook-STATUS",
            "signal-diagral-loaded-webhook-STATUS",
        }
