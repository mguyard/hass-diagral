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
