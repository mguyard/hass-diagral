"""Diagral Alarm Control Panel integration for Home Assistant."""

import logging

from pydiagral.api import DiagralAPI
from pydiagral.exceptions import DiagralAPIError
from pydiagral.models import AlarmConfiguration, SystemStatus
import voluptuous as vol

from homeassistant.components.alarm_control_panel import (
    AlarmControlPanelEntity,
    AlarmControlPanelEntityFeature,
    AlarmControlPanelState,
    CodeFormat,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_platform, entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import DiagralConfigEntry
from .const import DOMAIN, INPUT_GROUPS, SERVICE_ACTIVATE_GROUP, SERVICE_DISABLE_GROUP
from .coordinator import DiagralDataUpdateCoordinator
from .entity import DiagralEntity
from .models import DiagralConfigData

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DiagralConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Diagral Alarm Control Panel."""
    platform = entity_platform.async_get_current_platform()
    # Retrieve the coordinator and config
    coordinator: DiagralDataUpdateCoordinator = entry.runtime_data.coordinator
    config: DiagralConfigData = entry.runtime_data.config

    # Register services
    platform.async_register_entity_service(
        SERVICE_ACTIVATE_GROUP,
        {vol.Required(INPUT_GROUPS): vol.Any(vol.Coerce(int), [vol.Coerce(int)])},
        DiagralAlarmControlPanel.activate_group.__name__,
    )
    platform.async_register_entity_service(
        SERVICE_DISABLE_GROUP,
        {vol.Required(INPUT_GROUPS): vol.Any(vol.Coerce(int), [vol.Coerce(int)])},
        DiagralAlarmControlPanel.disable_group.__name__,
    )

    # Create the alarm control panel entity
    async_add_entities(
        [DiagralAlarmControlPanel(hass, entry, entry.entry_id, coordinator, config)],
        True,
    )


class DiagralAlarmControlPanel(DiagralEntity, AlarmControlPanelEntity):
    """Representation of a Diagral Alarm Control Panel."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: DiagralConfigEntry,
        entry_id: str,
        coordinator: DiagralDataUpdateCoordinator,
        config: DiagralConfigData,
    ) -> None:
        """Initialize the Diagral Alarm Control Panel."""
        super().__init__(coordinator)
        self._config = config
        self._alarm_config: AlarmConfiguration = coordinator.data.get(
            "alarm_config", {}
        )
        self._entry_id: str = entry_id
        self._attr_unique_id = f"{self._entry_id}_{DOMAIN}_{self._alarm_config.alarm.central.serial}_alarm_control_panel"
        # self._attr_name: str = "Central"
        self._attr_translation_key = "central"
        self._changed_by: str = ""
        self._api: DiagralAPI = entry.runtime_data.api

        self._attr_supported_features = (
            AlarmControlPanelEntityFeature.ARM_AWAY
            | AlarmControlPanelEntityFeature.ARM_HOME
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        system_status: SystemStatus = self.coordinator.data.get("system_status")

        # Update the status of the alarm
        new_state = self._get_ha_state(system_status)
        if new_state != self.state:
            _LOGGER.info("Alarm state changed from %s to %s", self.state, new_state)
            self._attr_state = new_state

        # Reset the alarm_triggered entity if the alarm is disarmed
        if new_state == AlarmControlPanelState.DISARMED:
            entity_registry = er.async_get(self.hass)
            alarm_triggered_entity_id = entity_registry.async_get_entity_id(
                "binary_sensor",
                "diagral",
                f"{self._entry_id}_{DOMAIN}_{self._alarm_config.alarm.central.serial}_alarm_triggered",
            )  # Search for the entity_id of the alarm_triggered binary_sensor
            if alarm_triggered_entity_id:
                alarm_triggered_entity = self.hass.states.get(alarm_triggered_entity_id)
                if alarm_triggered_entity and alarm_triggered_entity.state == "on":
                    self.hass.states.async_set(alarm_triggered_entity_id, "off")
                    _LOGGER.debug(
                        "Resetting Alarm Triggered Entity %s from on to off",
                        alarm_triggered_entity_id,
                    )

        self.async_write_ha_state()

    def _get_ha_state(
        self, system_status: SystemStatus
    ) -> AlarmControlPanelState | None:
        """Convert Diagral status to Home Assistant state."""
        if system_status:
            if system_status.status.lower() == "off":
                return AlarmControlPanelState.DISARMED
            if system_status.status.lower() == "group":
                return AlarmControlPanelState.ARMED_AWAY
            if system_status.status.lower() == "tempo_group":
                return AlarmControlPanelState.ARMING
            if system_status.status.lower() == "presence":
                return AlarmControlPanelState.ARMED_HOME
        return None

    @property
    def code_arm_required(self) -> bool:
        """Whether the code is required for arm actions."""
        return False

    @property
    def code_format(self) -> CodeFormat:
        """Return one or more digits/characters."""
        return CodeFormat.NUMBER

    @property
    def changed_by(self) -> str:
        """Return the last change triggered by."""
        return self._changed_by

    @property
    def alarm_state(self) -> AlarmControlPanelState | None:
        """Return the state of the device."""
        system_status: SystemStatus = self.coordinator.data.get("system_status")
        return self._get_ha_state(system_status)

    async def async_alarm_disarm(self, code: str | None = None) -> None:
        """Send disarm command."""
        try:
            await self._api.stop_system()
            await self.coordinator.async_request_refresh()
        except DiagralAPIError as e:
            _LOGGER.error("Failed to disarm Diagral alarm : %s", e)

    async def async_alarm_arm_away(self, code: str | None = None) -> None:
        """Send arm away command."""
        try:
            await self._api.start_system()
            await self.coordinator.async_request_refresh()
        except DiagralAPIError as e:
            _LOGGER.error("Failed to arm Diagral alarm in away mode: %s", e)

    async def async_alarm_arm_home(self, code: str | None = None) -> None:
        """Send arm home command."""
        _LOGGER.debug("Arming home with API instance: %s", id(self._api))
        try:
            await self._api.presence()
            await self.coordinator.async_request_refresh()
        except DiagralAPIError as e:
            _LOGGER.error("Failed to arm Diagral alarm in home mode: %s", e)

    async def activate_group(self, group_ids: int | list[int]) -> None:
        """Activate one or more groups."""
        _LOGGER.debug(
            "Activating group %s with API instance: %s", group_ids, id(self._api)
        )
        if isinstance(group_ids, int):
            group_ids = [group_ids]
            _LOGGER.debug("Activating group(s) after transformation: %s", group_ids)
        try:
            await self._api.activate_group(group_ids)
            await self.coordinator.async_request_refresh()
        except DiagralAPIError as e:
            _LOGGER.error("Failed to activate group(s): %s", e)

    async def disable_group(self, group_ids: int | list[int]) -> None:
        """Disable one or more groups."""
        _LOGGER.debug(
            "Disabling group %s with API instance: %s", group_ids, id(self._api)
        )
        if isinstance(group_ids, int):
            group_ids = [group_ids]
            _LOGGER.debug("Disabling group(s) after transformation: %s", group_ids)
        try:
            await self._api.disable_group(group_ids)
            await self.coordinator.async_request_refresh()
        except DiagralAPIError as e:
            _LOGGER.error("Failed to disable group(s): %s", e)
