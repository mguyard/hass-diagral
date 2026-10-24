"""Regression tests for safe reads, freshness and registry ownership."""

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.diagral.coordinator import DiagralDataUpdateCoordinator
from pydiagral.exceptions import AuthenticationError, ClientError, ServerError
import pytest

from homeassistant.helpers.update_coordinator import UpdateFailed


@pytest.fixture
def coordinator():
    """Build a coordinator with deterministic cloud responses."""
    result = object.__new__(DiagralDataUpdateCoordinator)
    result.hass = MagicMock()
    result.config_entry = SimpleNamespace(entry_id="entry-one")
    result.last_success = datetime(2025, 1, 1, tzinfo=UTC)
    result.consecutive_failures = 0
    result.communication_status = "connected"
    result.last_error = None
    result.data = {"previous": "snapshot"}
    alarm_config = SimpleNamespace(
        groups=[],
        alarm=SimpleNamespace(
            central=SimpleNamespace(
                serial="serial",
                firmwares=SimpleNamespace(central="1", centralradio="2"),
            )
        ),
    )
    result.api = SimpleNamespace(
        get_configuration=AsyncMock(return_value=alarm_config),
        get_devices_info=AsyncMock(return_value=SimpleNamespace()),
        get_system_status=AsyncMock(
            return_value=SimpleNamespace(status="off", activated_groups=[])
        ),
        get_anomalies=AsyncMock(return_value=None),
    )
    result._update_device_info = AsyncMock()
    return result


async def test_transient_server_error_recovers_with_one_read_retry(coordinator):
    """Recover from one transient failure and record the fresh observation."""
    previous_success = coordinator.last_success
    configuration = coordinator.api.get_configuration.return_value
    coordinator.api.get_configuration.side_effect = [
        ServerError("private cloud body"),
        configuration,
    ]
    with patch(
        "custom_components.diagral.coordinator.asyncio.sleep", new_callable=AsyncMock
    ) as delay:
        data = await coordinator._async_update_data()
    assert coordinator.api.get_configuration.await_count == 2
    delay.assert_awaited_once()
    assert data["system_status"].status == "off"
    assert coordinator.last_success > previous_success
    assert coordinator.consecutive_failures == 0
    assert coordinator.communication_status == "connected"
    assert coordinator.last_error is None


@pytest.mark.parametrize(
    "error", [ServerError("private cloud body"), ClientError("private endpoint")]
)
async def test_terminal_failure_preserves_snapshot_but_raises(coordinator, error):
    """Keep the prior snapshot while publishing failure without private details."""
    coordinator.api.get_configuration.side_effect = error
    previous_success = coordinator.last_success
    previous_data = coordinator.data
    with (
        patch(
            "custom_components.diagral.coordinator.asyncio.sleep",
            new_callable=AsyncMock,
        ),
        pytest.raises(UpdateFailed) as raised,
    ):
        await coordinator._async_update_data()
    assert coordinator.api.get_configuration.await_count == 2
    assert coordinator.data is previous_data
    assert coordinator.last_success == previous_success
    assert coordinator.consecutive_failures == 1
    assert coordinator.communication_status == "unavailable"
    assert "private" not in str(raised.value)
    assert "private" not in coordinator.last_error


async def test_authentication_error_is_not_retried(coordinator):
    """Fail immediately when retrying cannot repair invalid credentials."""
    coordinator.api.get_configuration.side_effect = AuthenticationError("secret PIN")
    with (
        patch(
            "custom_components.diagral.coordinator.asyncio.sleep",
            new_callable=AsyncMock,
        ) as delay,
        pytest.raises(UpdateFailed, match="authentication_failed"),
    ):
        await coordinator._async_update_data()
    coordinator.api.get_configuration.assert_awaited_once()
    delay.assert_not_awaited()


async def test_invalid_status_never_counts_as_success(coordinator):
    """Reject missing status data without advancing the success timestamp."""
    coordinator.api.get_system_status.return_value = None
    previous_success = coordinator.last_success
    with pytest.raises(UpdateFailed, match="invalid_response"):
        await coordinator._async_update_data()
    assert coordinator.last_success == previous_success
    assert coordinator.consecutive_failures == 1


