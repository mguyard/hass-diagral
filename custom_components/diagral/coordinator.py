"""DataUpdateCoordinator for Diagral integration."""

import asyncio
from datetime import datetime, timedelta
import logging
from typing import Any

from pydiagral.api import DiagralAPI
from pydiagral.exceptions import ClientError, DiagralAPIError, ServerError
from pydiagral.models import AlarmConfiguration, Anomalies, DeviceInfos, SystemStatus

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
import homeassistant.util.dt as dt_util

from .const import (
    BRAND,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    HTTP_SERVER_ERROR,
    PING_TIMEOUT,
    READ_ATTEMPT_TIMEOUTS,
    READ_RETRY_BUDGET,
    READ_RETRY_PAUSES,
)

_LOGGER = logging.getLogger(__name__)


def is_transient_error(err: Exception) -> bool:
    """Return whether a failed read may succeed when retried."""
    if isinstance(err, TimeoutError | ClientError | ServerError):
        return True
    status_code = getattr(err, "status_code", None)
    return status_code is not None and status_code >= HTTP_SERVER_ERROR


class DiagralDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching Diagral data."""

    def __init__(self, hass: HomeAssistant, api: DiagralAPI) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
        )
        self.api = api
        self.last_success: datetime | None = None
        self.last_error: str | None = None
        self.webhook_status: str | None = None
        self.last_webhook: datetime | None = None
        self.cloud_reachable: bool | None = None

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
        self.cloud_reachable = await self._async_ping()
        # A failed first refresh fails the setup, which Home Assistant retries.
        timeouts = READ_ATTEMPT_TIMEOUTS if self.data else READ_ATTEMPT_TIMEOUTS[:1]
        try:
            async with asyncio.timeout(READ_RETRY_BUDGET):
                updated_data = await self._async_read_with_retries(timeouts)
        except TimeoutError as err:
            self.last_error = type(err).__name__
            raise UpdateFailed("Timeout communicating with API") from err
        except DiagralAPIError as err:
            self.last_error = type(err).__name__
            raise UpdateFailed(f"Error communicating with API: {err}") from err

        self.last_success = dt_util.utcnow()
        self.last_error = None

        if updated_data is None:
            _LOGGER.debug("Received invalid data from API, keeping old data")
            return self.data
        self.data = updated_data
        await self._update_device_info()
        return updated_data

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
        alarm_config: AlarmConfiguration = await self.api.get_configuration()
        devices_infos: DeviceInfos = await self.api.get_devices_info()
        system_status: SystemStatus = await self.api.get_system_status()
        anomalies: Anomalies = await self.api.get_anomalies()
        if not (alarm_config and system_status):
            return None
        return {
            "alarm_config": alarm_config,
            "devices_infos": devices_infos,
            "groups": alarm_config.groups,
            "system_status": system_status,
            "anomalies": anomalies,
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
        hadevice = dev_reg.async_get_device(
            identifiers={(DOMAIN, alarm_config.alarm.central.serial)}
        )
        if hadevice and hadevice.sw_version is not None:
            _LOGGER.debug("Actual sw_version: %s", hadevice.sw_version)
            new_sw_version = f"{alarm_config.alarm.central.firmwares.central} / Radio:{alarm_config.alarm.central.firmwares.centralradio}"
            if new_sw_version != hadevice.sw_version:
                _LOGGER.info("Updated sw_version to %s", new_sw_version)
                dev_reg.async_update_device(hadevice.id, sw_version=new_sw_version)
