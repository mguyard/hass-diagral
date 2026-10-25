"""Tests for diagnostics.py: nothing identifying leaves the file."""

import json
from unittest.mock import MagicMock

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
}


def make_entry() -> MagicMock:
    """Return a config entry whose dump carries every identifying value."""
    entry = MagicMock()
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
    return entry


async def test_diagnostics_hide_identifying_values():
    """The file users attach to public issues names no central nor account."""
    result = await async_get_config_entry_diagnostics(MagicMock(), make_entry())
    dump = json.dumps(result)

    for name, value in SECRETS.items():
        assert value not in dump, name
    assert result["info"]["entry_id"] == "entry1"
