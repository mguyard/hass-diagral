"""Regression coverage for secrets in exported diagnostics."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.diagral.config_flow import (
    CannotConnect,
    InvalidAuth,
    validate_account,
)
from custom_components.diagral.diagnostics import async_get_config_entry_diagnostics
from custom_components.diagral.models import AccountInfoData
from pydiagral.exceptions import AuthenticationError, ClientError
import pytest


async def test_diagnostics_redacts_panel_code_and_identifiers():
    """Redact credentials and identifiers while retaining connection health."""
    entry = MagicMock()
    entry.as_dict.return_value = {
        "data": {
            "password": "PASSWORD_SENTINEL",
            "pin_code": "PIN_SENTINEL",
            "api_key": "API_SENTINEL",
            "secret_key": "SECRET_SENTINEL",
            "username": "EMAIL_SENTINEL",
            "serial_id": "SERIAL_SENTINEL",
            "webhook_url_hash": "FINGERPRINT_SENTINEL",
        },
        "title": "ADDRESS_SENTINEL",
        "unique_id": "SERIAL_SENTINEL",
        "options": {"alarmpanel_options": {"alarmpanel_code": 987654321}},
    }
    entry.runtime_data = SimpleNamespace(
        webhook_id="WEBHOOK_SENTINEL",
        webhook_status="registered",
        webhook_last_received=None,
        webhook_last_error=None,
        coordinator=SimpleNamespace(
            communication_status="connected",
            last_success=None,
            consecutive_failures=0,
            last_error=None,
        ),
    )
    diagnostics = await async_get_config_entry_diagnostics(MagicMock(), entry)
    serialized = json.dumps(diagnostics)
    assert "SENTINEL" not in serialized
    assert "987654321" not in serialized
    assert diagnostics["connection"]["status"] == "connected"


@pytest.mark.parametrize(
    "error,expected",
    [
        (AuthenticationError("SENTINEL_AUTH"), InvalidAuth),
        (ClientError("SENTINEL_PASSWORD"), CannotConnect),
        (ValueError("SENTINEL_PAYLOAD"), CannotConnect),
    ],
)
async def test_validation_errors_do_not_leak_credentials(caplog, error, expected):
    """Translate validation errors without logging secrets or exposing context."""
    api = AsyncMock()
    api.__aenter__.return_value = api
    api.try_connection.side_effect = error
    account = AccountInfoData(
        username="user@example.invalid",
        password="SENTINEL_PASSWORD",
        serial_id="SENTINEL_SERIAL",
        pin_code="1234",
    )
    with (
        patch("custom_components.diagral.config_flow.DiagralAPI", return_value=api),
        pytest.raises(expected) as raised,
    ):
        await validate_account(account)
    assert "SENTINEL" not in caplog.text
    assert raised.value.__suppress_context__
