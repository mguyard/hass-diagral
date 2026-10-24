"""Tests for __init__.py: secrets must never reach the log.

Webhook ids are bearer secrets — anyone who knows one can post events to
Home Assistant — and API keys grant access to the Diagral account.
"""

import logging
import sys
from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.diagral import (
    async_remove_entry,
    register_webhook,
    unregister_webhook,
)
from pydiagral.exceptions import DiagralAPIError
import pytest

WEBHOOK_ID = "SECRETWEBHOOKID"
OTHER_URL = "https://other.example.net/api/webhook/OTHERSECRETID"


class _CloudError(Exception):
    pass


@pytest.fixture
def cloud():
    """Stand in for homeassistant.components.cloud, imported lazily."""
    module = MagicMock()
    module.CloudNotAvailable = _CloudError
    module.CloudNotConnected = _CloudError
    module.async_active_subscription.return_value = True
    module.async_get_or_create_cloudhook = AsyncMock(
        return_value="https://hooks.nabu.casa/SECRETCLOUDHOOK"
    )
    module.async_delete_cloudhook = AsyncMock()
    with patch.dict(sys.modules, {"homeassistant.components.cloud": module}):
        yield module


@pytest.fixture
def debug_log(caplog):
    """Capture everything the integration logs."""
    caplog.set_level(logging.DEBUG, logger="custom_components.diagral")
    return caplog


def make_entry() -> MagicMock:
    """Return a config entry mock."""
    entry = MagicMock()
    entry.title = "fake home (FAKECENTRAL01)"
    return entry


async def run_register(external_url: str, api: MagicMock) -> str | None:
    """Call register_webhook with Home Assistant helpers patched."""
    with (
        patch("custom_components.diagral.get_url", return_value=external_url),
        patch("custom_components.diagral.webhook_generate_id", return_value=WEBHOOK_ID),
        patch("custom_components.diagral.webhook_async_register"),
    ):
        return await register_webhook(MagicMock(), make_entry(), api, "test")


class TestRegisterWebhookLogs:
    """register_webhook() must not log webhook ids."""

    @pytest.mark.parametrize(
        ("external_url", "existing"),
        [
            ("https://ha.example.com", None),
            ("https://ha.example.com", OTHER_URL),
            ("https://ha.example.com", "https://ha.example.com/api/webhook/OLDID"),
            ("https://abcdef.ui.nabu.casa", None),
        ],
        ids=["new", "foreign-subscription", "own-subscription", "cloudhook"],
    )
    async def test_no_webhook_id_in_logs(
        self, cloud, debug_log, external_url, existing
    ):
        """No path writes a webhook id, ours or another installation's."""
        api = MagicMock()
        if existing is None:
            api.get_webhook = AsyncMock(
                side_effect=DiagralAPIError("No subscription found for FAKECENTRAL01")
            )
        else:
            api.get_webhook = AsyncMock(return_value=MagicMock(webhook_url=existing))
        api.update_webhook = AsyncMock()
        api.register_webhook = AsyncMock()

        assert await run_register(external_url, api) == WEBHOOK_ID

        for secret in (WEBHOOK_ID, "OTHERSECRETID", "OLDID", "SECRETCLOUDHOOK"):
            assert secret not in debug_log.text

    async def test_host_is_kept_for_diagnosis(self, cloud, debug_log):
        """The host stays in the log, only the path is redacted."""
        api = MagicMock()
        api.get_webhook = AsyncMock(return_value=MagicMock(webhook_url=OTHER_URL))
        api.update_webhook = AsyncMock()

        await run_register("https://ha.example.com", api)

        assert "ha.example.com" in debug_log.text
        assert "other.example.net" in debug_log.text

    async def test_failed_registration_hides_webhook_id(self, cloud, debug_log):
        """The error logged when Diagral refuses the subscription has no id."""
        api = MagicMock()
        api.get_webhook = AsyncMock(
            side_effect=DiagralAPIError("No subscription found for FAKECENTRAL01")
        )
        api.register_webhook = AsyncMock(side_effect=DiagralAPIError("refused"))

        assert await run_register("https://ha.example.com", api) is None
        assert WEBHOOK_ID not in debug_log.text


class TestUnregisterWebhookLogs:
    """unregister_webhook() must not log webhook ids."""

    async def test_cloudhook_deletion_hides_webhook_id(self, cloud, debug_log):
        """Deleting a cloudhook does not log its id."""
        api = MagicMock()
        api.get_webhook = AsyncMock(
            return_value=MagicMock(webhook_url="https://hooks.nabu.casa/SECRETCLOUD")
        )
        api.delete_webhook = AsyncMock()

        await unregister_webhook(MagicMock(), make_entry(), api, WEBHOOK_ID, "test")

        assert WEBHOOK_ID not in debug_log.text
        assert "SECRETCLOUD" not in debug_log.text


class TestRemoveEntryLogs:
    """async_remove_entry() must not log the API key it deletes."""

    async def test_deleted_api_key_not_logged(self, debug_log):
        """The success message names the entry, not the key."""
        entry = make_entry()
        entry.data = {
            "username": "fake@example.com",
            "password": "SECRETPASSWORD",
            "serial_id": "FAKECENTRAL01",
            "api_key": "SECRETAPIKEY",
        }
        diagral = MagicMock()
        diagral.login = AsyncMock()
        diagral.delete_apikey = AsyncMock()
        api_cls = MagicMock()
        api_cls.return_value.__aenter__ = AsyncMock(return_value=diagral)
        api_cls.return_value.__aexit__ = AsyncMock(return_value=None)

        with patch("custom_components.diagral.DiagralAPI", api_cls):
            await async_remove_entry(MagicMock(), entry)

        diagral.delete_apikey.assert_awaited_once_with(apikey="SECRETAPIKEY")
        assert "SECRETAPIKEY" not in debug_log.text
        assert "SECRETPASSWORD" not in debug_log.text
