"""DataUpdateCoordinator for Diagral integration."""

import asyncio
from datetime import datetime, timedelta
import logging
from typing import TYPE_CHECKING, Any

from pydiagral.api import DiagralAPI
from pydiagral.exceptions import ClientError, DiagralAPIError, ServerError
from pydiagral.models import AlarmConfiguration, DeviceInfos, SystemStatus

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
import homeassistant.util.dt as dt_util

from .const import (
    BRAND,
    DEFAULT_SCAN_INTERVAL,
    DIAGRAL_REQUEST_TIMEOUT,
    DOMAIN,
    HTTP_SERVER_ERROR,
    PING_TIMEOUT,
    READ_ATTEMPT_TIMEOUTS,
    READ_RETRY_BUDGET,
    READ_RETRY_PAUSES,
)

if TYPE_CHECKING:
    from . import DiagralConfigEntry

_LOGGER = logging.getLogger(__name__)


def is_transient_error(err: Exception) -> bool:
    """Return whether a failed read may succeed when retried."""
    if isinstance(err, TimeoutError | ClientError | ServerError):
        return True
    status_code = getattr(err, "status_code", None)
    return status_code is not None and status_code >= HTTP_SERVER_ERROR


def fallback_connection_status(
    coordinator: DiagralDataUpdateCoordinator,
) -> bool | None:
    """Include backend changes made by a command's read-only preflight."""
    if getattr(coordinator.api, "supports_failover", False) is True:
        return coordinator.api.fallback_api_connected
    return coordinator.fallback_api_connected


def active_api_status(coordinator: DiagralDataUpdateCoordinator) -> str | None:
    """Name only a backend whose authenticated central read succeeded."""
    api = coordinator.api
    if api.active_api == "emerald" and api.primary_api_connected is True:
        return "emerald"
    if api.active_api == "topaze" and api.fallback_api_connected is True:
        return "topaze"
    return None


class DiagralDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching Diagral data."""

    config_entry: DiagralConfigEntry

    def __init__(
        self, hass: HomeAssistant, config_entry: DiagralConfigEntry, api: DiagralAPI
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=config_entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
        )
        self.api = api
        self.last_success: datetime | None = None
        self.last_error: str | None = None
        self.webhook_status: str | None = None
        self.last_webhook: datetime | None = None
        self.cloud_reachable: bool | None = None
        self.fallback_api_connected: bool | None = None
        self._cloud_ping_task: asyncio.Task[None] | None = None
        self.anomalies_available = False
        self._anomalies_error: str | None = None
        self._anomalies_task: asyncio.Task[None] | None = None

    @callback
    def async_set_webhook_status(self, status: str) -> None:
        """Record the state of the webhook and refresh the entities."""
        self.webhook_status = status
        self.async_update_listeners()

    @callback
    def async_webhook_received(self) -> None:
        """Record that a notification arrived and refresh the entities."""
        self.last_webhook = dt_util.utcnow()
        self.async_update_listeners()

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from Diagral API, retrying transient failures."""
        _LOGGER.debug("Updating data with API instance: %s", id(self.api))
        automatic_failover = getattr(self.api, "supports_failover", False) is True
        if automatic_failover:
            self._async_schedule_cloud_ping()
        else:
            self.cloud_reachable = await self._async_ping()
        # A failed first refresh fails the setup, which Home Assistant retries.
        timeouts = READ_ATTEMPT_TIMEOUTS if self.data else READ_ATTEMPT_TIMEOUTS[:1]
        try:
            async with asyncio.timeout(READ_RETRY_BUDGET):
                if automatic_failover:
                    # The SDK bounds both backends; do not replay that pipeline.
                    updated_data = await self._async_read()
                else:
                    updated_data = await self._async_read_with_retries(timeouts)
        except TimeoutError as err:
            if automatic_failover:
                self.fallback_api_connected = False
            self.last_error = type(err).__name__
            raise UpdateFailed("Timeout communicating with API") from err
        except DiagralAPIError as err:
            if automatic_failover:
                self.fallback_api_connected = False
            self.last_error = type(err).__name__
            raise UpdateFailed(f"Error communicating with API: {err}") from err

        self.last_success = dt_util.utcnow()
        if automatic_failover:
            self.fallback_api_connected = self.api.active_api == "topaze"
        self.last_error = None

        if updated_data is None:
            _LOGGER.debug("Received invalid data from API, keeping old data")
            return self.data
        self.data = updated_data
        await self._update_device_info()
        self._async_schedule_anomalies_refresh()
        return self.data

    @callback
    def _async_schedule_cloud_ping(self) -> None:
        """Measure reachability without delaying the SDK's authenticated probe."""
        if self._shutdown_requested or (
            self._cloud_ping_task is not None and not self._cloud_ping_task.done()
        ):
            return
        self._cloud_ping_task = self.config_entry.async_create_background_task(
            self.hass,
            self._async_refresh_cloud_ping(),
            f"{DOMAIN}-cloud-ping",
            eager_start=False,
        )

    async def _async_refresh_cloud_ping(self) -> None:
        """Report main API reachability without changing fallback availability."""
        reachable = await self._async_ping()
        if not self._shutdown_requested:
            self.cloud_reachable = reachable
            self.async_update_listeners()

    @callback
    def _async_schedule_anomalies_refresh(self) -> None:
        """Keep a slow secondary endpoint out of setup and central polling."""
        if self._shutdown_requested or (
            self._anomalies_task is not None and not self._anomalies_task.done()
        ):
            return
        self._anomalies_task = self.config_entry.async_create_background_task(
            self.hass,
            self._async_refresh_anomalies(),
            f"{DOMAIN}-anomalies",
            eager_start=False,
        )

    async def _async_refresh_anomalies(self) -> None:
        """Publish secondary availability without changing central health."""
        try:
            async with asyncio.timeout(DIAGRAL_REQUEST_TIMEOUT):
                anomalies = await self.api.get_anomalies()
        except (DiagralAPIError, TimeoutError) as err:
            self.anomalies_available = False
            error = type(err).__name__
            if self._anomalies_error != error:
                _LOGGER.warning("Diagral anomalies unavailable (%s)", error)
            self._anomalies_error = error
        else:
            if self._shutdown_requested or self.data is None:
                return
            # Merge into current data: a command may have updated the status.
            self.data["anomalies"] = anomalies
            self.anomalies_available = True
            if self._anomalies_error is not None:
                _LOGGER.info("Diagral anomalies available again")
            self._anomalies_error = None
        if not self._shutdown_requested:
            # async_set_updated_data would also mark stale central data healthy.
            self.async_update_listeners()

    async def _async_ping(self) -> bool:
        """Tell whether the cloud answers at all, whatever the credentials."""
        try:
            async with asyncio.timeout(PING_TIMEOUT):
                await self.api.ping()
        except (DiagralAPIError, TimeoutError) as err:
            _LOGGER.debug(
                "Diagral cloud did not answer the ping (%s)", type(err).__name__
            )
            return False
        return True

    async def _async_read_with_retries(
        self, timeouts: tuple[float, ...]
    ) -> dict[str, Any] | None:
        """Read the data, each retry with a longer deadline after a longer pause."""
        for attempt, timeout in enumerate(timeouts):
            try:
                async with asyncio.timeout(timeout):
                    return await self._async_read()
            except (DiagralAPIError, TimeoutError) as err:
                if attempt == len(timeouts) - 1 or not is_transient_error(err):
                    raise
                pause = READ_RETRY_PAUSES[attempt]
                # Home Assistant logs the outage once; retries stay in debug
                _LOGGER.debug(
                    "Diagral read failed (%s), retrying in %s s",
                    type(err).__name__,
                    pause,
                )
                await asyncio.sleep(pause)
        return None

    async def _async_read(self) -> dict[str, Any] | None:
        """Read everything the entities need, or None when the payload is invalid."""
        if getattr(self.api, "supports_failover", False) is True:
            snapshot = await self.api.get_core_snapshot()
            alarm_config = snapshot.alarm_config
            devices_infos = snapshot.devices_infos
            system_status = snapshot.system_status
        else:
            alarm_config: AlarmConfiguration = await self.api.get_configuration()
            devices_infos: DeviceInfos = await self.api.get_devices_info()
            system_status: SystemStatus = await self.api.get_system_status()
        if not (alarm_config and system_status):
            return None
        return {
            "alarm_config": alarm_config,
            "devices_infos": devices_infos,
            "groups": alarm_config.groups,
            "system_status": system_status,
            "anomalies": (self.data or {}).get("anomalies"),
        }

    def get_alarm_central_device(self) -> DeviceInfo:
        """Return the device info for the alarm."""
        alarm_config: AlarmConfiguration = self.data.get("alarm_config")

        return DeviceInfo(
            identifiers={(DOMAIN, alarm_config.alarm.central.serial)},
            name=alarm_config.alarm.name.title()
            if alarm_config.alarm.name
            else "Diagral Central",
            manufacturer=BRAND,
            model=f"{BRAND} Alarm",
            serial_number=alarm_config.alarm.central.serial,
            sw_version=f"{alarm_config.alarm.central.firmwares.central} / Radio:{alarm_config.alarm.central.firmwares.centralradio}",
        )

    async def _update_device_info(self) -> None:
        """Update device info."""
        alarm_config: AlarmConfiguration = self.data.get("alarm_config")
        dev_reg = dr.async_get(self.hass)
        hadevice = dev_reg.async_get_device_by_identifier(
            (DOMAIN, alarm_config.alarm.central.serial), self.config_entry.entry_id
        )
        if hadevice and hadevice.sw_version is not None:
            _LOGGER.debug("Actual sw_version: %s", hadevice.sw_version)
            new_sw_version = f"{alarm_config.alarm.central.firmwares.central} / Radio:{alarm_config.alarm.central.firmwares.centralradio}"
            if new_sw_version != hadevice.sw_version:
                _LOGGER.info("Updated sw_version to %s", new_sw_version)
                dev_reg.async_update_device(hadevice.id, sw_version=new_sw_version)
