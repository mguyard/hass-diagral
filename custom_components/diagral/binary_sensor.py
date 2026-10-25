"""Binary sensor platform for Diagral integration."""

from __future__ import annotations

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

CLOUD_CONNECTION = BinarySensorEntityDescription(
    key="cloud_connection",
    translation_key="cloud_connection",
    device_class=BinarySensorDeviceClass.CONNECTIVITY,
    entity_category=EntityCategory.DIAGNOSTIC,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DiagralConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Diagral binary sensors."""
    async_add_entities([DiagralCloudConnection(entry.runtime_data.coordinator, entry)])


class DiagralCloudConnection(DiagralEntity, BinarySensorEntity):
    """Whether the last refresh from the Diagral cloud succeeded."""

    entity_description = CLOUD_CONNECTION

    def __init__(
        self,
        coordinator: DiagralDataUpdateCoordinator,
        config_entry: DiagralConfigEntry,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        serial = coordinator.data["alarm_config"].alarm.central.serial
        self._attr_unique_id = (
            f"{config_entry.entry_id}_{DOMAIN}_{serial}_{CLOUD_CONNECTION.key}"
        )

    @property
    def available(self) -> bool:
        """It reports the outage that makes the other entities unavailable."""
        return True

    @property
    def is_on(self) -> bool:
        """Return whether the Diagral cloud answered the last refresh."""
        return self.coordinator.last_update_success
