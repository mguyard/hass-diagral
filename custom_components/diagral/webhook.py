"""Validate and route incoming Diagral webhooks to their owning entry."""

from dataclasses import asdict
from datetime import UTC, datetime
import logging

from aiohttp.web import Request
from pydiagral.models import DeviceInfos, DeviceList, WebHookNotification

from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


def _validated_notification(payload: object) -> WebHookNotification:
    """Use the library's validated parser, including numeric code/index support."""
    return WebHookNotification.from_dict(payload)


async def handle_webhook(
    hass: HomeAssistant, webhook_id: str, request: Request
) -> None:
    """Handle only valid notifications for a loaded entry and its transmitter."""
    entry = next(
        (
            candidate
            for candidate in hass.config_entries.async_loaded_entries(DOMAIN)
            if (runtime := getattr(candidate, "runtime_data", None)) is not None
            and runtime.webhook_id == webhook_id
            and runtime.webhook_local_registered
            and not runtime.stopping
        ),
        None,
    )
    if entry is None:
        _LOGGER.debug("Received a webhook that matches no loaded Diagral entry")
        return
    runtime = entry.runtime_data
    try:
        data = _validated_notification(await request.json())
    except ValueError, TypeError, KeyError, AttributeError:
        _LOGGER.warning("Ignoring malformed Diagral webhook")
        return
    # Never route a transmitter's notification into another alarm panel.
    if data.transmitter_id != runtime.config.serial_id or runtime.stopping:
        _LOGGER.warning("Ignoring Diagral webhook with an unexpected transmitter")
        return

    coordinator = runtime.coordinator
    current_data = coordinator.data or {}
    if data.alarm_type in ("ALERT", "ANOMALY"):
        data = enrich_data_alert_anomaly(
            data, current_data.get("devices_infos"), current_data.get("groups", [])
        )
    event_data = asdict(data)
    event_data["date_time"] = data.date_time.isoformat()
    runtime.webhook_last_received = datetime.now(UTC)
    runtime.webhook_status = "received"
    runtime.webhook_last_error = None
    async_dispatcher_send(hass, f"signal-{DOMAIN}-{entry.entry_id}-webhook-health")
    publish_event(hass, event_data, entry.entry_id)
    if data.alarm_type in ("STATUS", "ANOMALY"):
        await coordinator.async_request_refresh()


def enrich_data_alert_anomaly(
    data: WebHookNotification,
    devices_infos: DeviceList | None,
    groups: dict,
) -> WebHookNotification:
    """Add a known device label without assuming complete configuration data."""
    if (
        not data.detail
        or not data.detail.device_type
        or data.detail.device_index is None
    ):
        return data
    try:
        webhook_device_index = int(data.detail.device_index)
    except TypeError, ValueError:
        return data
    webhook_device_types = data.detail.device_type.lower() + "s"
    device_info: DeviceInfos | None = next(
        (
            info
            for info in (getattr(devices_infos, webhook_device_types, None) or [])
            if info.index == webhook_device_index
        ),
        None,
    )
    if device_info:
        data.detail.device_label = device_info.label
    return data


def publish_event(hass: HomeAssistant, data: dict, entry_id: str) -> None:
    """Publish a serializable public event and an entry-scoped internal signal."""
    event_data = dict(data)
    event_type = event_data.pop("alarm_type", None)
    envelope = {"entry_id": entry_id, "type": event_type, "data": event_data}
    async_dispatcher_send(hass, f"signal-{DOMAIN}-webhook-{event_type}", envelope)
    async_dispatcher_send(
        hass, f"signal-{DOMAIN}-{entry_id}-webhook-{event_type}", envelope
    )
    hass.bus.async_fire(f"{DOMAIN.upper()}_EVENT", envelope)
