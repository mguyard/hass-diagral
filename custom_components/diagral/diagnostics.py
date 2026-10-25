"""Diagnostics support for Diagral."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from . import DiagralConfigEntry

# Users attach this file to public issues: the serial (also the unique id) and
# the alarm name in the title identify their installation.
TO_REDACT = {
    "api_key",
    "password",
    "pin_code",
    "secret_key",
    "serial_id",
    "title",
    "unique_id",
    "username",
    "webhook_id",
    "webhook_url_hash",
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
    }
