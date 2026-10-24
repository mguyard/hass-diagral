"""DataUpdateCoordinator for Diagral integration."""

import asyncio
from datetime import datetime, timedelta
from http import HTTPStatus
import logging
from typing import TYPE_CHECKING, Any

from aiohttp import ClientError as AiohttpClientError
from pydiagral.api import DiagralAPI
from pydiagral.exceptions import (
    AuthenticationError,
    ClientError,
    DiagralAPIError,
    ServerError,
)
from pydiagral.models import (
    AlarmConfiguration,
    Anomalies,
    DeviceInfos,
    Group,
    SystemStatus,
)

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import (
    BRAND,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    READ_ATTEMPTS,
    READ_RETRY_DELAY,
    UPDATE_TIMEOUT,
)

_LOGGER = logging.getLogger(__name__)

if TYPE_CHECKING:
    from . import DiagralConfigEntry


def _is_transient_error(error: Exception) -> bool:
    """Only retry safe reads after network errors or temporary server failures."""
    return isinstance(
        error, (TimeoutError, AiohttpClientError, ClientError, ServerError)
    ) or (
        isinstance(error, DiagralAPIError)
        and error.status_code in {408, 500, 502, 503, 504}
    )


def _safe_error_category(error: Exception) -> str:
    """Return a diagnostic category without cloud response bodies or credentials."""
    if isinstance(error, AuthenticationError):
        return "authentication_failed"
    if isinstance(error, TimeoutError):
        return "timeout"
    if isinstance(error, (AiohttpClientError, ClientError)):
        return "network_error"
    if isinstance(error, ServerError):
        return "cloud_unavailable"
    if isinstance(error, DiagralAPIError):
        if error.status_code in {401, 403}:
            return "authentication_failed"
        if error.status_code == HTTPStatus.TOO_MANY_REQUESTS:
            return "rate_limited"
        if (
            error.status_code is not None
            and HTTPStatus.INTERNAL_SERVER_ERROR
            <= error.status_code
            < HTTPStatus.INTERNAL_SERVER_ERROR + 100
        ):
            return "cloud_unavailable"
        return "api_error"
    return "invalid_response"


class DiagralDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching Diagral data."""

    def __init__(
        self,
        hass: HomeAssistant,
        api: DiagralAPI,
        config_entry: DiagralConfigEntry | None = None,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            config_entry=config_entry,
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
        )
        self.api = api
        self.last_success: datetime | None = None
        self.consecutive_failures = 0
        self.communication_status = "initializing"
        self.last_error: str | None = None

    @callback
    def async_set_update_error(self, err: Exception) -> None:
        """Publish an externally interrupted refresh without exposing raw errors."""
        was_successful = self.last_update_success
        self.consecutive_failures += 1
        self.communication_status = "unavailable"
        self.last_error = _safe_error_category(err)
        super().async_set_update_error(
            UpdateFailed(f"Diagral refresh failed ({self.last_error})")
        )
        if not was_successful:
            self.async_update_listeners()

    @callback
    def _async_refresh_finished(self) -> None:
        """Keep diagnostic counters current during a prolonged outage."""
        super()._async_refresh_finished()
        # The base coordinator publishes the first failure, then suppresses
        # subsequent failed updates because availability is already unchanged.
        if not self.last_update_success and self.consecutive_failures > 1:
            self.async_update_listeners()

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from Diagral API."""
        try:
            async with asyncio.timeout(UPDATE_TIMEOUT):
                for attempt in range(READ_ATTEMPTS):
                    try:
                        updated_data = await self._async_fetch_data()
                        break
                    except (DiagralAPIError, AiohttpClientError, TimeoutError) as err:
                        if attempt + 1 >= READ_ATTEMPTS or not _is_transient_error(err):
                            raise
                        await asyncio.sleep(READ_RETRY_DELAY)
            await self._update_device_info(updated_data["alarm_config"])
        except (
            DiagralAPIError,
            AiohttpClientError,
            TimeoutError,
            ValueError,
            TypeError,
            AttributeError,
        ) as err:
            self.consecutive_failures += 1
            self.communication_status = "unavailable"
            self.last_error = _safe_error_category(err)
            # Keep the previous snapshot for diagnostics, but let HA mark entities
            # unavailable. Never report old data as a successful new observation.
            raise UpdateFailed(f"Diagral refresh failed ({self.last_error})") from None

        self.last_success = dt_util.utcnow()
        self.consecutive_failures = 0
        self.communication_status = "connected"
        self.last_error = None
        return updated_data

    async def _async_fetch_data(self) -> dict[str, Any]:
        """Fetch a complete snapshot without modifying the last successful data."""
        alarm_config: AlarmConfiguration = await self.api.get_configuration()
        if alarm_config is None:
            raise ValueError("Missing alarm configuration")
        groups: list[Group] = alarm_config.groups
        devices_infos: DeviceInfos = await self.api.get_devices_info()
        system_status: SystemStatus = await self.api.get_system_status()
        if (
            system_status is None
            or not isinstance(system_status.status, str)
            or not system_status.status
            or not isinstance(system_status.activated_groups, list)
        ):
            raise ValueError("Invalid system status")
        anomalies: Anomalies = await self.api.get_anomalies()
        return {
            "alarm_config": alarm_config,
            "devices_infos": devices_infos,
            "groups": groups,
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

    async def _update_device_info(self, alarm_config: AlarmConfiguration) -> None:
        """Update device info."""
        if self.config_entry is None:
            return
        dev_reg = dr.async_get(self.hass)
        identifier = (DOMAIN, alarm_config.alarm.central.serial)
        lookup = getattr(dev_reg, "async_get_device_by_identifier", None)
        if lookup is not None:
            hadevice = lookup(
                identifier=identifier,
                config_entry_id=self.config_entry.entry_id,
            )
        else:
            # Older supported HA releases only expose the unscoped lookup.
            hadevice = dev_reg.async_get_device(identifiers={identifier})
            if (
                hadevice is not None
                and self.config_entry.entry_id not in hadevice.config_entries
            ):
                return
        if hadevice:
            _LOGGER.debug("Actual sw_version: %s", hadevice.sw_version)
            new_sw_version = f"{alarm_config.alarm.central.firmwares.central} / Radio:{alarm_config.alarm.central.firmwares.centralradio}"
            if new_sw_version != hadevice.sw_version:
                _LOGGER.info("Updated sw_version to %s", new_sw_version)
                dev_reg.async_update_device(hadevice.id, sw_version=new_sw_version)
