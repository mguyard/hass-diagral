"""Tests for __init__.py: webhook ownership and secrets in logs.

The central holds a single webhook subscription. An entry only updates or
deletes it when it can prove the subscription is its own; otherwise it
raises a repair issue and leaves it alone. Webhook ids are bearer secrets
and API keys grant access to the Diagral account: neither may be logged.
"""

import hashlib
import logging
import sys
from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.diagral import (
    WebhookUnavailable,
    async_check_webhook,
    async_migrate_entry,
    async_remove_entry,
    async_setup_entry,
    register_webhook,
    unregister_webhook,
)
from custom_components.diagral.const import (
    CONF_PIN_CODE,
    CONF_WEBHOOK_URL_HASH,
    CONFIG_MINOR_VERSION,
    CONFIG_VERSION,
    DIAGRAL_REQUEST_TIMEOUT,
    ISSUE_WEBHOOK_NO_URL,
    ISSUE_WEBHOOK_OWNED_ELSEWHERE,
    ISSUE_WEBHOOK_REGISTRATION_FAILED,
    WEBHOOK_CONNECTED,
    WEBHOOK_NO_URL,
    WEBHOOK_OWNED_ELSEWHERE,
    WEBHOOK_REGISTRATION_FAILED,
    WEBHOOK_UNREGISTERED,
)
from pydiagral.exceptions import DiagralAPIError
import pytest

from homeassistant.const import CONF_WEBHOOK_ID
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.network import NoURLAvailableError

WEBHOOK_ID = "SECRETWEBHOOKID"
OWN_HOST = "https://ha.example.com"
OWN_NEW_URL = f"{OWN_HOST}/api/webhook/{WEBHOOK_ID}"
OWN_OLD_URL = f"{OWN_HOST}/api/webhook/OLDID"
OTHER_URL = "https://other.example.net/api/webhook/OTHERSECRETID"
CLOUDHOOK_URL = "https://hooks.nabu.casa/SECRETCLOUDHOOK"
NO_SUBSCRIPTION = DiagralAPIError("No subscription found for FAKECENTRAL01")


def url_hash(url: str) -> str:
    """Return the hash an entry stores to recognise its subscription."""
    return hashlib.sha256(url.encode()).hexdigest()


class _CloudError(Exception):
    pass


@pytest.fixture
def cloud():
    """Stand in for homeassistant.components.cloud, imported lazily."""
    module = MagicMock()
    module.CloudNotAvailable = _CloudError
    module.CloudNotConnected = _CloudError
    module.async_active_subscription.return_value = True
    module.async_get_or_create_cloudhook = AsyncMock(return_value=CLOUDHOOK_URL)
    module.async_delete_cloudhook = AsyncMock()
    with patch.dict(sys.modules, {"homeassistant.components.cloud": module}):
        yield module


@pytest.fixture
def issues():
    """Patch the issue registry helper used by the integration."""
    with patch("custom_components.diagral.ir") as ir:
        yield ir


@pytest.fixture
def debug_log(caplog):
    """Capture everything the integration logs."""
    caplog.set_level(logging.DEBUG, logger="custom_components.diagral")
    return caplog


def make_entry(stored_url: str | None = None) -> MagicMock:
    """Return a config entry mock, optionally owning a subscription."""
    entry = MagicMock()
    entry.entry_id = "entry1"
    entry.title = "fake home (FAKECENTRAL01)"
    entry.data = {}
    if stored_url is not None:
        entry.data[CONF_WEBHOOK_URL_HASH] = url_hash(stored_url)
    return entry


def make_api(existing_url: str | None) -> MagicMock:
    """Return a DiagralAPI mock whose central has the given subscription."""
    api = MagicMock()
    if existing_url is None:
        api.get_webhook = AsyncMock(side_effect=NO_SUBSCRIPTION)
    else:
        api.get_webhook = AsyncMock(return_value=MagicMock(webhook_url=existing_url))
    api.update_webhook = AsyncMock()
    api.register_webhook = AsyncMock()
    api.delete_webhook = AsyncMock()
    return api


