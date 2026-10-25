"""Tests for coordinator.py — progressive retries of Diagral reads."""

import asyncio
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, call, patch

from custom_components.diagral import coordinator as coordinator_module
from custom_components.diagral.const import (
    PING_TIMEOUT,
    READ_ATTEMPT_TIMEOUTS,
    READ_RETRY_BUDGET,
    READ_RETRY_PAUSES,
)
from custom_components.diagral.coordinator import DiagralDataUpdateCoordinator
from pydiagral.exceptions import (
    AuthenticationError,
    ClientError,
    DiagralAPIError,
    ServerError,
    ValidationError,
)
import pytest

from homeassistant.helpers.update_coordinator import UpdateFailed

OLD_DATA = {"system_status": "old"}

TRANSIENT_ERRORS = [
    ServerError("HTTP 500"),
    DiagralAPIError("HTTP 502", status_code=502),
    ClientError("Network error"),
    TimeoutError(),
]
TRANSIENT_IDS = ["server-error", "bad-gateway", "network", "timeout"]


def make_coordinator(data=OLD_DATA):
    """Return a coordinator whose API answers with valid data."""
    coordinator = object.__new__(DiagralDataUpdateCoordinator)
    coordinator.data = data
    coordinator.api = MagicMock()
    coordinator.api.ping = AsyncMock(return_value=SimpleNamespace(status="we're alive"))
    coordinator.api.get_configuration = AsyncMock(return_value=MagicMock(groups=[]))
    coordinator.api.get_devices_info = AsyncMock(return_value=MagicMock())
    coordinator.api.get_system_status = AsyncMock(return_value=MagicMock())
    coordinator.api.get_anomalies = AsyncMock(return_value={})
    coordinator._update_device_info = AsyncMock()
    return coordinator


@pytest.fixture
def sleep():
    """Skip the pauses between attempts and record them."""
    with patch.object(coordinator_module.asyncio, "sleep", AsyncMock()) as mock:
        yield mock


class TestRetries:
    """Tests for the retry policy of _async_update_data()."""

    async def test_success_needs_no_retry(self, sleep):
        """A successful read returns fresh data at the first attempt."""
        coordinator = make_coordinator()
        data = await coordinator._async_update_data()
        assert data["system_status"] is not OLD_DATA["system_status"]
        assert coordinator.api.get_system_status.await_count == 1
        sleep.assert_not_awaited()

    @pytest.mark.parametrize("error", TRANSIENT_ERRORS, ids=TRANSIENT_IDS)
    async def test_transient_error_is_retried(self, sleep, error):
        """A transient failure is retried after the first pause."""
        coordinator = make_coordinator()
        coordinator.api.get_system_status.side_effect = [error, MagicMock()]
        await coordinator._async_update_data()
        assert coordinator.api.get_system_status.await_count == 2
        sleep.assert_awaited_once_with(READ_RETRY_PAUSES[0])

    async def test_persistent_failure_uses_every_attempt(self, sleep):
        """Each attempt is used, with growing pauses, before giving up."""
        coordinator = make_coordinator()
        coordinator.api.get_system_status.side_effect = ServerError("HTTP 503")
        with pytest.raises(UpdateFailed):
            await coordinator._async_update_data()
        assert coordinator.api.get_system_status.await_count == len(
            READ_ATTEMPT_TIMEOUTS
        )
        assert sleep.await_args_list == [call(pause) for pause in READ_RETRY_PAUSES]

    @pytest.mark.parametrize(
        "error",
        [
            AuthenticationError("Unauthorized"),
            ValidationError("Invalid JSON response"),
            DiagralAPIError("HTTP 404", status_code=404),
        ],
        ids=["auth", "validation", "not-found"],
    )
    async def test_permanent_error_is_not_retried(self, sleep, error):
        """An error that a retry cannot fix fails at once."""
        coordinator = make_coordinator()
        coordinator.api.get_system_status.side_effect = error
        with pytest.raises(UpdateFailed):
            await coordinator._async_update_data()
        assert coordinator.api.get_system_status.await_count == 1
        sleep.assert_not_awaited()

    async def test_first_refresh_is_not_retried(self, sleep):
        """Setup fails fast: Home Assistant retries a failed setup itself."""
        coordinator = make_coordinator(data=None)
        coordinator.api.get_system_status.side_effect = ServerError("HTTP 500")
        with pytest.raises(UpdateFailed):
            await coordinator._async_update_data()
        assert coordinator.api.get_system_status.await_count == 1
        sleep.assert_not_awaited()

    async def test_invalid_payload_keeps_old_data(self, sleep):
        """A payload without a status keeps the previous data, without retry."""
        coordinator = make_coordinator()
        coordinator.api.get_system_status.return_value = None
        assert await coordinator._async_update_data() is OLD_DATA
        sleep.assert_not_awaited()


