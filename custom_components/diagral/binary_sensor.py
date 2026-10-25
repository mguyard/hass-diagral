"""Binary sensor platform for Diagral integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import DiagralConfigEntry
from .const import DOMAIN
from .coordinator import DiagralDataUpdateCoordinator
from .entity import DiagralEntity


@dataclass(frozen=True, kw_only=True)
class DiagralHealthSensorDescription(BinarySensorEntityDescription):
    """Describe a sensor reporting the health of the link to the Diagral cloud."""

    is_on_fn: Callable[[DiagralDataUpdateCoordinator], bool | None]


CLOUD_CONNECTION = DiagralHealthSensorDescription(
    key="cloud_connection",
    translation_key="cloud_connection",
    device_class=BinarySensorDeviceClass.CONNECTIVITY,
    entity_category=EntityCategory.DIAGNOSTIC,
    is_on_fn=lambda coordinator: coordinator.last_update_success,
)

# Answers without credentials: tells a Diagral outage from a refused key or PIN
CLOUD_REACHABLE = DiagralHealthSensorDescription(
    key="cloud_reachable",
    translation_key="cloud_reachable",
    device_class=BinarySensorDeviceClass.CONNECTIVITY,
    entity_category=EntityCategory.DIAGNOSTIC,
    is_on_fn=lambda coordinator: coordinator.cloud_reachable,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DiagralConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Diagral binary sensors."""
    coordinator = entry.runtime_data.coordinator
    async_add_entities(
        DiagralHealthSensor(coordinator, entry, description)
        for description in (CLOUD_CONNECTION, CLOUD_REACHABLE)
    )


class DiagralHealthSensor(DiagralEntity, BinarySensorEntity):
    """Report the link to the Diagral cloud, even while it is down."""

    entity_description: DiagralHealthSensorDescription

    def __init__(
        self,
        coordinator: DiagralDataUpdateCoordinator,
        config_entry: DiagralConfigEntry,
        description: DiagralHealthSensorDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        serial = coordinator.data["alarm_config"].alarm.central.serial
        self._attr_unique_id = (
            f"{config_entry.entry_id}_{DOMAIN}_{serial}_{description.key}"
        )

    @property
    def available(self) -> bool:
        """It reports the outage that makes the other entities unavailable."""
        return True

    @property
    def is_on(self) -> bool | None:
        """Return the state of the link this sensor reports."""
        return self.entity_description.is_on_fn(self.coordinator)
