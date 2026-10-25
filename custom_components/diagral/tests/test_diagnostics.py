"""Tests for diagnostics.py: nothing identifying leaves the file."""

import asyncio
from collections import deque
from datetime import UTC, datetime
from importlib.metadata import version
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.diagral.diagnostics import async_get_config_entry_diagnostics
from pydiagral.exceptions import AuthenticationError, ClientError, ServerError
import pytest

from homeassistant.config_entries import ConfigEntryState

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
    "listed_key": "SECRETLISTEDKEY",
    "other_serial": "OTHERCENTRAL99",
    "automatism": "Front gate",
    "canal": "SECRETCANAL",
}


RECENT_WEBHOOK = {
    "at": "2026-10-25T18:40:03+01:00",
    "sent_at": "2026-10-25T17:40:02+00:00",
    "type": "ALERT",
    "alarm_code": "1130",
    "group_index": "03",
    "device": {"type": "SENSOR", "index": "2"},
    "user": False,
    "keys": ["alarm_code", "date_time", "detail", "group_index", "transmitter_id"],
    "outcome": "processed",
    "reason": None,
}


def make_entry() -> MagicMock:
    """Return a config entry whose dump carries every identifying value."""
    entry = MagicMock()
    entry.entry_id = "entry1"
    entry.state = ConfigEntryState.LOADED
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
    entry.runtime_data.recent_webhooks = deque([dict(RECENT_WEBHOOK)])
    entry.runtime_data.api.ping = AsyncMock(
        return_value=SimpleNamespace(status="we're alive")
    )
    entry.runtime_data.config.serial_id = SECRETS["serial"]
    entry.runtime_data.api.get_systems = AsyncMock(
        return_value=[
            SimpleNamespace(serial_id=SECRETS["other_serial"], api_keys=["OTHERKEY"]),
            SimpleNamespace(
                serial_id=SECRETS["serial"],
                api_keys=[SECRETS["listed_key"], *(f"KEY{i}" for i in range(12))],
            ),
        ]
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
    entry.runtime_data.api.get_automatism_rudes = AsyncMock(
        return_value=SimpleNamespace(
            rudes=[
                SimpleNamespace(
                    name=SECRETS["automatism"], canal=SECRETS["canal"], mode="PULSE"
                ),
                SimpleNamespace(name="Garage", canal="relais_2", mode="TIMER"),
            ]
        )
    )
    entry.runtime_data.api.response_shapes = MagicMock(
        return_value={"get_system_status": {"status": "OFF", "groups": [1]}}
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


async def test_diagnostics_count_the_central_api_keys():
    """Only the number of this central's keys: piled-up keys show, none leaks."""
    result = await run_diagnostics()

    assert result["health"]["api_keys"] == {"count": 13, "error": None}


async def test_api_key_count_when_the_central_is_not_listed():
    """A central missing from the account's list gives no count, and no error."""
    entry = make_entry()
    entry.runtime_data.api.get_systems = AsyncMock(return_value=[])

    result = await run_diagnostics(entry=entry)

    assert result["health"]["api_keys"] == {"count": None, "error": None}


async def test_api_key_count_when_the_login_is_refused():
    """A refused login is reported by name, without a count."""
    entry = make_entry()
    entry.runtime_data.api.get_systems = AsyncMock(
        side_effect=AuthenticationError("Login refused")
    )

    result = await run_diagnostics(entry=entry)

    assert result["health"]["api_keys"] == {
        "count": None,
        "error": "AuthenticationError",
    }


async def test_diagnostics_list_the_automatism_canals_and_modes():
    """A canal the specification lists is shown, any other one hidden: names never."""
    result = await run_diagnostics()

    assert result["automatisms"] == {
        "count": 2,
        "items": [
            {"canal": "other", "mode": "PULSE"},
            {"canal": "RELAIS_2", "mode": "TIMER"},
        ],
        "error": None,
    }


async def test_installation_without_automatisms():
    """No automatism is a count of zero, not an error."""
    entry = make_entry()
    entry.runtime_data.api.get_automatism_rudes = AsyncMock(
        return_value=SimpleNamespace(rudes=[])
    )

    result = await run_diagnostics(entry=entry)

    assert result["automatisms"] == {"count": 0, "items": [], "error": None}


async def test_automatisms_when_the_call_is_refused():
    """A refused call is reported by name, without a count."""
    entry = make_entry()
    entry.runtime_data.api.get_automatism_rudes = AsyncMock(
        side_effect=AuthenticationError("Invalid API key")
    )

    result = await run_diagnostics(entry=entry)

    assert result["automatisms"] == {
        "count": None,
        "items": None,
        "error": "AuthenticationError",
    }


async def test_diagnostics_list_what_the_models_did_not_expect():
    """The registry is copied field by field: a key pydiagral adds later stays out."""
    registry = [
        {"model": "Rude", "field": "mode", "problem": "is not a documented mode"},
        {"model": "Group", "field": "colour", "problem": "is not declared"},
    ]
    registry[0]["value"] = "IMPULSION"
    registry[1]["raw"] = SECRETS["device"]

    with patch(
        "custom_components.diagral.diagnostics.unexpected_data",
        return_value=registry,
    ):
        result = await run_diagnostics()

    assert result["health"]["unexpected_data"] == [
        {
            "model": "Rude",
            "field": "mode",
            "problem": "is not a documented mode",
            "value": "IMPULSION",
        },
        {"model": "Group", "field": "colour", "problem": "is not declared"},
    ]
    assert SECRETS["device"] not in json.dumps(result, default=str)


async def test_diagnostics_without_unexpected_data():
    """Data that fits the models gives an empty list."""
    with patch(
        "custom_components.diagral.diagnostics.unexpected_data", return_value=[]
    ):
        result = await run_diagnostics()

    assert result["health"]["unexpected_data"] == []


async def test_unexpected_data_include_the_reads_made_for_the_diagnostics():
    """The registry is read last: an automatism mode met by the download is in."""
    entry = make_entry()
    api = entry.runtime_data.api

    def registry() -> list:
        api.get_system_details.assert_awaited_once()
        api.get_automatism_rudes.assert_awaited_once()
        return []

    with patch(
        "custom_components.diagral.diagnostics.unexpected_data", side_effect=registry
    ):
        result = await run_diagnostics(entry=entry)

    assert result["health"]["unexpected_data"] == []


async def test_diagnostics_describe_the_shape_of_the_answers():
    """The shapes pydiagral recorded are listed as it gives them."""
    result = await run_diagnostics()

    assert result["api_shape"] == {
        "get_system_status": {"status": "OFF", "groups": [1]}
    }


async def test_answer_shapes_include_the_reads_made_for_the_diagnostics():
    """Shapes are taken last, so the reads the download itself makes are in."""
    entry = make_entry()
    api = entry.runtime_data.api

    def shapes() -> dict:
        api.get_system_details.assert_awaited_once()
        api.get_automatism_rudes.assert_awaited_once()
        return {}

    api.response_shapes = MagicMock(side_effect=shapes)

    result = await run_diagnostics(entry=entry)

    assert result["api_shape"] == {}


def make_unloaded_entry(state: ConfigEntryState) -> MagicMock:
    """Return an entry that did not load: it has no runtime data."""
    entry = make_entry()
    del entry.runtime_data
    entry.state = state
    entry.reason = (
        f"Error communicating with API: {SECRETS['serial']} {SECRETS['username']} "
        f"{SECRETS['title']}"
    )
    entry.data = entry.as_dict.return_value["data"]
    entry.title = entry.as_dict.return_value["title"]
    return entry


async def run_unloaded_diagnostics(entry: MagicMock, ping: AsyncMock) -> dict:
    """Return the diagnostics of an entry that did not load."""
    client = MagicMock(ping=ping)
    with (
        patch(
            "custom_components.diagral.diagnostics.DiagralAPI", return_value=client
        ) as api,
        patch("custom_components.diagral.diagnostics.async_get_clientsession"),
        patch(
            "custom_components.diagral.diagnostics.unexpected_data",
            return_value=[{"model": "Group", "field": "x", "problem": "is missing"}],
        ),
    ):
        result = await run_diagnostics(entry=entry)
    assert "serial_id" not in api.call_args.kwargs
    return result


@pytest.mark.parametrize(
    "state",
    [ConfigEntryState.SETUP_RETRY, ConfigEntryState.SETUP_ERROR],
    ids=["setup-retry", "setup-error"],
)
async def test_unloaded_entry_gives_reduced_diagnostics(state):
    """An entry that did not load still tells why and whether the cloud answers."""
    entry = make_unloaded_entry(state)
    ping = AsyncMock(return_value=SimpleNamespace(status="we're alive"))

    result = await run_unloaded_diagnostics(entry, ping)

    assert result["health"] == {
        "state": state.value,
        "reason": "Error communicating with API: **REDACTED** **REDACTED** "
        "**REDACTED**",
        "pydiagral": version("pydiagral"),
        "cloud": {"ping": {"reachable": True, "status": "we're alive", "error": None}},
        "repairs": ["webhook_owned_elsewhere"],
        "unexpected_data": [{"model": "Group", "field": "x", "problem": "is missing"}],
    }
    assert result["info"]["entry_id"] == "entry1"
    dump = json.dumps(result, default=str)
    for name, value in SECRETS.items():
        assert value not in dump, name


async def test_unloaded_entry_when_the_cloud_does_not_answer():
    """The ping tells a Diagral outage from a setup problem on this side."""
    entry = make_unloaded_entry(ConfigEntryState.SETUP_RETRY)
    ping = AsyncMock(side_effect=ServerError("Service unavailable"))

    result = await run_unloaded_diagnostics(entry, ping)

    assert result["health"]["cloud"]["ping"] == {
        "reachable": False,
        "status": None,
        "error": "ServerError",
    }


async def test_diagnostics_list_the_recent_webhooks():
    """The last notifications are listed with what was done with them."""
    entry = make_entry()

    result = await run_diagnostics(entry=entry)

    assert result["recent_webhooks"] == [RECENT_WEBHOOK]
    result["recent_webhooks"][0]["outcome"] = "changed"
    assert entry.runtime_data.recent_webhooks[0]["outcome"] == "processed"


async def test_package_version_is_read_off_the_event_loop():
    """Reading package metadata touches the disk: it runs in the executor."""
    hass = make_hass()
    result = await run_diagnostics(hass)

    hass.async_add_executor_job.assert_awaited_once_with(version, "pydiagral")
    assert result["health"]["pydiagral"] == version("pydiagral")
