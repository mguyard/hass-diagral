"""Binary sensor for Diagral integration."""

from collections.abc import Callable
from dataclasses import dataclass
import logging

from pydiagral.models import AlarmConfiguration

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import DiagralConfigEntry
from .const import DOMAIN
from .coordinator import DiagralDataUpdateCoordinator
from .entity import DiagralEntity

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class DiagralBinarySensorEntityDescription(BinarySensorEntityDescription):
    """Sensor entity description for Diagral."""

    exists_fn: Callable[..., bool] = lambda _: True


BINARY_SENSORS: tuple[DiagralBinarySensorEntityDescription, ...] = (
    DiagralBinarySensorEntityDescription(
        key="alarm_triggered",
        translation_key="alarm_triggered",
        icon="mdi:alarm-light",
        device_class=BinarySensorDeviceClass.SAFETY,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DiagralConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Diagral binary sensor based on a config entry."""
    coordinator: DiagralDataUpdateCoordinator = entry.runtime_data.coordinator

    for sensor in BINARY_SENSORS:
        if sensor.exists_fn(coordinator):
            async_add_entities([DiagralBinarySensor(coordinator, sensor, entry)])


class DiagralBinarySensor(DiagralEntity, BinarySensorEntity):
    """Representation of a Diagral binary sensor."""

    def __init__(
        self,
        coordinator: DiagralDataUpdateCoordinator,
        description: DiagralBinarySensorEntityDescription,
        config_entry: DiagralConfigEntry,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator=coordinator)
        self.coordinator = coordinator
        self.entity_description = description
        self._config = config_entry.data.get("config", {})
        self._entry_id: str = config_entry.entry_id
        self._alarm_config: AlarmConfiguration = coordinator.data.get(
            "alarm_config", {}
        )
        self._attr_unique_id = f"{self._entry_id}_{DOMAIN}_{self._alarm_config.alarm.central.serial}_{self.entity_description.key}"

        self._attr_is_on = False

    @property
    def icon(self) -> str | None:
        """Return the icon to use in the frontend."""
        return self.entity_description.icon

    async def async_added_to_hass(self) -> None:
        """Register callbacks."""
        await super().async_added_to_hass()
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                f"signal-{DOMAIN}-webhook-ALERT",
                self._handle_event,
            )
        )

    @callback
    def _handle_event(self, event) -> None:
        """Handle incoming event."""
        _LOGGER.debug("%s received event: %s", self.name, event)
        if self.entity_description.key == "alarm_triggered":
            event_alarm_code = int(event["data"].get("alarm_code"))
            ALARM_INTRUSION_CODES = {1130, 1139}
            if event_alarm_code in ALARM_INTRUSION_CODES:
                self._attr_is_on = True
            self.async_write_ha_state()
