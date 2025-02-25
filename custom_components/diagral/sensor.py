"""Sensor platform for Diagral integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import logging

from pydiagral.models import (
    AlarmConfiguration,
    Anomalies,
    AnomalyDetail,
    DeviceList,
    Group,
)

from homeassistant.components.sensor import SensorEntity, SensorEntityDescription
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
import homeassistant.util.dt as dt_util

from . import DiagralConfigEntry
from .const import DOMAIN
from .coordinator import DiagralDataUpdateCoordinator
from .entity import DiagralEntity

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class DiagralSensorEntityDescription(SensorEntityDescription):
    """Sensor entity description for Diagral."""

    exists_fn: Callable[..., bool] = lambda _: True


SENSORS: tuple[DiagralSensorEntityDescription, ...] = (
    DiagralSensorEntityDescription(
        key="anomalies",
        translation_key="alarm_anomalies",
        icon="mdi:alert-box",
        native_unit_of_measurement="anomalies",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DiagralConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Diagral sensor based on a config entry."""
    coordinator: DiagralDataUpdateCoordinator = entry.runtime_data.coordinator

    for sensor in SENSORS:
        if sensor.exists_fn(coordinator):
            async_add_entities([DiagralSensor(coordinator, sensor, entry)])


class DiagralSensor(DiagralEntity, SensorEntity):
    """Representation of a Diagral sensor."""

    def __init__(
        self,
        coordinator: DiagralDataUpdateCoordinator,
        description: DiagralSensorEntityDescription,
        config_entry: DiagralConfigEntry,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.coordinator = coordinator
        self.entity_description: DiagralSensorEntityDescription = description
        self._config = config_entry.data.get("config", {})
        self._entry_id: str = config_entry.entry_id
        self._alarm_config: AlarmConfiguration = coordinator.data.get(
            "alarm_config", {}
        )
        self._attr_unique_id = f"{self._entry_id}_{DOMAIN}_{self._alarm_config.alarm.central.serial}_{description.key}"

    @property
    def icon(self) -> str | None:
        """Return the icon to use in the frontend."""
        return self.entity_description.icon

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        _LOGGER.debug("_handle_coordinator_update called for %s", self.name)
        alarm_config = self.coordinator.data.get("alarm_config")
        anomalies: Anomalies = self.coordinator.data.get("anomalies")
        groups: list[Group] = self.coordinator.data.get("groups", [])
        devices_infos: DeviceList = self.coordinator.data.get("devices_infos")
        if not alarm_config:
            _LOGGER.warning("No alarm_config in coordinator data for %s", self.name)
            return

        _LOGGER.debug("Anomalies retrieved: %s", anomalies)
        _LOGGER.debug("Groups retrieved: %s", groups)
        _LOGGER.debug("Devices infos retrieved: %s", devices_infos)

        if self.entity_description.key == "anomalies":
            self._update_anomalies(anomalies, groups, devices_infos)

        _LOGGER.debug("State updated for %s: %s", self.name, self.state)
        self.async_write_ha_state()

    def _update_anomalies(
        self, anomalies: Anomalies, groups: list[Group], devices_infos: DeviceList
    ) -> None:
        """Update the anomalies data."""
        if anomalies:
            # Count the number of anomalies
            anomaly_count = sum(
                len(getattr(anomalies, attr))
                for attr in vars(anomalies)
                if isinstance(getattr(anomalies, attr), list)
                and all(
                    isinstance(item, AnomalyDetail) for item in getattr(anomalies, attr)
                )
            )
            _LOGGER.debug("Anomaly count: %s", anomaly_count)
            self._attr_native_value = anomaly_count

            # Create a list of anomalies
            self._attr_extra_state_attributes = {}
            # Add created_at with the date and time of the anomaly creation in local timezone
            if hasattr(anomalies, "created_at"):
                created_at_utc = anomalies.created_at
                created_at_local = dt_util.as_local(created_at_utc)
                self._attr_extra_state_attributes["created_at"] = (
                    created_at_local.isoformat()
                )
            # Add updated_at with the current date and time in local timezone
            self._attr_extra_state_attributes["updated_at"] = dt_util.now().isoformat()

            # Create a mapping from group index to group name
            group_mapping = {group.index: group.name for group in groups}

            # Create a mapping from device index to device label
            device_mapping = {
                device.index: device.label
                for device_list in vars(devices_infos).values()
                for device in device_list
            }

            # Define the order of keys
            key_order = ["serial", "index", "group", "label", "anomaly_names"]
            anomaly_name_order = ["id", "name"]

            # Add each list of anomalies to extra state attributes
            for attr in vars(anomalies):
                if isinstance(getattr(anomalies, attr), list) and all(
                    isinstance(item, AnomalyDetail) for item in getattr(anomalies, attr)
                ):
                    # Create a list of details for each anomaly
                    # Order the keys and remove None values
                    details = [
                        {
                            key: (
                                group_mapping[value]
                                if key == "group" and value in group_mapping
                                else device_mapping[value]
                                if key == "index" and value in device_mapping
                                else value
                            )
                            for key, value in sorted(
                                vars(equipment).items(),
                                key=lambda item: key_order.index(item[0])
                                if item[0] in key_order
                                else len(key_order),
                            )
                            if value is not None
                        }
                        for equipment in getattr(anomalies, attr)
                    ]
                    # Sort anomaly names by id with name first
                    for detail in details:
                        if "anomaly_names" in detail:
                            detail["anomaly_names"] = [
                                {
                                    key: value
                                    for key, value in sorted(
                                        vars(anomaly).items(),
                                        key=lambda item: anomaly_name_order.index(
                                            item[0]
                                        )
                                        if item[0] in anomaly_name_order
                                        else len(anomaly_name_order),
                                    )
                                    if value is not None
                                }
                                for anomaly in detail["anomaly_names"]
                            ]
                    if details:  # Only add if there are anomalies
                        self._attr_extra_state_attributes[attr] = details

            # Sort extra state attributes by key with created_at and updated_at first
            self._attr_extra_state_attributes = {
                k: self._attr_extra_state_attributes[k]
                for k in (
                    "created_at",
                    "updated_at",
                    *sorted(
                        k
                        for k in self._attr_extra_state_attributes
                        if k not in ["created_at", "updated_at"]
                    ),
                )
            }
        else:
            self._attr_native_value = 0
            self._attr_extra_state_attributes = {}
