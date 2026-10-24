"""Diagnostics support for Diagral."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from . import DiagralConfigEntry

TO_REDACT = {
    "api_key",
    "password",
    "pin_code",
    "secret_key",
    "username",
    "webhook_id",
    "alarmpanel_code",
    "serial_id",
    "unique_id",
    "title",
    "webhook_url",
    "webhook_url_hash",
    "url",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: DiagralConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""

    return {
        "info": async_redact_data(
            {
                **entry.as_dict(),
                "webhook_id": entry.runtime_data.webhook_id,
            },
            TO_REDACT,
        ),
        "connection": {
            "status": entry.runtime_data.coordinator.communication_status,
            "last_success": (
                entry.runtime_data.coordinator.last_success.isoformat()
                if entry.runtime_data.coordinator.last_success
                else None
            ),
            "consecutive_failures": entry.runtime_data.coordinator.consecutive_failures,
            "last_error": entry.runtime_data.coordinator.last_error,
            "webhook_status": entry.runtime_data.webhook_status,
            "webhook_last_received": (
                entry.runtime_data.webhook_last_received.isoformat()
                if entry.runtime_data.webhook_last_received
                else None
            ),
            "webhook_last_error": entry.runtime_data.webhook_last_error,
        },
    }
