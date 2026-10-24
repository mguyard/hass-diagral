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
    SystemStatus,
)

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
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
    DiagralSensorEntityDescription(
        key="active_groups",
        translation_key="active_groups",
        icon="mdi:home-group",
        native_unit_of_measurement="active groups",
    ),
)

DIAGNOSTIC_SENSORS = (
    SensorEntityDescription(
        key="cloud_connection",
        translation_key="cloud_connection",
        device_class=SensorDeviceClass.ENUM,
        options=["initializing", "connected", "unavailable"],
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SensorEntityDescription(
        key="last_success",
        translation_key="last_success",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SensorEntityDescription(
        key="webhook_status",
        translation_key="webhook_status",
        device_class=SensorDeviceClass.ENUM,
        options=[
            "pending",
            "registered",
            "received",
            "retrying",
            "retry_exhausted",
            "conflict",
            "disabled",
        ],
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SensorEntityDescription(
        key="webhook_last_received",
        translation_key="webhook_last_received",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
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
    async_add_entities(
        [
            DiagralDiagnosticSensor(coordinator, description, entry)
            for description in DIAGNOSTIC_SENSORS
        ]
    )


class DiagralDiagnosticSensor(DiagralEntity, SensorEntity):
    """Connection health remains readable even while cloud data is unavailable."""

    def __init__(self, coordinator, description, entry) -> None:
        """Bind a health sensor to its coordinator and config entry."""
        super().__init__(coordinator)
        self.entity_description = description
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_{DOMAIN}_{description.key}"

    @property
    def available(self) -> bool:
        """Keep failure diagnostics available when cloud observations fail."""
        return True

    @property
    def native_value(self):
        """Return the latest health status or successful observation time."""
        key = self.entity_description.key
        if key == "cloud_connection":
            return self.coordinator.communication_status
        if key == "last_success":
            return self.coordinator.last_success
        return getattr(self._entry.runtime_data, key)

    @property
    def extra_state_attributes(self):
        """Expose failure counts and safe error categories for status sensors."""
        if self.entity_description.key == "cloud_connection":
            return {
                "consecutive_failures": self.coordinator.consecutive_failures,
                "last_error": self.coordinator.last_error,
            }
        if self.entity_description.key == "webhook_status":
            return {
                "retry_attempts": self._entry.runtime_data.webhook_retry_attempts,
                "last_error": self._entry.runtime_data.webhook_last_error,
            }
        return None

    async def async_added_to_hass(self) -> None:
        """Subscribe to webhook health changes for this config entry."""
        await super().async_added_to_hass()
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                f"signal-{DOMAIN}-{self._entry.entry_id}-webhook-health",
                self._handle_webhook_health,
            )
        )

    @callback
    def _handle_webhook_health(self) -> None:
        """Publish health changes independently of the cloud polling cycle."""
        self.async_write_ha_state()


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
        # The coordinator's first successful refresh precedes entity creation.
        # Initialize from that snapshot without another cloud read or a state
        # write before this entity has been attached to Home Assistant.
        self._update_value_from_coordinator()

    @property
    def icon(self) -> str | None:
        """Return the icon to use in the frontend."""
        return self.entity_description.icon

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        if self.coordinator.last_update_success:
            self._update_value_from_coordinator()
        # A failed poll still needs to publish the availability change, but must
        # not give old data a new updated_at timestamp.
        self.async_write_ha_state()

    def _update_value_from_coordinator(self) -> None:
        """Compute the sensor's value from the current snapshot without HA IO."""
        alarm_config: AlarmConfiguration = self.coordinator.data.get("alarm_config")
        anomalies: Anomalies = self.coordinator.data.get("anomalies")
        groups: list[Group] = self.coordinator.data.get("groups", [])
        system_status: SystemStatus = self.coordinator.data.get("system_status")
        devices_infos: DeviceList = self.coordinator.data.get("devices_infos")
        if not alarm_config:
            _LOGGER.warning("No alarm configuration in coordinator data")
            return

        if self.entity_description.key == "anomalies":
            self._update_anomalies(anomalies, groups, devices_infos)
        if self.entity_description.key == "active_groups":
            self._update_active_groups(system_status, groups, alarm_config)

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
            anomalies_dict = {}
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
                                key=lambda item: (
                                    key_order.index(item[0])
                                    if item[0] in key_order
                                    else len(key_order)
                                ),
                            )
                            if value is not None
                        }
                        for equipment in getattr(anomalies, attr)
                    ]
                    # Flatten anomaly names directly into the details
                    for detail in details:
                        if "anomaly_names" in detail:
                            for anomaly in detail.pop("anomaly_names"):
                                detail.update(
                                    {
                                        key: value
                                        for key, value in vars(anomaly).items()
                                        if key in anomaly_name_order
                                    }
                                )
                    if details:  # Only add if there are anomalies
                        anomalies_dict[attr] = details

            if anomalies_dict:
                self._attr_extra_state_attributes["anomalies"] = anomalies_dict

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

    def _update_active_groups(
        self,
        system_status: SystemStatus,
        groups: list[Group],
        alarm_config: AlarmConfiguration,
    ) -> None:
        """Update the active groups sensor."""
        if system_status.status == "PRESENCE":
            # If the system is in presence mode, we grab the groups from the alarm configuration
            group_list = alarm_config.presence_group
        else:
            # Otherwise, count the number of activated groups
            group_list = system_status.activated_groups

        active_groups_count: int = len(group_list)
        self._attr_native_value = active_groups_count

        groups_info = [
            {
                "index": group.index,
                "name": group.name,
                "active": group.index in group_list,
            }
            for group in groups
        ]
        self._attr_extra_state_attributes = {
            "groups": groups_info,
            "updated_at": dt_util.now().isoformat(),
        }
        _LOGGER.debug("Active groups count: %s", active_groups_count)
