"""Tests for diagnostics.py: nothing identifying leaves the file."""

import asyncio
from datetime import UTC, datetime
from importlib.metadata import version
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.diagral.diagnostics import async_get_config_entry_diagnostics
from pydiagral.exceptions import AuthenticationError, ClientError, ServerError
import pytest

SECRETS = {
    "serial": "FAKECENTRAL01",
    "title": "fake home",
    "username": "fake@example.com",
    "password": "SECRETPASSWORD",
    "pin": "97531",
    "api_key": "SECRETAPIKEY",
    "secret_key": "SECRETSECRETKEY",
    "webhook_id": "SECRETWEBHOOKID",
    "webhook_url_hash": "0f" * 32,
    "device": "Front door",
    "group": "Ground floor",
    "ip_address": "192.168.1.20",
    "vocal_contact": "0612345678",
}


def make_entry() -> MagicMock:
    """Return a config entry whose dump carries every identifying value."""
    entry = MagicMock()
    entry.entry_id = "entry1"
    entry.as_dict.return_value = {
        "entry_id": "entry1",
        "domain": "diagral",
        "title": f"{SECRETS['title']} ({SECRETS['serial']})",
        "unique_id": SECRETS["serial"],
        "data": {
            "serial_id": SECRETS["serial"],
            "username": SECRETS["username"],
            "password": SECRETS["password"],
            "pin_code": SECRETS["pin"],
            "api_key": SECRETS["api_key"],
            "secret_key": SECRETS["secret_key"],
            "webhook_id": SECRETS["webhook_id"],
            "webhook_url_hash": SECRETS["webhook_url_hash"],
        },
        "options": {},
    }
    entry.runtime_data.webhook_id = SECRETS["webhook_id"]
    entry.runtime_data.api.ping = AsyncMock(
        return_value=SimpleNamespace(status="we're alive")
    )
    entry.runtime_data.api.get_system_details = AsyncMock(
        return_value=SimpleNamespace(
            device_type="PLUG_IP~DIAGRAL",
            firmware_version="V1.6.0_V13_V1.1.20",
            ip_address=SECRETS["ip_address"],
            ipoda_version="3.0",
            mode="900",
            first_vocal_contact=SECRETS["vocal_contact"],
            is_alarm_file_present=False,
            is_mjpeg_archive_video_supported=False,
            is_mass_storage_present=True,
            is_remote_startup_shutdown_allowed=False,
            is_video_password_protected=False,
        )
    )
    coordinator = entry.runtime_data.coordinator
    coordinator.last_update_success = False
    coordinator.last_success = datetime(2026, 10, 25, 0, 30, tzinfo=UTC)
    coordinator.last_error = "ServerError"
    coordinator.webhook_status = "owned_elsewhere"
    coordinator.last_webhook = None
    device = SimpleNamespace(index=1, label=SECRETS["device"])
    coordinator.data = {
        "system_status": SimpleNamespace(status="GROUP", activated_groups=[1, 2]),
        "groups": [SimpleNamespace(index=1, name=SECRETS["group"])],
        "devices_infos": SimpleNamespace(
            cameras=[], commands=[], sensors=[device, device], sirens=[device]
        ),
        "anomalies": SimpleNamespace(sensors=[device], sirens=[]),
    }
    return entry


def issue(issue_id: str) -> MagicMock:
    """Return a repair issue of the diagral domain."""
    return MagicMock(domain="diagral", issue_id=issue_id)


def make_hass() -> MagicMock:
    """Return a hass whose executor runs jobs inline and records them."""
    hass = MagicMock()

    async def run(job, *args):
        return job(*args)

    hass.async_add_executor_job = AsyncMock(side_effect=run)
    return hass


async def run_diagnostics(
    hass: MagicMock | None = None, entry: MagicMock | None = None
) -> dict:
    """Return the diagnostics of the fake entry, with one active repair."""
    registry = MagicMock()
    registry.issues = {
        ("diagral", "webhook_owned_elsewhere_entry1"): issue(
            "webhook_owned_elsewhere_entry1"
        ),
        ("diagral", "webhook_no_url_other"): issue("webhook_no_url_other"),
    }
    with patch(
        "custom_components.diagral.diagnostics.ir.async_get", return_value=registry
    ):
        return await async_get_config_entry_diagnostics(
            hass or make_hass(), entry or make_entry()
        )