async def test_recovery_resets_failure_diagnostics(coordinator):
    """Clear failure counters and error status after a successful refresh."""
    coordinator.consecutive_failures = 2
    coordinator.communication_status = "unavailable"
    coordinator.last_error = "network_error"
    await coordinator._async_update_data()
    assert coordinator.consecutive_failures == 0
    assert coordinator.communication_status == "connected"
    assert coordinator.last_error is None


async def test_registry_lookup_is_scoped_to_config_entry(coordinator):
    """Use the modern registry API with the owning config entry identifier."""
    config = coordinator.api.get_configuration.return_value
    registry = MagicMock()
    registry.async_get_device_by_identifier.return_value = SimpleNamespace(
        id="device-one", sw_version=None
    )
    with patch(
        "custom_components.diagral.coordinator.dr.async_get", return_value=registry
    ):
        await DiagralDataUpdateCoordinator._update_device_info(coordinator, config)
    registry.async_get_device_by_identifier.assert_called_once_with(
        identifier=("diagral", "serial"), config_entry_id="entry-one"
    )
    registry.async_get_device.assert_not_called()
    registry.async_update_device.assert_called_once_with(
        "device-one", sw_version="1 / Radio:2"
    )


@pytest.mark.parametrize("config_entries", [None, {"entry-one"}, {"another-entry"}])
async def test_legacy_registry_only_updates_owned_devices(coordinator, config_entries):
    """Support old HA registries without updating a different entry's device."""
    config = coordinator.api.get_configuration.return_value
    device = (
        None
        if config_entries is None
        else SimpleNamespace(
            id="device-one", sw_version=None, config_entries=config_entries
        )
    )
    registry = SimpleNamespace(
        async_get_device=MagicMock(return_value=device),
        async_update_device=MagicMock(),
    )
    with patch(
        "custom_components.diagral.coordinator.dr.async_get", return_value=registry
    ):
        await DiagralDataUpdateCoordinator._update_device_info(coordinator, config)
    registry.async_get_device.assert_called_once_with(
        identifiers={("diagral", "serial")}
    )
    if config_entries == {"entry-one"}:
        registry.async_update_device.assert_called_once_with(
            "device-one", sw_version="1 / Radio:2"
        )
    else:
        registry.async_update_device.assert_not_called()


async def test_framework_publishes_repeated_failures_and_recovery(coordinator):
    """Diagnostic listeners receive every failure, not only availability edges."""
    hass = MagicMock()
    hass.loop = asyncio.get_running_loop()
    hass.is_stopping = False
    live = DiagralDataUpdateCoordinator(hass, coordinator.api)
    live.update_interval = None
    observations = []
    live.async_add_listener(
        lambda: observations.append(
            (
                live.last_update_success,
                live.consecutive_failures,
                live.communication_status,
            )
        )
    )
    coordinator.api.get_configuration.side_effect = ServerError("outage")
    with patch(
        "custom_components.diagral.coordinator.asyncio.sleep", new_callable=AsyncMock
    ):
        await live.async_refresh()
        await live.async_refresh()
    coordinator.api.get_configuration.side_effect = None
    await live.async_refresh()
    assert observations == [
        (False, 1, "unavailable"),
        (False, 2, "unavailable"),
        (True, 0, "connected"),
    ]


async def test_cancelled_confirmation_publishes_failure_even_if_base_already_failed(
    coordinator,
):
    """Notify listeners of a safe timeout error even while already unavailable."""
    hass = MagicMock()
    hass.loop = asyncio.get_running_loop()
    live = DiagralDataUpdateCoordinator(hass, coordinator.api)
    live.update_interval = None
    live.last_update_success = False
    listener = MagicMock()
    live.async_add_listener(listener)
    live.async_set_update_error(TimeoutError("private URL"))
    assert live.communication_status == "unavailable"
    assert live.last_error == "timeout"
    assert live.consecutive_failures == 1
    assert "private" not in str(live.last_exception)
    listener.assert_called_once()