async def run_register(
    entry: MagicMock,
    api: MagicMock,
    external_url: str = OWN_HOST,
    *,
    take_over: bool = False,
    local: MagicMock | None = None,
) -> tuple[str | None, MagicMock]:
    """Call register_webhook with Home Assistant helpers patched."""
    hass = MagicMock()
    local = local or MagicMock()
    with (
        patch("custom_components.diagral.get_url", return_value=external_url),
        patch("custom_components.diagral.webhook_generate_id", return_value=WEBHOOK_ID),
        patch("custom_components.diagral.webhook_async_register", local.register),
        patch("custom_components.diagral.webhook_async_unregister", local.unregister),
    ):
        result = await register_webhook(hass, entry, api, "test", take_over=take_over)
    return result, hass


def deleted_issues(issues: MagicMock) -> set[str]:
    """Return the ids of the repair issues the integration deleted."""
    return {call.args[2] for call in issues.async_delete_issue.call_args_list}


WEBHOOK_ISSUES = {
    f"{ISSUE_WEBHOOK_OWNED_ELSEWHERE}_entry1",
    f"{ISSUE_WEBHOOK_REGISTRATION_FAILED}_entry1",
    f"{ISSUE_WEBHOOK_NO_URL}_entry1",
}


def stored_hash(hass: MagicMock) -> str | None:
    """Return the hash written to the entry, or None if nothing was written."""
    if not hass.config_entries.async_update_entry.called:
        return None
    return hass.config_entries.async_update_entry.call_args.kwargs["data"].get(
        CONF_WEBHOOK_URL_HASH
    )


class TestRegisterOwnership:
    """register_webhook() only replaces a subscription it owns."""

    async def test_no_subscription_registers_and_remembers(self, cloud, issues):
        """Without a subscription, register one and remember it."""
        api = make_api(None)
        result, hass = await run_register(make_entry(), api)

        assert result == WEBHOOK_ID
        api.register_webhook.assert_awaited_once()
        assert stored_hash(hass) == url_hash(OWN_NEW_URL)
        assert deleted_issues(issues) == WEBHOOK_ISSUES

    async def test_own_subscription_is_updated(self, cloud, issues):
        """A subscription matching the stored hash is updated in place."""
        api = make_api(OWN_OLD_URL)
        result, hass = await run_register(make_entry(OWN_OLD_URL), api)

        assert result == WEBHOOK_ID
        api.update_webhook.assert_awaited_once()
        assert stored_hash(hass) == url_hash(OWN_NEW_URL)

    async def test_foreign_subscription_is_left_alone(self, cloud, issues):
        """A subscription owned elsewhere is not touched; a repair is raised."""
        api = make_api(OTHER_URL)
        result, hass = await run_register(make_entry(OWN_OLD_URL), api)

        assert result is None
        api.update_webhook.assert_not_awaited()
        api.register_webhook.assert_not_awaited()
        issues.async_create_issue.assert_called_once()
        kwargs = issues.async_create_issue.call_args.kwargs
        assert kwargs["translation_key"] == ISSUE_WEBHOOK_OWNED_ELSEWHERE
        assert kwargs["is_fixable"] is True
        assert kwargs["data"] == {"entry_id": "entry1"}
        assert stored_hash(hass) is None

    async def test_same_host_but_other_id_is_foreign_once_tracked(self, cloud, issues):
        """Two installations behind Nabu Casa share a host: the hash decides."""
        api = make_api("https://hooks.nabu.casa/SOMEONEELSE")
        result, _ = await run_register(
            make_entry(CLOUDHOOK_URL), api, "https://abcdef.ui.nabu.casa"
        )

        assert result is None
        api.update_webhook.assert_not_awaited()

    @pytest.mark.parametrize(
        ("existing", "owned"),
        [(OWN_OLD_URL, True), (OTHER_URL, False)],
        ids=["same-host", "other-host"],
    )
    async def test_untracked_entry_falls_back_to_host(
        self, cloud, issues, existing, owned
    ):
        """An entry set up before ownership tracking compares hosts once."""
        api = make_api(existing)
        result, hass = await run_register(make_entry(), api)

        assert (result == WEBHOOK_ID) is owned
        assert api.update_webhook.await_count == int(owned)
        assert (stored_hash(hass) == url_hash(OWN_NEW_URL)) is owned

    async def test_take_over_replaces_foreign_subscription(self, cloud, issues):
        """An explicit take-over updates even a foreign subscription."""
        api = make_api(OTHER_URL)
        result, hass = await run_register(make_entry(), api, take_over=True)

        assert result == WEBHOOK_ID
        api.update_webhook.assert_awaited_once()
        issues.async_create_issue.assert_not_called()
        assert deleted_issues(issues) == WEBHOOK_ISSUES
        assert stored_hash(hass) == url_hash(OWN_NEW_URL)


