"""Tests for coordinator.py — progressive retries of Diagral reads."""

import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock, call, patch

from custom_components.diagral import coordinator as coordinator_module
from custom_components.diagral.const import (
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
        """Attempts run under 30, 45 then 60 s, inside the overall budget."""
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

    def test_webhook_status_and_reception_notify_entities(self):
        """Webhook state changes reach the entities at once."""
        coordinator = make_coordinator()
        coordinator.async_update_listeners = MagicMock()

        coordinator.async_set_webhook_status("connected")
        coordinator.async_webhook_received()

        assert coordinator.webhook_status == "connected"
        assert coordinator.last_webhook is not None
        assert coordinator.async_update_listeners.call_count == 2
