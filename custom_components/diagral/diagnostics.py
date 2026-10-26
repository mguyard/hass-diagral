"""Diagnostics support for Diagral."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable
from datetime import datetime
from importlib.metadata import version
import re
from typing import Any

from pydiagral import DiagralAPIError
from pydiagral.api import DiagralAPI
from pydiagral.constants import AUTOMATISM_CANALS
from pydiagral.models import unexpected_data

from homeassistant.components.diagnostics import REDACTED, async_redact_data
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from . import DiagralConfigEntry
from .const import (
    CONF_SERIAL_ID,
    DIAGNOSTICS_CLOUD_TIMEOUT,
    DIAGRAL_VENDOR,
    DOMAIN,
    WEBHOOK_CHECK_INTERVAL,
)

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

# Copied field by field, so a field pydiagral adds to its registry later stays out.
UNEXPECTED_DATA_FIELDS = ("model", "field", "problem", "value")


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: DiagralConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    repairs = _repairs(hass, entry)
    if entry.state is not ConfigEntryState.LOADED:
        return await _unloaded_diagnostics(hass, entry, repairs)
    coordinator = entry.runtime_data.coordinator
    # Read before the registry and the shapes, so they cover these reads too.
    api = entry.runtime_data.api
    ping = await _ping(api)
    api_keys = await _api_key_count(api, entry.runtime_data.config.serial_id)
    system = await _system_details(api)
    automatisms = await _automatisms(api)

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
                "ping": ping,
            },
            "webhook": {
                "status": coordinator.webhook_status,
                "last_received": _iso(coordinator.last_webhook),
                "check_interval": WEBHOOK_CHECK_INTERVAL,
            },
            "repairs": repairs,
            "unexpected_data": _unexpected_data(),
            "api_keys": api_keys,
        },
        "alarm": _alarm_summary(coordinator.data or {}),
        "system": system,
        "automatisms": automatisms,
        "api_shape": api.response_shapes(),
        # Copied, so a notification arriving meanwhile cannot alter the file
        "recent_webhooks": [
            dict(record) for record in entry.runtime_data.recent_webhooks
        ],
    }


async def _unloaded_diagnostics(
    hass: HomeAssistant, entry: DiagralConfigEntry, repairs: list[str]
) -> dict[str, Any]:
    """Diagnose an entry that did not load, when the file is needed most."""
    # The ping needs no credential: it tells a Diagral outage from a setup problem.
    api = DiagralAPI(
        username=entry.data[CONF_USERNAME],
        password=entry.data[CONF_PASSWORD],
        request_timeout=DIAGNOSTICS_CLOUD_TIMEOUT,
        session=async_get_clientsession(hass),
        vendor=DIAGRAL_VENDOR,
    )
    return {
        "info": async_redact_data(entry.as_dict(), TO_REDACT),
        "health": {
            "state": entry.state.value,
            "reason": _redact_text(
                entry.reason,
                (
                    entry.data.get(CONF_SERIAL_ID),
                    entry.data.get(CONF_USERNAME),
                    entry.title,
                    # The title is "<alarm name> (<serial>)": the name can come alone
                    entry.title.rsplit(" (", 1)[0],
                ),
            ),
            "pydiagral": await hass.async_add_executor_job(version, "pydiagral"),
            "cloud": {"ping": await _ping(api)},
            "repairs": repairs,
            "unexpected_data": _unexpected_data(),
        },
    }


def _repairs(hass: HomeAssistant, entry: DiagralConfigEntry) -> list[str]:
    """List the repair issues of this entry, without the entry id they end with."""
    suffix = f"_{entry.entry_id}"
    return sorted(
        issue.issue_id.removesuffix(suffix)
        for issue in ir.async_get(hass).issues.values()
        if issue.domain == DOMAIN and issue.issue_id.endswith(suffix)
    )


def _unexpected_data() -> list[dict[str, str]]:
    """Copy pydiagral's registry field by field; it covers every entry of the process."""
    return [
        {key: item[key] for key in UNEXPECTED_DATA_FIELDS if key in item}
        for item in unexpected_data()
    ]


def _redact_text(text: str | None, values: tuple[str | None, ...]) -> str | None:
    """Mask identifying values in a free text, such as a setup error message."""
    if not text:
        return text
    # Longest first, so a value containing another one is masked whole
    for value in sorted(filter(None, values), key=len, reverse=True):
        text = re.sub(re.escape(value), REDACTED, text, flags=re.IGNORECASE)
    return text


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
