"""Diagral Alarm Control Panel integration for Home Assistant."""

import logging

from pydiagral.api import DiagralAPI
from pydiagral.exceptions import DiagralAPIError
from pydiagral.models import AlarmConfiguration, SystemStatus, WebHookNotificationUser
import voluptuous as vol

from homeassistant.components.alarm_control_panel import (
    AlarmControlPanelEntity,
    AlarmControlPanelEntityFeature,
    AlarmControlPanelState,
    CodeFormat,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_platform, entity_registry as er
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import DiagralConfigEntry, register_webhook, unregister_webhook
from .const import (
    CONF_ALARMPANEL_ACTIONTYPE_CODE,
    CONF_ALARMPANEL_CODE,
    DOMAIN,
    INPUT_GROUPS,
    SERVICE_ARM_GROUP,
    SERVICE_DISARMGROUP,
    SERVICE_REGISTER_WEBHOOK,
    SERVICE_UNREGISTER_WEBHOOK,
)
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
        SERVICE_ARM_GROUP,
        {vol.Required(INPUT_GROUPS): vol.Any(vol.Coerce(int), [vol.Coerce(int)])},
        DiagralAlarmControlPanel.action_arm_groups.__name__,
    )
    platform.async_register_entity_service(
        SERVICE_DISARMGROUP,
        {vol.Required(INPUT_GROUPS): vol.Any(vol.Coerce(int), [vol.Coerce(int)])},
        DiagralAlarmControlPanel.action_disarm_groups.__name__,
    )
    platform.async_register_entity_service(
        SERVICE_REGISTER_WEBHOOK,
        None,
        DiagralAlarmControlPanel.action_register_webhook.__name__,
    )
    platform.async_register_entity_service(
        SERVICE_UNREGISTER_WEBHOOK,
        None,
        DiagralAlarmControlPanel.action_unregister_webhook.__name__,
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
        new_state: AlarmControlPanelState | None = self._get_ha_state(system_status)
        if new_state:
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
                    alarm_triggered_entity = self.hass.states.get(
                        alarm_triggered_entity_id
                    )
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
        if (
            self._config.options.alarmpanel_options[CONF_ALARMPANEL_ACTIONTYPE_CODE]
            != "never"
        ):
            return True
        return False

    @property
    def code_format(self) -> CodeFormat | None:
        """Return one or more digits/characters."""
        if (
            self._config.options.alarmpanel_options[CONF_ALARMPANEL_ACTIONTYPE_CODE]
            != "never"
        ):
            return CodeFormat.NUMBER
        return None

    @property
    def changed_by(self) -> str:
        """Return the last change triggered by."""
        return self._changed_by

    @property
    def alarm_state(self) -> AlarmControlPanelState | None:
        """Return the state of the device."""
        system_status: SystemStatus = self.coordinator.data.get("system_status")
        return self._get_ha_state(system_status)

    def _validate_code(self, to_state, code_provided: int | None = None) -> bool:
        """Validate given code."""
        code = self._config.options.alarmpanel_options[CONF_ALARMPANEL_CODE]
        trigger = self._config.options.alarmpanel_options[
            CONF_ALARMPANEL_ACTIONTYPE_CODE
        ]

        # Convert code to int if not None
        if code_provided is not None:
            code_provided = int(code_provided)

        if trigger == "never":
            _LOGGER.debug("Code validation not required")
            return True

        if (
            trigger == "disarm" and to_state == AlarmControlPanelState.DISARMED
        ) or trigger == "always":
            _LOGGER.debug("Code validation required")
            if code is None:
                _LOGGER.error("Code is not set in the configuration")
                return False
            return code_provided == code
        return True

    async def async_alarm_disarm(self, code: int | None = None) -> None:
        """Send disarm command."""
        if self._validate_code(
            to_state=AlarmControlPanelState.DISARMED, code_provided=code
        ):
            try:
                await self._api.stop_system()
                await self.coordinator.async_request_refresh()
            except DiagralAPIError as e:
                _LOGGER.error("Failed to disarm Diagral alarm : %s", e)
        else:
            _LOGGER.error("Invalid code provided for disarming")

    async def async_alarm_arm_away(self, code: str | None = None) -> None:
        """Send arm away command."""
        if self._validate_code(
            to_state=AlarmControlPanelState.ARMED_AWAY, code_provided=code
        ):
            try:
                await self._api.start_system()
                await self.coordinator.async_request_refresh()
            except DiagralAPIError as e:
                _LOGGER.error("Failed to arm Diagral alarm in away mode: %s", e)
        else:
            _LOGGER.error("Invalid code provided for arming away")

    async def async_alarm_arm_home(self, code: str | None = None) -> None:
        """Send arm home command."""
        if self._validate_code(
            to_state=AlarmControlPanelState.ARMED_HOME, code_provided=code
        ):
            try:
                await self._api.presence()
                await self.coordinator.async_request_refresh()
            except DiagralAPIError as e:
                _LOGGER.error("Failed to arm Diagral alarm in home mode: %s", e)
        else:
            _LOGGER.error("Invalid code provided for arming home")

    async def action_arm_groups(self, group_ids: int | list[int]) -> None:
        """Activate one or more groups."""
        _LOGGER.debug("Arming group %s with API instance: %s", group_ids, id(self._api))
        if isinstance(group_ids, int):
            group_ids = [group_ids]
            _LOGGER.debug("Armed group(s) after transformation: %s", group_ids)
        try:
            await self._api.activate_group(group_ids)
            await self.coordinator.async_request_refresh()
        except DiagralAPIError as e:
            _LOGGER.error("Failed to arm group(s): %s", e)

    async def action_disarm_groups(self, group_ids: int | list[int]) -> None:
        """Disarm one or more groups."""
        _LOGGER.debug(
            "Disarming group %s with API instance: %s", group_ids, id(self._api)
        )
        if isinstance(group_ids, int):
            group_ids = [group_ids]
            _LOGGER.debug("Disarmed group(s) after transformation: %s", group_ids)
        try:
            await self._api.disable_group(group_ids)
            await self.coordinator.async_request_refresh()
        except DiagralAPIError as e:
            _LOGGER.error("Failed to disarm group(s): %s", e)

    async def action_register_webhook(self) -> None:
        """Register the webhook for Diagral."""
        entry = self.hass.config_entries.async_get_entry(self._entry_id)
        webhook_id = await register_webhook(
            self.hass, entry, entry.runtime_data.api, "HA Action"
        )
        # Force the webhook_id in the entry runtime data to be sure it is saved
        entry.runtime_data.webhook_id = webhook_id

    async def action_unregister_webhook(self) -> None:
        """Unregister the webhook for Diagral."""
        entry = self.hass.config_entries.async_get_entry(self._entry_id)
        # No need to get the webhook_id as it is saved in the entry.runtime_data
        # directly by the unregister_webhook function
        await unregister_webhook(
            self.hass,
            entry,
            entry.runtime_data.api,
            entry.runtime_data.webhook_id,
            "HA Action",
        )

    async def async_added_to_hass(self) -> None:
        """Register callbacks."""
        await super().async_added_to_hass()
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                f"signal-{DOMAIN}-webhook-STATUS",
                self._handle_event,
            )
        )

    @callback
    def _handle_event(self, event) -> None:
        """Handle incoming event."""
        _LOGGER.debug("Alarm Control Panel Received event: %s", event)
        user_info: WebHookNotificationUser | None = event["data"].get("user", None)
        if user_info:
            changed_by: str = user_info.username
            _LOGGER.debug("Alarm State changed by %s", changed_by)
            self._changed_by = changed_by
            self.async_write_ha_state()
