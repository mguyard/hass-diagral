"""Describe the webhooks received from Diagral in the activity log."""

from collections.abc import Callable
from typing import Any

from homeassistant.components.logbook import (
    LOGBOOK_ENTRY_ENTITY_ID,
    LOGBOOK_ENTRY_MESSAGE,
    LOGBOOK_ENTRY_NAME,
)
from homeassistant.core import Event, HomeAssistant, callback

from .const import BRAND, DIAGRAL_EVENT, DOMAIN


def _field(value: Any, key: str) -> Any:
    """Read a key of a recorded event, or an attribute of a live one."""
    if isinstance(value, dict):
        return value.get(key)
    return getattr(value, key, None)


@callback
def async_describe_events(
    hass: HomeAssistant,
    async_describe_event: Callable[
        [str, str, Callable[[Event], dict[str, str | None]]], None
    ],
) -> None:
    """Describe DIAGRAL_EVENT, fired for every webhook received."""

    @callback
    def describe(event: Event) -> dict[str, str | None]:
        """Describe one received webhook."""
        data = event.data.get("data") or {}
        message = (
            f"{event.data.get('type')} webhook: {_field(data, 'alarm_description')}"
        )
        if code := _field(data, "alarm_code"):
            message += f" ({code})"
        if username := _field(_field(data, "user"), "username"):
            message += f", by {username}"
        if device := _field(_field(data, "detail"), "device_label"):
            message += f", {device}"
        return {
            LOGBOOK_ENTRY_NAME: BRAND,
            LOGBOOK_ENTRY_MESSAGE: message,
            LOGBOOK_ENTRY_ENTITY_ID: event.data.get("entity_id"),
        }

    async_describe_event(DOMAIN, DIAGRAL_EVENT, describe)