class TestUnregisterOwnership:
    """unregister_webhook() only deletes a subscription it owns."""

    async def test_own_subscription_is_deleted(self, cloud):
        """The entry's own subscription is deleted and forgotten."""
        api = make_api(OWN_OLD_URL)
        entry = make_entry(OWN_OLD_URL)
        hass = MagicMock()
        with patch("custom_components.diagral.webhook_async_unregister") as local:
            await unregister_webhook(hass, entry, api, WEBHOOK_ID, "test")

        api.delete_webhook.assert_awaited_once()
        local.assert_called_once_with(hass, WEBHOOK_ID)
        assert stored_hash(hass) is None
        assert (
            CONF_WEBHOOK_URL_HASH
            not in hass.config_entries.async_update_entry.call_args.kwargs["data"]
        )

    @pytest.mark.parametrize(
        "stored", [OWN_OLD_URL, None], ids=["tracked-other", "untracked"]
    )
    async def test_foreign_subscription_is_kept(self, cloud, stored):
        """A subscription the entry cannot prove it owns is not deleted."""
        api = make_api(OTHER_URL)
        hass = MagicMock()
        with patch("custom_components.diagral.webhook_async_unregister") as local:
            await unregister_webhook(hass, make_entry(stored), api, WEBHOOK_ID, "t")

        api.delete_webhook.assert_not_awaited()
        local.assert_called_once_with(hass, WEBHOOK_ID)


class TestLogsHideSecrets:
    """No webhook id, API key or password reaches the log."""

    @pytest.mark.parametrize(
        ("external_url", "existing", "stored"),
        [
            (OWN_HOST, None, None),
            (OWN_HOST, OTHER_URL, None),
            (OWN_HOST, OWN_OLD_URL, OWN_OLD_URL),
            ("https://abcdef.ui.nabu.casa", None, None),
        ],
        ids=["new", "foreign-subscription", "own-subscription", "cloudhook"],
    )
    async def test_register_hides_webhook_ids(
        self, cloud, issues, debug_log, external_url, existing, stored
    ):
        """No registration path writes a webhook id."""
        await run_register(make_entry(stored), make_api(existing), external_url)

        for secret in (WEBHOOK_ID, "OTHERSECRETID", "OLDID", "SECRETCLOUDHOOK"):
            assert secret not in debug_log.text

    async def test_host_is_kept_for_diagnosis(self, cloud, issues, debug_log):
        """The hosts stay in the log, only the paths are redacted."""
        await run_register(make_entry(), make_api(OTHER_URL))

        assert "other.example.net" in debug_log.text

    async def test_failed_registration_hides_webhook_id(self, cloud, issues, debug_log):
        """The error logged when Diagral refuses the subscription has no id."""
        api = make_api(None)
        api.register_webhook = AsyncMock(side_effect=DiagralAPIError("refused"))

        with pytest.raises(WebhookUnavailable):
            await run_register(make_entry(), api)

        assert WEBHOOK_ID not in debug_log.text

    async def test_cloudhook_deletion_hides_webhook_id(self, cloud, debug_log):
        """Deleting a cloudhook does not log its id."""
        api = make_api(CLOUDHOOK_URL)

        await unregister_webhook(
            MagicMock(), make_entry(CLOUDHOOK_URL), api, WEBHOOK_ID, "test"
        )

        cloud.async_delete_cloudhook.assert_awaited_once()
        assert WEBHOOK_ID not in debug_log.text
        assert "SECRETCLOUDHOOK" not in debug_log.text

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


def make_versioned_entry(version: int, minor: int, pin) -> MagicMock:
    """Return a config entry mock stored at the given config version."""
    entry = MagicMock()
    entry.version = version
    entry.minor_version = minor
    entry.data = {"serial_id": "FAKECENTRAL01", CONF_PIN_CODE: pin}
    return entry


