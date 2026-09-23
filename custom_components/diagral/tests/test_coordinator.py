"""Tests for DiagralDataUpdateCoordinator resilience to Diagral outages.

The Diagral cloud regularly answers 500/503 for a few minutes. These tests
cover _async_update_data() without any Home Assistant plumbing: the
coordinator is built with object.__new__ and only the attributes the method
touches are set.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.helpers.update_coordinator import UpdateFailed
from pydiagral.exceptions import AuthenticationError, ServerError

from custom_components.diagral.const import MAX_CONSECUTIVE_SERVER_ERRORS
from custom_components.diagral.coordinator import DiagralDataUpdateCoordinator


def make_coordinator(data=None, api=None) -> DiagralDataUpdateCoordinator:
    """Return a coordinator with mocked dependencies.

    Bypasses __init__ so that no HomeAssistant instance is required.
    """
    coordinator = object.__new__(DiagralDataUpdateCoordinator)
    coordinator.api = api if api is not None else make_api()
    coordinator.data = data
    coordinator._consecutive_server_errors = 0
    return coordinator


def make_api(**overrides) -> MagicMock:
    """Return a DiagralAPI mock whose calls all succeed."""
    api = MagicMock()
    alarm_config = MagicMock()
    alarm_config.groups = []
    api.get_configuration = AsyncMock(return_value=alarm_config)
    api.get_devices_info = AsyncMock(return_value=MagicMock())
    api.get_system_status = AsyncMock(return_value=MagicMock())
    api.get_anomalies = AsyncMock(return_value=MagicMock())
    for name, value in overrides.items():
        setattr(api, name, value)
    return api


PREVIOUS_DATA = {"system_status": "armed", "alarm_config": MagicMock()}


class TestServerErrorTolerance:
    """A transient 5xx must not take the entities down."""

    async def test_first_server_error_keeps_last_known_data(self):
        """The previous payload is served instead of raising UpdateFailed."""
        api = make_api(get_configuration=AsyncMock(side_effect=ServerError("Internal Server Error")))
        coordinator = make_coordinator(data=PREVIOUS_DATA, api=api)

        assert await coordinator._async_update_data() == PREVIOUS_DATA
        assert coordinator._consecutive_server_errors == 1

    async def test_tolerated_failures_are_counted(self):
        """Every tolerated failure increments the counter."""
        api = make_api(get_configuration=AsyncMock(side_effect=ServerError("Internal Server Error")))
        coordinator = make_coordinator(data=PREVIOUS_DATA, api=api)

        for expected in range(1, MAX_CONSECUTIVE_SERVER_ERRORS + 1):
            assert await coordinator._async_update_data() == PREVIOUS_DATA
            assert coordinator._consecutive_server_errors == expected

    async def test_failure_past_the_threshold_raises(self):
        """Once the outage lasts, the entities must become unavailable."""
        api = make_api(get_configuration=AsyncMock(side_effect=ServerError("Internal Server Error")))
        coordinator = make_coordinator(data=PREVIOUS_DATA, api=api)

        for _ in range(MAX_CONSECUTIVE_SERVER_ERRORS):
            await coordinator._async_update_data()

        with pytest.raises(UpdateFailed, match="Diagral service unavailable"):
            await coordinator._async_update_data()

    async def test_server_error_without_previous_data_raises(self):
        """Nothing to keep on the first refresh, so the setup must fail."""
        api = make_api(get_configuration=AsyncMock(side_effect=ServerError("Internal Server Error")))
        coordinator = make_coordinator(data=None, api=api)

        with pytest.raises(UpdateFailed):
            await coordinator._async_update_data()


class TestCounterReset:
    """The tolerance must apply to consecutive failures only."""

    async def test_successful_update_resets_the_counter(self):
        """A successful poll clears the failure streak."""
        coordinator = make_coordinator(data=PREVIOUS_DATA)
        coordinator._consecutive_server_errors = MAX_CONSECUTIVE_SERVER_ERRORS

        with patch.object(
            DiagralDataUpdateCoordinator, "_update_device_info", AsyncMock()
        ):
            await coordinator._async_update_data()

        assert coordinator._consecutive_server_errors == 0

    async def test_other_api_error_resets_the_counter(self):
        """A non-5xx error is a different problem and clears the streak."""
        api = make_api(get_configuration=AsyncMock(side_effect=AuthenticationError("Unauthorized")))
        coordinator = make_coordinator(data=PREVIOUS_DATA, api=api)
        coordinator._consecutive_server_errors = 1

        with pytest.raises(UpdateFailed, match="Error communicating with API"):
            await coordinator._async_update_data()

        assert coordinator._consecutive_server_errors == 0


class TestOtherErrorsAreNotTolerated:
    """Only service outages are worth serving stale data for."""

    async def test_authentication_error_raises_immediately(self):
        """An expired token must surface at once, not be hidden for 15 min."""
        api = make_api(get_configuration=AsyncMock(side_effect=AuthenticationError("Unauthorized")))
        coordinator = make_coordinator(data=PREVIOUS_DATA, api=api)

        with pytest.raises(UpdateFailed, match="Error communicating with API"):
            await coordinator._async_update_data()