class TestDeadlines:
    """Tests for the per-attempt deadlines and the overall budget."""

    async def test_each_attempt_gets_a_longer_deadline(self, sleep):
        """After the ping, attempts run under 30, 45 then 60 s, inside the budget."""
        coordinator = make_coordinator()
        coordinator.api.get_system_status.side_effect = ServerError("HTTP 500")
        real_timeout = asyncio.timeout
        with (
            patch.object(
                coordinator_module.asyncio, "timeout", side_effect=real_timeout
            ) as timeout,
            pytest.raises(UpdateFailed),
        ):
            await coordinator._async_update_data()
        assert [args.args[0] for args in timeout.call_args_list] == [
            PING_TIMEOUT,
            READ_RETRY_BUDGET,
            *READ_ATTEMPT_TIMEOUTS,
        ]

    async def test_slow_attempt_is_cut_and_retried(self, sleep):
        """An attempt that outlives its deadline is abandoned and retried."""
        coordinator = make_coordinator()
        attempts = []

        async def hang_first_attempt():
            attempts.append(None)
            if len(attempts) == 1:
                await asyncio.Event().wait()
            return MagicMock()

        coordinator.api.get_system_status.side_effect = hang_first_attempt
        with patch.object(coordinator_module, "READ_ATTEMPT_TIMEOUTS", (0.01, 0.01)):
            await coordinator._async_update_data()
        assert coordinator.api.get_system_status.await_count == 2

    async def test_budget_bounds_the_whole_refresh(self, sleep):
        """Retries never outlast the overall budget."""
        coordinator = make_coordinator()

        async def hang():
            await asyncio.Event().wait()

        coordinator.api.get_system_status.side_effect = hang
        with (
            patch.object(coordinator_module, "READ_ATTEMPT_TIMEOUTS", (10, 10)),
            patch.object(coordinator_module, "READ_RETRY_BUDGET", 0.01),
            pytest.raises(UpdateFailed),
        ):
            await coordinator._async_update_data()
        assert coordinator.api.get_system_status.await_count == 1


class TestOutageLogging:
    """An outage is logged once by Home Assistant, not on every poll."""

    async def test_retries_stay_out_of_the_log(self, sleep, caplog):
        """Retrying a failed read writes nothing at INFO or above."""
        caplog.set_level(logging.INFO, logger="custom_components.diagral")
        coordinator = make_coordinator()
        coordinator.api.get_system_status.side_effect = ServerError("HTTP 503")
        with pytest.raises(UpdateFailed):
            await coordinator._async_update_data()

        assert not caplog.records

    async def test_invalid_payload_stays_out_of_the_log(self, sleep, caplog):
        """Keeping the old data on an invalid payload writes nothing either."""
        caplog.set_level(logging.INFO, logger="custom_components.diagral")
        coordinator = make_coordinator()
        coordinator.api.get_system_status.return_value = None
        await coordinator._async_update_data()

        assert not caplog.records