class TestMigrateEntry:
    """async_migrate_entry() brings any older entry to the current version."""

    @pytest.mark.parametrize(
        ("minor", "pin", "expected_pin"),
        [(1, 1234, "1234"), (2, "1234", "1234"), (3, "0123", "0123")],
        ids=["1.1-int-pin", "1.2", "1.3-already-migrated"],
    )
    async def test_version_1_reaches_current_version(self, minor, pin, expected_pin):
        """Every 1.x entry ends at the current version, PIN stored as text."""
        hass = MagicMock()
        entry = make_versioned_entry(1, minor, pin)

        assert await async_migrate_entry(hass, entry) is True

        kwargs = hass.config_entries.async_update_entry.call_args.kwargs
        assert kwargs["version"] == CONFIG_VERSION
        assert kwargs["minor_version"] == CONFIG_MINOR_VERSION
        assert kwargs["data"][CONF_PIN_CODE] == expected_pin

    async def test_future_version_is_refused(self):
        """An entry from a newer release is not touched."""
        hass = MagicMock()
        entry = make_versioned_entry(CONFIG_VERSION + 1, 1, "1234")

        assert await async_migrate_entry(hass, entry) is False
        hass.config_entries.async_update_entry.assert_not_called()


class TestSetupEntry:
    """async_setup_entry() builds the Diagral client."""

    async def test_client_allows_the_longest_read_attempt(self):
        """The client's request timeout covers the coordinator's last attempt."""
        api_cls = MagicMock()
        api_cls.return_value.__aenter__ = AsyncMock(
            side_effect=DiagralAPIError("stop after construction")
        )
        with (
            patch("custom_components.diagral.DiagralConfigData"),
            patch("custom_components.diagral.asdict", return_value=MagicMock()),
            patch("custom_components.diagral.DiagralAPI", api_cls),
            pytest.raises(ConfigEntryNotReady),
        ):
            await async_setup_entry(MagicMock(), MagicMock())

        assert api_cls.call_args.kwargs["request_timeout"] == DIAGRAL_REQUEST_TIMEOUT


def stored_webhook_id(hass: MagicMock) -> str | None:
    """Return the webhook id written to the entry, if any."""
    if not hass.config_entries.async_update_entry.called:
        return None
    return hass.config_entries.async_update_entry.call_args.kwargs["data"].get(
        CONF_WEBHOOK_ID
    )


class TestWebhookLifecycle:
    """The webhook keeps its id, registers locally first, reports failures."""

    async def test_stored_id_is_reused(self, cloud, issues):
        """An entry that already has a webhook id keeps it across restarts."""
        entry = make_entry(OWN_OLD_URL)
        entry.data[CONF_WEBHOOK_ID] = "KEPTWEBHOOKID"
        local = MagicMock()
        result, _ = await run_register(entry, make_api(OWN_OLD_URL), local=local)

        assert result == "KEPTWEBHOOKID"
        assert local.register.call_args.args[3] == "KEPTWEBHOOKID"

    async def test_new_id_is_stored(self, cloud, issues):
        """A first registration stores the id it generated."""
        _, hass = await run_register(make_entry(), make_api(None))

        assert stored_webhook_id(hass) == WEBHOOK_ID

    async def test_current_subscription_is_not_rewritten(self, cloud, issues):
        """A restart with the same id leaves Diagral's subscription alone."""
        entry = make_entry(OWN_NEW_URL)
        entry.data[CONF_WEBHOOK_ID] = WEBHOOK_ID
        api = make_api(OWN_NEW_URL)

        assert (await run_register(entry, api))[0] == WEBHOOK_ID
        api.update_webhook.assert_not_awaited()
        api.register_webhook.assert_not_awaited()

    async def test_local_handler_comes_before_the_subscription(self, cloud, issues):
        """Home Assistant listens before Diagral is told where to send."""
        order = MagicMock()
        api = make_api(None)
        api.register_webhook = AsyncMock(side_effect=lambda **_: order.subscribe())
        local = MagicMock()
        local.register.side_effect = lambda *_: order.listen()

        await run_register(make_entry(), api, local=local)

        assert [c[0] for c in order.mock_calls] == ["listen", "subscribe"]

    @pytest.mark.parametrize(
        "failing",
        ["get_webhook", "register_webhook"],
        ids=["read-subscription", "create-subscription"],
    )
    async def test_diagral_error_is_reported(self, cloud, issues, failing):
        """A Diagral error raises WebhookUnavailable and drops the local handler."""
        api = make_api(None)
        setattr(api, failing, AsyncMock(side_effect=DiagralAPIError("HTTP 503")))
        local = MagicMock()

        with pytest.raises(WebhookUnavailable) as raised:
            await run_register(make_entry(), api, local=local)

        assert raised.value.reason == ISSUE_WEBHOOK_REGISTRATION_FAILED
        # The handler registered first is removed once Diagral fails
        assert [c[0] for c in local.mock_calls][-2:] == ["register", "unregister"]

    async def test_no_url_is_reported(self, cloud, issues):
        """Without an external HTTPS URL, the reason is the missing URL."""
        api = make_api(None)
        with (
            patch("custom_components.diagral.get_url", side_effect=NoURLAvailableError),
            pytest.raises(WebhookUnavailable) as raised,
        ):
            await register_webhook(MagicMock(), make_entry(), api, "test")

        assert raised.value.reason == ISSUE_WEBHOOK_NO_URL
        api.get_webhook.assert_not_awaited()

    async def test_inactive_cloud_is_reported(self, cloud, issues):
        """A Nabu Casa URL without an active subscription is a missing URL."""
        cloud.async_active_subscription.return_value = False

        with pytest.raises(WebhookUnavailable) as raised:
            await run_register(make_entry(), make_api(None), "https://abc.ui.nabu.casa")

        assert raised.value.reason == ISSUE_WEBHOOK_NO_URL