async def test_diagnostics_hide_identifying_values():
    """The file users attach to public issues names no central nor account."""
    result = await run_diagnostics()
    dump = json.dumps(result, default=str)

    for name, value in SECRETS.items():
        assert value not in dump, name
    assert result["info"]["entry_id"] == "entry1"


async def test_diagnostics_report_health_and_counts():
    """The file says why events or data are missing, with counts only."""
    result = await run_diagnostics()

    assert result["health"]["cloud"] == {
        "connected": False,
        "last_success": "2026-10-25T00:30:00+00:00",
        "last_error": "ServerError",
        "ping": {"reachable": True, "status": "we're alive", "error": None},
    }
    assert result["health"]["webhook"]["status"] == "owned_elsewhere"
    assert result["health"]["webhook"]["last_received"] is None
    assert result["health"]["repairs"] == ["webhook_owned_elsewhere"]
    assert result["health"]["pydiagral"]
    assert result["alarm"] == {
        "status": "GROUP",
        "activated_groups": [1, 2],
        "groups": 1,
        "devices": {"cameras": 0, "commands": 0, "sensors": 2, "sirens": 1},
        "anomalies": 1,
    }


@pytest.mark.parametrize(
    "error",
    [ServerError("Service unavailable"), ClientError("Connection refused")],
    ids=["server-error", "client-error"],
)
async def test_ping_failure_says_the_cloud_does_not_answer(error):
    """A cloud that does not answer is told apart from refused credentials."""
    entry = make_entry()
    entry.runtime_data.api.ping = AsyncMock(side_effect=error)

    result = await run_diagnostics(entry=entry)

    assert result["health"]["cloud"]["ping"] == {
        "reachable": False,
        "status": None,
        "error": type(error).__name__,
    }


async def test_slow_ping_does_not_hold_the_download():
    """A hung cloud fails the ping quickly instead of the whole download."""
    entry = make_entry()

    async def hang() -> None:
        await asyncio.sleep(5)

    entry.runtime_data.api.ping = AsyncMock(side_effect=hang)

    with patch("custom_components.diagral.diagnostics.DIAGNOSTICS_CLOUD_TIMEOUT", 0.01):
        result = await run_diagnostics(entry=entry)

    assert result["health"]["cloud"]["ping"] == {
        "reachable": False,
        "status": None,
        "error": "TimeoutError",
    }


async def test_diagnostics_describe_the_hardware():
    """The system details are listed, except what locates or reaches the home."""
    result = await run_diagnostics()

    assert result["system"] == {
        "device_type": "PLUG_IP~DIAGRAL",
        "firmware_version": "V1.6.0_V13_V1.1.20",
        "ipoda_version": "3.0",
        "mode": "900",
        "is_alarm_file_present": False,
        "is_mjpeg_archive_video_supported": False,
        "is_mass_storage_present": True,
        "is_remote_startup_shutdown_allowed": False,
        "is_video_password_protected": False,
    }


async def test_refused_credentials_are_told_apart_from_an_outage():
    """The cloud answers the ping but refuses the signed call: credentials, not outage."""
    entry = make_entry()
    entry.runtime_data.api.get_system_details = AsyncMock(
        side_effect=AuthenticationError("Invalid API key")
    )

    result = await run_diagnostics(entry=entry)

    assert result["health"]["cloud"]["ping"]["reachable"] is True
    assert result["system"] == {"error": "AuthenticationError"}


async def test_package_version_is_read_off_the_event_loop():
    """Reading package metadata touches the disk: it runs in the executor."""
    hass = make_hass()
    result = await run_diagnostics(hass)

    hass.async_add_executor_job.assert_awaited_once_with(version, "pydiagral")
    assert result["health"]["pydiagral"] == version("pydiagral")
