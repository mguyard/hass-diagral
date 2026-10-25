"""Diagnostics support for Diagral."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable
from datetime import datetime
from importlib.metadata import version
from typing import Any

from pydiagral import DiagralAPIError
from pydiagral.api import DiagralAPI
from pydiagral.constants import AUTOMATISM_CANALS

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir

from . import DiagralConfigEntry
from .const import DIAGNOSTICS_CLOUD_TIMEOUT, DOMAIN, WEBHOOK_CHECK_INTERVAL

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

# An allowlist, so a field Diagral adds later stays out until reviewed. The IP
# address and the first vocal contact are left out: they locate or reach the home.
SYSTEM_DETAILS_FIELDS = (
    "device_type",
    "firmware_version",
    "ipoda_version",
    "mode",
    "is_alarm_file_present",
    "is_mjpeg_archive_video_supported",
    "is_mass_storage_present",
    "is_remote_startup_shutdown_allowed",
    "is_video_password_protected",
)


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
            "api_keys": await _api_key_count(
                entry.runtime_data.api, entry.runtime_data.config.serial_id
            ),
        },
        "alarm": _alarm_summary(coordinator.data or {}),
        "system": await _system_details(entry.runtime_data.api),
        "automatisms": await _automatisms(entry.runtime_data.api),
    }


async def _query(call: Awaitable[Any]) -> tuple[Any, str | None]:
    """Run a cloud call for diagnostics: its result, or the name of its error."""
    try:
        async with asyncio.timeout(DIAGNOSTICS_CLOUD_TIMEOUT):
            return await call, None
    except (DiagralAPIError, TimeoutError) as err:
        return None, type(err).__name__


async def _ping(api: DiagralAPI) -> dict[str, Any]:
    """Tell whether the Diagral cloud answers, whatever the credentials."""
    ping, error = await _query(api.ping())
    if error:
        return {"reachable": False, "status": None, "error": error}
    return {"reachable": True, "status": ping.status, "error": None}


async def _api_key_count(api: DiagralAPI, serial_id: str) -> dict[str, Any]:
    """Count the central's API keys, never list them: they are secrets."""
    systems, error = await _query(api.get_systems())
    if error:
        return {"count": None, "error": error}
    keys = next(
        (
            system.api_keys
            for system in systems
            if system.serial_id.upper() == serial_id.upper()
        ),
        None,
    )
    return {"count": None if keys is None else len(keys), "error": None}


async def _system_details(api: DiagralAPI) -> dict[str, Any]:
    """Describe the hardware; a refused call here, after a ping, means credentials."""
    details, error = await _query(api.get_system_details())
    if error:
        return {"error": error}
    return {name: getattr(details, name) for name in SYSTEM_DETAILS_FIELDS}


async def _automatisms(api: DiagralAPI) -> dict[str, Any]:
    """List the automatisms without their names, which name the home."""
    rudes, error = await _query(api.get_automatism_rudes())
    if error:
        return {"count": None, "items": None, "error": error}
    return {
        "count": len(rudes.rudes),
        "items": [
            {"canal": _known_canal(rude.canal), "mode": rude.mode}
            for rude in rudes.rudes
        ],
        "error": None,
    }


def _known_canal(canal: str) -> str:
    """Return a canal of the specification, or "other": a free value could leak."""
    canal = canal.upper()
    return canal if canal in AUTOMATISM_CANALS else "other"


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