class TestUnregisterResult:
    """unregister_webhook() tells whether the subscription could be handled."""

    async def test_failed_deletion_returns_false(self, cloud):
        """A subscription Diagral refuses to delete is reported."""
        api = make_api(OWN_OLD_URL)
        api.delete_webhook = AsyncMock(side_effect=DiagralAPIError("HTTP 503"))
        with patch("custom_components.diagral.webhook_async_unregister"):
            result = await unregister_webhook(
                MagicMock(), make_entry(OWN_OLD_URL), api, WEBHOOK_ID, "test"
            )

        assert result is False

    async def test_deleted_subscription_returns_true(self, cloud):
        """A deleted subscription is reported as done."""
        with patch("custom_components.diagral.webhook_async_unregister"):
            result = await unregister_webhook(
                MagicMock(),
                make_entry(OWN_OLD_URL),
                make_api(OWN_OLD_URL),
                WEBHOOK_ID,
                "test",
            )

        assert result is True


class TestSetupReportsWebhookFailure:
    """A webhook failure at setup raises a repair instead of failing setup."""

    @pytest.mark.parametrize(
        ("reason", "fixable"),
        [(ISSUE_WEBHOOK_REGISTRATION_FAILED, True), (ISSUE_WEBHOOK_NO_URL, False)],
        ids=["diagral-error", "no-url"],
    )
    async def test_setup_continues_with_a_repair(self, issues, reason, fixable):
        """Polling still works, and the repair says why events cannot arrive."""
        hass = MagicMock()
        hass.config_entries.async_forward_entry_setups = AsyncMock()
        entry = make_entry()
        api_cls = MagicMock()
        api_cls.return_value.__aenter__ = AsyncMock()
        with (
            patch("custom_components.diagral.DiagralConfigData"),
            patch("custom_components.diagral.asdict", return_value=MagicMock()),
            patch("custom_components.diagral.DiagralAPI", api_cls),
            patch("custom_components.diagral.DiagralDataUpdateCoordinator") as coord,
            patch(
                "custom_components.diagral.register_webhook",
                AsyncMock(side_effect=WebhookUnavailable(reason)),
            ),
        ):
            coord.return_value.async_config_entry_first_refresh = AsyncMock()
            assert await async_setup_entry(hass, entry) is True

        kwargs = issues.async_create_issue.call_args.kwargs
        assert issues.async_create_issue.call_args.args[2] == f"{reason}_entry1"
        assert kwargs["translation_key"] == reason
        assert kwargs["is_fixable"] is fixable
        assert entry.runtime_data.webhook_id is None
        coord.return_value.async_set_webhook_status.assert_called_with(
            reason.removeprefix("webhook_")
        )