class TestHealth:
    """The coordinator keeps what the diagnostic entities report."""

    async def test_success_and_failure_are_recorded(self, sleep):
        """A read records its time on success, the error kind on failure."""
        coordinator = make_coordinator()
        await coordinator._async_update_data()
        assert coordinator.last_success is not None
        assert coordinator.last_error is None

        coordinator.api.get_system_status.side_effect = ServerError("HTTP 503")
        with pytest.raises(UpdateFailed):
            await coordinator._async_update_data()
        assert coordinator.last_error == "ServerError"

    async def test_answered_ping_marks_the_cloud_reachable(self, sleep):
        """Each refresh pings the cloud, whatever the credentials."""
        coordinator = make_coordinator()

        await coordinator._async_update_data()

        coordinator.api.ping.assert_awaited_once()
        assert coordinator.cloud_reachable is True

    @pytest.mark.parametrize(
        "error",
        [ServerError("HTTP 503"), ClientError("Network error")],
        ids=["server-error", "network"],
    )
    async def test_failed_ping_does_not_stop_the_reads(self, sleep, error):
        """An unanswered ping is recorded, and the data is still read."""
        coordinator = make_coordinator()
        coordinator.api.ping.side_effect = error

        await coordinator._async_update_data()

        assert coordinator.cloud_reachable is False
        coordinator.api.get_system_status.assert_awaited()

    async def test_hung_ping_is_cut_short(self, sleep):
        """A ping that never answers gives up instead of holding the refresh."""
        coordinator = make_coordinator()

        async def hang() -> None:
            await asyncio.Event().wait()

        coordinator.api.ping.side_effect = hang
        with patch.object(coordinator_module, "PING_TIMEOUT", 0.01):
            await coordinator._async_update_data()

        assert coordinator.cloud_reachable is False

    def test_webhook_status_and_reception_notify_entities(self):
        """Webhook state changes reach the entities at once."""
        coordinator = make_coordinator()
        coordinator.async_update_listeners = MagicMock()

        coordinator.async_set_webhook_status("connected")
        coordinator.async_webhook_received()

        assert coordinator.webhook_status == "connected"
        assert coordinator.last_webhook is not None
        assert coordinator.async_update_listeners.call_count == 2


def make_device_coordinator(sw_version: str | None) -> tuple[MagicMock, MagicMock]:
    """Return a coordinator holding a central and the registry it reads."""
    coordinator = object.__new__(DiagralDataUpdateCoordinator)
    coordinator.hass = MagicMock()
    coordinator.config_entry = MagicMock(entry_id="entry1")
    central = SimpleNamespace(
        serial="SERIAL123",
        firmwares=SimpleNamespace(central="2.1", centralradio="1.4"),
    )
    coordinator.data = {
        "alarm_config": SimpleNamespace(alarm=SimpleNamespace(central=central))
    }
    registry = MagicMock()
    registry.async_get_device_by_identifier.return_value = (
        None
        if sw_version is None
        else SimpleNamespace(id="device1", sw_version=sw_version)
    )
    return coordinator, registry


class TestDeviceInfo:
    """The central's firmware follows what Diagral reports."""

    async def test_device_is_looked_up_within_its_config_entry(self):
        """The lookup is scoped to the entry, never the deprecated global one."""
        coordinator, registry = make_device_coordinator("2.1 / Radio:1.4")
        with patch.object(coordinator_module.dr, "async_get", return_value=registry):
            await coordinator._update_device_info()

        registry.async_get_device_by_identifier.assert_called_once_with(
            (coordinator_module.DOMAIN, "SERIAL123"), "entry1"
        )
        registry.async_get_device.assert_not_called()

    @pytest.mark.parametrize(
        ("sw_version", "expected"),
        [
            ("2.0 / Radio:1.4", [call("device1", sw_version="2.1 / Radio:1.4")]),
            ("2.1 / Radio:1.4", []),
            (None, []),
        ],
        ids=["firmware-changed", "firmware-unchanged", "no-device"],
    )
    async def test_firmware_is_updated_only_when_it_changed(self, sw_version, expected):
        """A new firmware is written once; an unknown device is left alone."""
        coordinator, registry = make_device_coordinator(sw_version)
        with patch.object(coordinator_module.dr, "async_get", return_value=registry):
            await coordinator._update_device_info()

        assert registry.async_update_device.call_args_list == expected
