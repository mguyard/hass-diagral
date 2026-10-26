"""Module to handle incoming webhooks from Diagral."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from aiohttp.web import Request
from pydiagral.exceptions import ModelValidationError
from pydiagral.models import DeviceInfos, DeviceList, WebHookNotification
from pydiagral.utils import schema_key

from homeassistant.components.alarm_control_panel import DOMAIN as PANEL_DOMAIN
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.util import dt as dt_util

from .const import (
    DIAGRAL_EVENT,
    DOMAIN,
    ENTRY_WEBHOOK_SIGNAL,
    WEBHOOK_FAILED,
    WEBHOOK_IGNORED,
    WEBHOOK_INVALID_JSON,
    WEBHOOK_INVALID_PAYLOAD,
    WEBHOOK_OTHER_CENTRAL,
    WEBHOOK_PROCESSED,
    WEBHOOK_SIGNAL,
)
from .coordinator import DiagralDataUpdateCoordinator

if TYPE_CHECKING:
    from . import DiagralConfigEntry

_LOGGER = logging.getLogger(__name__)


def _same_central(transmitter_id: str | None, serial_id: str) -> bool:
    """Return whether a notification comes from the entry's central.

    Diagral sends the central's serial as `transmitter_id`.
    """
    return (transmitter_id or "").strip().upper() == serial_id.strip().upper()


async def handle_webhook(
    hass: HomeAssistant, webhook_id: str, request: Request
) -> None:
    """Handle incoming webhook from Diagral."""
    # Only loaded entries have runtime_data; a disabled one would raise here
    entry = next(
        (
            entry
            for entry in hass.config_entries.async_loaded_entries(DOMAIN)
            if entry.runtime_data.webhook_id == webhook_id
        ),
        None,
    )
    if entry is None:
        _LOGGER.error("Received a webhook that matches no loaded Diagral entry")
        return

    # Recorded before reading the body, so even an unreadable one is listed
    record = _new_record()
    entry.runtime_data.recent_webhooks.append(record)
    try:
        try:
            payload = await request.json()
        except ValueError:
            _LOGGER.error("Received invalid JSON data from webhook")
            record.update(outcome=WEBHOOK_IGNORED, reason=WEBHOOK_INVALID_JSON)
            return
        if isinstance(payload, dict):
            record["keys"] = sorted({schema_key(str(key)) for key in payload})
        try:
            data = WebHookNotification.from_dict(payload)
        except ModelValidationError as err:
            # pydiagral keeps the payload, which carries the serial, out of the message
            _LOGGER.error("Ignoring an invalid Diagral webhook: %s", err)
            record.update(outcome=WEBHOOK_IGNORED, reason=WEBHOOK_INVALID_PAYLOAD)
            return
        record.update(_describe(data))
        # Never the payload: it carries the serial and user names into shared logs
        _LOGGER.debug(
            "Received Diagral webhook: %s %s (%s)",
            data.alarm_type,
            data.alarm_code,
            data.alarm_description,
        )

        # A notification of another central must never drive this entry
        if not _same_central(data.transmitter_id, entry.runtime_data.config.serial_id):
            _LOGGER.warning("Ignoring a Diagral webhook sent by another central")
            record.update(outcome=WEBHOOK_IGNORED, reason=WEBHOOK_OTHER_CENTRAL)
            return

        await _process(hass, entry, data)
    except Exception as err:
        record.update(outcome=WEBHOOK_FAILED, reason=type(err).__name__)
        raise


def _new_record() -> dict[str, Any]:
    """Return the diagnostics record of a notification just received."""
    return {
        "at": dt_util.now().isoformat(),
        "sent_at": None,
        "type": None,
        "alarm_code": None,
        "group_index": None,
        "device": None,
        "user": False,
        "keys": [],
        "outcome": WEBHOOK_PROCESSED,
        "reason": None,
    }


def _describe(data: WebHookNotification) -> dict[str, Any]:
    """Describe a notification by its technical fields: no serial, name or label."""
    detail = data.detail
    return {
        "sent_at": data.date_time.isoformat() if data.date_time else None,
        "type": data.alarm_type,
        "alarm_code": data.alarm_code,
        "group_index": data.group_index,
        "device": (
            {"type": detail.device_type, "index": detail.device_index}
            if detail and detail.device_type
            else None
        ),
        "user": bool(data.user and data.user.username),
    }


async def _process(
    hass: HomeAssistant, entry: DiagralConfigEntry, data: WebHookNotification
) -> None:
    """Refresh, enrich and publish a notification of the entry's own central."""
    coordinator: DiagralDataUpdateCoordinator = entry.runtime_data.coordinator
    coordinator.async_webhook_received()
    devices_infos: DeviceList = coordinator.data.get("devices_infos", {})
    groups = coordinator.data.get("groups", {})

    # Check the alarm type and handle the request accordingly
    if data.alarm_type in ["STATUS", "ANOMALY"]:
        _LOGGER.debug("Received status change webhook (type: %s)", data.alarm_type)
        await coordinator.async_request_refresh()

    # Enrich the data with additional information
    if data.alarm_type in ["ALERT", "ANOMALY"]:
        enriched_data = enrich_data_alert_anomaly(data, devices_infos, groups)
    else:
        enriched_data = data
    # Publish the event to the event bus
    publish_event(hass, enriched_data.__dict__, entry.entry_id)


def enrich_data_alert_anomaly(
    data: WebHookNotification, devices_infos: DeviceList, groups: dict
) -> WebHookNotification:
    """Enrich the data with additional information."""

    # If the device_type or device_index is None, skip the enrichment
    if data.detail.device_type is None or data.detail.device_index is None:
        _LOGGER.debug("Device type or index is None, skipping enrichment")
        return data

    webhook_device_types = (
        data.detail.device_type.lower() + "s"
    )  # Adding 's' to match the key in devices_infos
    webhook_device_index = int(data.detail.device_index)

    device_info: DeviceInfos | None = None
    _LOGGER.debug("Webhook device types: %s", webhook_device_types)
    _LOGGER.debug("Enriching data with device_infos: %s", devices_infos)
    # if webhook_device_types in devices_infos:
    if hasattr(devices_infos, webhook_device_types):
        device_list = getattr(devices_infos, webhook_device_types)
        device_info = next(
            (info for info in device_list if info.index == webhook_device_index),
            None,
        )
    if device_info:
        data.detail.device_label = device_info.label
    return data


def _panel_entity_id(hass: HomeAssistant, entry_id: str) -> str | None:
    """Return the alarm panel of the config entry, if registered."""
    entities = er.async_entries_for_config_entry(er.async_get(hass), entry_id)
    return next(
        (entity.entity_id for entity in entities if entity.domain == PANEL_DOMAIN),
        None,
    )


def publish_event(hass: HomeAssistant, data: dict, entry_id: str) -> None:
    """Publish event to the event bus."""
    event_type = data.pop("alarm_type", None)
    _LOGGER.debug("Publishing event %s", event_type)
    signal_data = {"type": event_type, "data": data}
    async_dispatcher_send(
        hass, WEBHOOK_SIGNAL.format(alarm_type=event_type), signal_data
    )
    async_dispatcher_send(
        hass,
        ENTRY_WEBHOOK_SIGNAL.format(entry_id=entry_id, alarm_type=event_type),
        signal_data,
    )

    event_data = {
        "type": event_type,
        "data": data,
        # Tells two centrals apart in automations
        "entry_id": entry_id,
        # The logbook only lists an event under an entity named in its data
        "entity_id": _panel_entity_id(hass, entry_id),
    }

    hass.bus.async_fire(DIAGRAL_EVENT, event_data)
