"""Tests for diagnostics.py: nothing identifying leaves the file."""

from datetime import UTC, datetime
from importlib.metadata import version
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.diagral.diagnostics import async_get_config_entry_diagnostics

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


async def run_diagnostics(hass: MagicMock | None = None) -> dict:
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
            hass or make_hass(), make_entry()
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


async def test_package_version_is_read_off_the_event_loop():
    """Reading package metadata touches the disk: it runs in the executor."""
    hass = make_hass()
    result = await run_diagnostics(hass)

    hass.async_add_executor_job.assert_awaited_once_with(version, "pydiagral")
    assert result["health"]["pydiagral"] == version("pydiagral")
