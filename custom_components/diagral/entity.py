"""Entity definitions for Diagral integration."""

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import DiagralDataUpdateCoordinator


class DiagralEntity(CoordinatorEntity[DiagralDataUpdateCoordinator]):
    """Defines a base Diagral entity."""

    _attr_has_entity_name = True

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information about this Diagral device."""
        return self.coordinator.get_alarm_central_device()
