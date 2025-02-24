"""DataUpdateCoordinator for Diagral integration."""

from datetime import timedelta
import logging
from typing import Any

from pydiagral.api import DiagralAPI
from pydiagral.exceptions import DiagralAPIError
from pydiagral.models import (
    AlarmConfiguration,
    Anomalies,
    DeviceInfos,
    Group,
    SystemStatus,
)

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import BRAND, DEFAULT_SCAN_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)


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

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from Diagral API."""
        _LOGGER.debug("Updating data with API instance: %s", id(self.api))
        try:
            alarm_config: AlarmConfiguration = await self.api.get_configuration()
            groups: list[Group] = alarm_config.groups
            devices_infos: DeviceInfos = await self.api.get_devices_info()
            system_status: SystemStatus = await self.api.get_system_status()
            anomalies: Anomalies = await self.api.get_anomalies()

            if alarm_config and system_status:
                updated_data = {
                    "alarm_config": alarm_config,
                    "devices_infos": devices_infos,
                    "groups": groups,
                    "system_status": system_status,
                    "anomalies": anomalies,
                }
                # Update only if the data is valid
                self.data = updated_data
                await self._update_device_info()
                self.async_update_listeners()
                return updated_data
        except DiagralAPIError as err:
            raise UpdateFailed(f"Error communicating with API: {err}") from err
        else:
            _LOGGER.warning("Received invalid data from API, keeping old data")
            return self.data  # Return the old data if the new data is invalid

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
