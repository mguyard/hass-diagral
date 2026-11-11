"""Secondary anomaly reads must not decide the central's availability."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from custom_components.diagral.coordinator import DiagralDataUpdateCoordinator
from custom_components.diagral.sensor import SENSORS, DiagralSensor
from pydiagral.exceptions import ServerError
from pydiagral.models import Anomalies, AnomalyDetail, AnomalyName, DeviceList
import pytest


@pytest.fixture
async def coordinator():
    """Use fake SDK reads and track every task for deterministic cleanup."""
    instance = object.__new__(DiagralDataUpdateCoordinator)
    instance.hass = MagicMock()
    instance.data = None
    instance.last_update_success = True
    instance.last_success = None
    instance.last_error = None
    instance.anomalies_available = False
    instance._shutdown_requested = False
    instance._anomalies_error = None
    instance._anomalies_task = None
    instance.api = MagicMock()
    instance.api.ping = AsyncMock()
    instance.api.get_configuration = AsyncMock(return_value=SimpleNamespace(groups=[]))
    instance.api.get_devices_info = AsyncMock(
        return_value=DeviceList(
            cameras=[], commands=[], sensors=[], sirens=[], transmitters=[]
        )
    )
    instance.api.get_system_status = AsyncMock(
        return_value=SimpleNamespace(status="off", activated_groups=[])
    )
    instance.api.get_anomalies = AsyncMock(return_value={})
    instance._update_device_info = AsyncMock()
    instance.async_update_listeners = MagicMock()
    instance.async_set_updated_data = MagicMock()
    tasks = []

    def create_task(_hass, coroutine, _name, **kwargs):
        assert kwargs.get("eager_start") is False
        task = asyncio.create_task(coroutine)
        tasks.append(task)
        return task

    instance.config_entry = SimpleNamespace(
        async_create_background_task=MagicMock(side_effect=create_task),
        async_create_task=MagicMock(side_effect=create_task),
    )
    yield instance
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)


async def wait_for_secondary(coordinator):
    """Wait for a scheduled read without depending on task callback ordering."""
    task = coordinator._anomalies_task
    assert task is not None
    await task


class TestIndependentAnomalyRead:
    """A slow or failed secondary read cannot discard a valid central status."""

    async def test_first_core_refresh_returns_while_anomalies_are_blocked(
        self, coordinator
    ):
        """A hanging anomaly request must not delay the first usable status."""
        release = asyncio.Event()

        async def blocked():
            await release.wait()
            return {}

        coordinator.api.get_anomalies.side_effect = blocked
        data = await asyncio.wait_for(coordinator._async_update_data(), timeout=0.2)
        assert data["system_status"].status == "off"
        assert "anomalies" in data
        assert coordinator.anomalies_available is False
        assert coordinator._anomalies_task is not None
        assert not coordinator._anomalies_task.done()
        release.set()
        await wait_for_secondary(coordinator)
        assert coordinator.anomalies_available is True

    @pytest.mark.parametrize(
        "error",
        [ServerError("HTTP 500"), TimeoutError()],
        ids=["server-error", "timeout"],
    )
    async def test_secondary_failure_preserves_successful_core(
        self, coordinator, error
    ):
        """An anomaly error does not turn a successful primary read into failure."""
        coordinator.api.get_anomalies.side_effect = error
        data = await coordinator._async_update_data()
        await wait_for_secondary(coordinator)
        assert data["system_status"].status == "off"
        assert coordinator.last_update_success is True
        assert coordinator.last_error is None
        assert coordinator.anomalies_available is False
        coordinator.async_set_updated_data.assert_not_called()

    async def test_secondary_success_never_revives_a_failed_core(self, coordinator):
        """Fresh anomaly data cannot certify an unavailable central status."""
        coordinator.data = {
            "system_status": SimpleNamespace(status="off"),
            "anomalies": None,
        }
        coordinator.last_update_success = False
        coordinator.last_error = "TimeoutError"
        await coordinator._async_refresh_anomalies()
        assert coordinator.anomalies_available is True
        assert coordinator.last_update_success is False
        assert coordinator.last_error == "TimeoutError"
        coordinator.async_set_updated_data.assert_not_called()

    async def test_secondary_result_preserves_a_newer_command_status(self, coordinator):
        """A late response must merge with the latest command result."""
        started = asyncio.Event()
        release = asyncio.Event()
        fault = Anomalies(
            created_at=None,
            sensors=[
                AnomalyDetail(
                    index=1, anomaly_names=[AnomalyName(id=1, name="lowBattery")]
                )
            ],
        )

        async def blocked():
            started.set()
            await release.wait()
            return fault

        coordinator.data = {
            "system_status": SimpleNamespace(status="off"),
            "anomalies": None,
        }
        coordinator.api.get_anomalies.side_effect = blocked
        coordinator._async_schedule_anomalies_refresh()
        await started.wait()
        newer_status = SimpleNamespace(status="group")
        coordinator.data = {**coordinator.data, "system_status": newer_status}
        release.set()
        await wait_for_secondary(coordinator)
        assert coordinator.data["system_status"] is newer_status
        assert coordinator.data["anomalies"] is fault

    async def test_scheduling_is_singleflight_and_cancel_does_not_publish(
        self, coordinator
    ):
        """Overlapping refreshes share one task and unload cancellation is silent."""
        started = asyncio.Event()

        async def blocked():
            started.set()
            await asyncio.Event().wait()

        coordinator.data = {
            "system_status": SimpleNamespace(status="off"),
            "anomalies": None,
        }
        coordinator.api.get_anomalies.side_effect = blocked
        coordinator._async_schedule_anomalies_refresh()
        task = coordinator._anomalies_task
        await started.wait()
        coordinator._async_schedule_anomalies_refresh()
        assert coordinator._anomalies_task is task
        coordinator.api.get_anomalies.assert_awaited_once()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert coordinator.data["anomalies"] is None
        assert coordinator.anomalies_available is False
        coordinator.async_update_listeners.assert_not_called()

    async def test_zero_result_failure_and_recovery_have_distinct_availability(
        self, coordinator
    ):
        """A successful empty result alone means no known faults."""
        coordinator.data = {
            "system_status": SimpleNamespace(status="off"),
            "anomalies": None,
        }
        await coordinator._async_refresh_anomalies()
        assert coordinator.data["anomalies"] == {}
        assert coordinator.anomalies_available is True
        coordinator.api.get_anomalies.side_effect = ServerError("HTTP 500")
        await coordinator._async_refresh_anomalies()
        assert coordinator.anomalies_available is False
        coordinator.api.get_anomalies.side_effect = None
        await coordinator._async_refresh_anomalies()
        assert coordinator.anomalies_available is True
        assert coordinator.data["anomalies"] == {}

    async def test_shutdown_prevents_new_reads(self, coordinator):
        """Unloading must not start another secondary API read."""
        coordinator.data = {"anomalies": None}
        coordinator._shutdown_requested = True
        coordinator._async_schedule_anomalies_refresh()
        assert coordinator._anomalies_task is None
        coordinator.api.get_anomalies.assert_not_awaited()

    async def test_result_after_shutdown_is_not_published(self, coordinator):
        """A response arriving after unload must not update removed entities."""
        started = asyncio.Event()
        release = asyncio.Event()

        async def blocked():
            started.set()
            await release.wait()
            return {}

        coordinator.data = {"anomalies": None}
        coordinator.api.get_anomalies.side_effect = blocked
        coordinator._async_schedule_anomalies_refresh()
        await started.wait()
        coordinator._shutdown_requested = True
        release.set()
        await wait_for_secondary(coordinator)
        assert coordinator.data["anomalies"] is None
        assert coordinator.anomalies_available is False
        coordinator.async_update_listeners.assert_not_called()


class TestAnomalySensorAvailability:
    """Missing reads are unavailable, never a fabricated zero-fault result."""

    @pytest.mark.parametrize(
        ("key", "core_ok", "anomalies_ok", "expected"),
        [
            ("anomalies", True, False, False),
            ("anomalies", True, True, True),
            ("anomalies", False, True, False),
            ("active_groups", True, False, True),
            ("active_groups", False, True, False),
        ],
        ids=[
            "secondary-failed",
            "both-good",
            "core-failed",
            "groups-independent",
            "groups-core-failed",
        ],
    )
    def test_only_anomaly_sensor_requires_secondary_success(
        self, key, core_ok, anomalies_ok, expected
    ):
        """Anomalies need both reads; active groups only need the central read."""
        sensor = object.__new__(DiagralSensor)
        sensor.entity_description = next(item for item in SENSORS if item.key == key)
        sensor.coordinator = SimpleNamespace(
            last_update_success=core_ok, anomalies_available=anomalies_ok
        )
        assert sensor.available is expected

    def test_failed_read_does_not_replace_existing_faults_with_zero(self):
        """The last details survive a failure while availability reports it."""
        sensor = object.__new__(DiagralSensor)
        sensor.entity_description = next(
            item for item in SENSORS if item.key == "anomalies"
        )
        sensor._attr_name = "Anomalies"
        sensor._attr_native_value = 1
        sensor._attr_extra_state_attributes = {"fault_count": 2}
        sensor.coordinator = SimpleNamespace(
            anomalies_available=False,
            last_update_success=True,
            data={
                "alarm_config": SimpleNamespace(groups=[]),
                "anomalies": None,
                "groups": [],
                "devices_infos": None,
            },
        )
        sensor._update_from_coordinator()
        assert sensor._attr_native_value == 1
        assert sensor._attr_extra_state_attributes == {"fault_count": 2}
