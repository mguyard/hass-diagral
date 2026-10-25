"""Diagnostics support for Diagral."""

from __future__ import annotations

import asyncio
from datetime import datetime
from importlib.metadata import version
from typing import Any

from pydiagral import DiagralAPIError
from pydiagral.api import DiagralAPI

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir

from . import DiagralConfigEntry
from .const import DIAGNOSTICS_PING_TIMEOUT, DOMAIN, WEBHOOK_CHECK_INTERVAL

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
    coordinator = entry.runtime_data.coordinator
    suffix = f"_{entry.entry_id}"
    repairs = sorted(
        issue.issue_id.removesuffix(suffix)
        for issue in ir.async_get(hass).issues.values()
        if issue.domain == DOMAIN and issue.issue_id.endswith(suffix)
    )

    return {
        "info": async_redact_data(
            {
                **entry.as_dict(),
                "webhook_id": entry.runtime_data.webhook_id,
            },
            TO_REDACT,
        ),
        "health": {
            # Package metadata is read from disk, never on the event loop
            "pydiagral": await hass.async_add_executor_job(version, "pydiagral"),
            "cloud": {
                "connected": coordinator.last_update_success,
                "last_success": _iso(coordinator.last_success),
                "last_error": coordinator.last_error,
                "ping": await _ping(entry.runtime_data.api),
            },
            "webhook": {
                "status": coordinator.webhook_status,
                "last_received": _iso(coordinator.last_webhook),
                "check_interval": WEBHOOK_CHECK_INTERVAL,
            },
            "repairs": repairs,
        },
        "alarm": _alarm_summary(coordinator.data or {}),
    }


async def _ping(api: DiagralAPI) -> dict[str, Any]:
    """Tell whether the Diagral cloud answers, whatever the credentials."""
    try:
        async with asyncio.timeout(DIAGNOSTICS_PING_TIMEOUT):
            ping = await api.ping()
    except (DiagralAPIError, TimeoutError) as err:
        return {"reachable": False, "status": None, "error": type(err).__name__}
    return {"reachable": True, "status": ping.status, "error": None}


def _iso(moment: datetime | None) -> str | None:
    return moment.isoformat() if moment else None


def _lists(model: Any) -> dict[str, list]:
    """Return the list fields of a pydiagral model, by name."""
    if not model:
        return {}
    return {
        name: value for name, value in vars(model).items() if isinstance(value, list)
    }


def _alarm_summary(data: dict[str, Any]) -> dict[str, Any]:
    """Describe the alarm with states and counts only: labels name the home."""
    status = data.get("system_status")
    return {
        "status": status.status if status else None,
        "activated_groups": list(status.activated_groups or []) if status else [],
        "groups": len(data.get("groups") or []),
        "devices": {
            kind: len(devices)
            for kind, devices in _lists(data.get("devices_infos")).items()
        },
        "anomalies": sum(
            len(items) for items in _lists(data.get("anomalies")).values()
        ),
    }