def make_checked_entry(status: str, subscription: str | None) -> MagicMock:
    """Return a loaded entry whose webhook is in the given state."""
    entry = make_entry(OWN_NEW_URL)
    entry.runtime_data.coordinator.webhook_status = status
    entry.runtime_data.api = make_api(subscription)
    entry.runtime_data.webhook_id = WEBHOOK_ID if status == WEBHOOK_CONNECTED else None
    return entry


async def run_check(entry: MagicMock, register: AsyncMock | None = None) -> AsyncMock:
    """Run the hourly check, with register_webhook replaced."""
    register = register or AsyncMock(return_value=WEBHOOK_ID)
    with patch("custom_components.diagral.register_webhook", register):
        await async_check_webhook(MagicMock(), entry)
    return register


class TestHourlyCheck:
    """The subscription is checked every hour, between restarts."""

    async def test_own_subscription_is_only_read(self, cloud, issues):
        """A subscription still ours costs one read and nothing else."""
        entry = make_checked_entry(WEBHOOK_CONNECTED, OWN_NEW_URL)
        register = await run_check(entry)

        register.assert_not_awaited()
        entry.runtime_data.api.update_webhook.assert_not_awaited()
        entry.runtime_data.coordinator.async_set_webhook_status.assert_not_called()
        issues.async_create_issue.assert_not_called()

    async def test_taken_over_subscription_raises_the_repair(self, cloud, issues):
        """A subscription another installation took since setup is reported."""
        entry = make_checked_entry(WEBHOOK_CONNECTED, OTHER_URL)
        register = await run_check(entry)

        register.assert_not_awaited()
        entry.runtime_data.api.update_webhook.assert_not_awaited()
        assert (
            issues.async_create_issue.call_args.kwargs["translation_key"]
            == ISSUE_WEBHOOK_OWNED_ELSEWHERE
        )
        entry.runtime_data.coordinator.async_set_webhook_status.assert_called_with(
            WEBHOOK_OWNED_ELSEWHERE
        )

    async def test_removed_subscription_is_registered_again(self, cloud, issues):
        """A subscription deleted since setup is created again."""
        entry = make_checked_entry(WEBHOOK_CONNECTED, None)
        register = await run_check(entry)

        assert register.call_args.kwargs.get("take_over", False) is False
        entry.runtime_data.coordinator.async_set_webhook_status.assert_called_with(
            WEBHOOK_CONNECTED
        )

    async def test_unreachable_cloud_changes_nothing(self, cloud, issues):
        """A Diagral outage never drops a working webhook."""
        entry = make_checked_entry(WEBHOOK_CONNECTED, OWN_NEW_URL)
        entry.runtime_data.api.get_webhook = AsyncMock(
            side_effect=DiagralAPIError("HTTP 503", status_code=503)
        )
        register = await run_check(entry)

        register.assert_not_awaited()
        entry.runtime_data.coordinator.async_set_webhook_status.assert_not_called()

    @pytest.mark.parametrize(
        "status",
        [WEBHOOK_REGISTRATION_FAILED, WEBHOOK_NO_URL, WEBHOOK_OWNED_ELSEWHERE],
    )
    async def test_failed_webhook_recovers_by_itself(self, cloud, issues, status):
        """A webhook that could not register is retried, never taken over."""
        entry = make_checked_entry(status, None)
        register = await run_check(entry)

        assert register.call_args.kwargs.get("take_over", False) is False
        assert entry.runtime_data.webhook_id == WEBHOOK_ID
        entry.runtime_data.coordinator.async_set_webhook_status.assert_called_with(
            WEBHOOK_CONNECTED
        )

    async def test_retry_failing_again_keeps_its_reason(self, cloud, issues):
        """A retry that fails again records why, without a new repair."""
        entry = make_checked_entry(WEBHOOK_REGISTRATION_FAILED, None)
        register = AsyncMock(side_effect=WebhookUnavailable(ISSUE_WEBHOOK_NO_URL))
        await run_check(entry, register)

        entry.runtime_data.coordinator.async_set_webhook_status.assert_called_with(
            WEBHOOK_NO_URL
        )

    async def test_unregistered_by_the_user_stays_so(self, cloud, issues):
        """A webhook the user unregistered on purpose is not brought back."""
        entry = make_checked_entry(WEBHOOK_UNREGISTERED, None)
        register = await run_check(entry)

        register.assert_not_awaited()
        entry.runtime_data.api.get_webhook.assert_not_awaited()
