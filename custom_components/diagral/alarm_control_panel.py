"""Diagral Alarm Control Panel integration for Home Assistant."""

import asyncio
from collections.abc import Awaitable, Callable
import logging
from typing import Any

from pydiagral.api import DiagralAPI
from pydiagral.exceptions import DiagralAPIError
from pydiagral.models import (
    AlarmConfiguration,
    Group,
    SystemStatus,
    WebHookNotificationUser,
)
import voluptuous as vol

from homeassistant.components.alarm_control_panel import (
    AlarmControlPanelEntity,
    AlarmControlPanelEntityFeature,
    AlarmControlPanelState,
    CodeFormat,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import entity_platform
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import (
    DiagralConfigEntry,
    WebhookUnavailable,
    register_webhook,
    unregister_webhook,
)
from .const import (
    ALARM_INTRUSION_CODES,
    COMMAND_TIMEOUT,
    CONF_ALARMPANEL_ACTIONTYPE_CODE,
    CONF_ALARMPANEL_CODE,
    DOMAIN,
    ENTRY_WEBHOOK_SIGNAL,
    INPUT_GROUPS,
    SERVICE_ARM_GROUP,
    SERVICE_DISARMGROUP,
    SERVICE_REGISTER_WEBHOOK,
    SERVICE_UNREGISTER_WEBHOOK,
    STATUS_GROUP,
    STATUS_OFF,
    STATUS_PRESENCE,
    STATUS_TEMPO_GROUP,
    WEBHOOK_CONNECTED,
    WEBHOOK_STATUS_OF_ISSUE,
    WEBHOOK_UNREGISTERED,
)
from .coordinator import DiagralDataUpdateCoordinator, is_transient_error
from .entity import DiagralEntity
from .models import DiagralConfigData

_LOGGER = logging.getLogger(__name__)

ARMED_STATUSES = (STATUS_GROUP, STATUS_TEMPO_GROUP)


def _status_in(status: SystemStatus, *values: str) -> bool:
    """Return whether the Diagral status is one of the given values."""
    return status.status.lower() in values


def _groups_armed(group_ids: list[int]) -> Callable[[SystemStatus], bool]:
    """Return a check that every given group is armed or arming."""

    def check(status: SystemStatus) -> bool:
        active = set(status.activated_groups or [])
        # The exit delay may not list the arming groups yet.
        if _status_in(status, STATUS_TEMPO_GROUP) and not active:
            return True
        return _status_in(status, *ARMED_STATUSES) and set(group_ids) <= active

    return check


def _groups_disarmed(group_ids: list[int]) -> Callable[[SystemStatus], bool]:
    """Return a check that none of the given groups is armed."""
    return lambda status: not set(group_ids) & set(status.activated_groups or [])


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
        self._attr_alarm_state: AlarmControlPanelState = self._get_ha_state(
            self.coordinator.data.get("system_status")
        )
        self._changed_by: str = ""
        self._api: DiagralAPI = entry.runtime_data.api
        self._attr_code_arm_required: bool = self._is_code_arm_required()
        self._attr_supported_features = (
            AlarmControlPanelEntityFeature.ARM_AWAY
            | AlarmControlPanelEntityFeature.ARM_HOME
        )
        self._attr_extra_state_attributes: dict[str, Any] = {}

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        system_status: SystemStatus = self.coordinator.data.get("system_status")

        # Update the status of the alarm
        new_state: AlarmControlPanelState | None = self._get_ha_state(system_status)
        if new_state and new_state != self.state:
            # If the alarm is triggered, keep the trigger until disarm
            if (
                self.state == AlarmControlPanelState.TRIGGERED
                and new_state != AlarmControlPanelState.DISARMED
            ):
                _LOGGER.info(
                    "Alarm state remains triggered despite change from %s to %s",
                    self.state,
                    new_state,
                )
                self._attr_alarm_state = self.state
            else:  # Otherwise, update the state
                _LOGGER.info("Alarm state changed from %s to %s", self.state, new_state)
                self._attr_alarm_state = new_state
                self._attr_extra_state_attributes.pop("trigger", None)

            # Update the code requirement
            self._attr_code_arm_required = self._is_code_arm_required()

        # Always write state so availability follows the coordinator
        self.async_write_ha_state()

    def _get_ha_state(
        self, system_status: SystemStatus
    ) -> AlarmControlPanelState | None:
        """Convert Diagral status to Home Assistant state."""
        if system_status:
            if _status_in(system_status, STATUS_OFF):
                return AlarmControlPanelState.DISARMED
            if _status_in(system_status, STATUS_GROUP):
                return AlarmControlPanelState.ARMED_AWAY
            if _status_in(system_status, STATUS_TEMPO_GROUP):
                return AlarmControlPanelState.ARMING
            if _status_in(system_status, STATUS_PRESENCE):
                return AlarmControlPanelState.ARMED_HOME
        return None

    @property
    def code_format(self) -> CodeFormat | None:
        """Return one or more digits/characters."""
        if self._is_code_arm_required():
            return CodeFormat.NUMBER
        return None

    @property
    def changed_by(self) -> str:
        """Return the last change triggered by."""
        return self._changed_by

    def _is_code_arm_required(self) -> bool:
        """Return whether the code is required for requested actions."""
        # If configuration requires code never, don't require code
        if (
            self._config.options.alarmpanel_options[CONF_ALARMPANEL_ACTIONTYPE_CODE]
            == "never"
        ):
            return False
        # If configuration requires code disarm, require code if the alarm is armed
        if (
            self._config.options.alarmpanel_options[CONF_ALARMPANEL_ACTIONTYPE_CODE]
            == "disarm"
        ):
            return self._attr_alarm_state in (
                AlarmControlPanelState.ARMING,
                AlarmControlPanelState.ARMED_AWAY,
                AlarmControlPanelState.ARMED_HOME,
                AlarmControlPanelState.TRIGGERED,
            )
        return True  # For all other cases, require code

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

    def _check_code(self, to_state: AlarmControlPanelState, code) -> None:
        """Refuse an action whose code is wrong or missing."""
        if not self._validate_code(to_state=to_state, code_provided=code):
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="invalid_code"
            )

    async def _async_send_command(
        self,
        command: Callable[[], Awaitable[SystemStatus]],
        took_effect: Callable[[SystemStatus], bool],
    ) -> None:
        """Send a command once and publish the status Diagral returns.

        A command whose answer is lost may still have been executed: one status
        read decides, and the command is never resent.
        """
        try:
            async with asyncio.timeout(COMMAND_TIMEOUT):
                status = await command()
        except (DiagralAPIError, TimeoutError) as err:
            if not is_transient_error(err):
                raise HomeAssistantError(
                    translation_domain=DOMAIN, translation_key="command_failed"
                ) from err
            _LOGGER.warning(
                "Diagral command answer lost (%s), checking the alarm status",
                type(err).__name__,
            )
            status = await self._async_read_status()
            if status is None or not took_effect(status):
                raise HomeAssistantError(
                    translation_domain=DOMAIN, translation_key="command_not_confirmed"
                ) from err
        self.coordinator.async_set_updated_data(
            {**self.coordinator.data, "system_status": status}
        )

    async def _async_read_status(self) -> SystemStatus | None:
        """Read the alarm status, or None when Diagral does not answer."""
        try:
            async with asyncio.timeout(COMMAND_TIMEOUT):
                return await self._api.get_system_status()
        except (DiagralAPIError, TimeoutError) as err:
            _LOGGER.warning("Diagral status unreadable (%s)", type(err).__name__)
            return None

    async def async_alarm_disarm(self, code: int | None = None) -> None:
        """Send disarm command."""
        self._check_code(AlarmControlPanelState.DISARMED, code)
        await self._async_send_command(
            self._api.stop_system, lambda status: _status_in(status, STATUS_OFF)
        )

    async def async_alarm_arm_away(self, code: str | None = None) -> None:
        """Send arm away command."""
        self._check_code(AlarmControlPanelState.ARMED_AWAY, code)
        await self._async_send_command(
            self._api.start_system,
            lambda status: _status_in(status, *ARMED_STATUSES),
        )

    async def async_alarm_arm_home(self, code: str | None = None) -> None:
        """Send arm home command."""
        self._check_code(AlarmControlPanelState.ARMED_HOME, code)
        await self._async_send_command(
            self._api.presence, lambda status: _status_in(status, STATUS_PRESENCE)
        )

    async def action_arm_groups(self, group_ids: int | list[int]) -> None:
        """Activate one or more groups."""
        if isinstance(group_ids, int):
            group_ids = [group_ids]
        _LOGGER.debug("Arming group(s) %s", group_ids)
        await self._async_send_command(
            lambda: self._api.activate_group(group_ids), _groups_armed(group_ids)
        )

    async def action_disarm_groups(self, group_ids: int | list[int]) -> None:
        """Disarm one or more groups."""
        if isinstance(group_ids, int):
            group_ids = [group_ids]
        _LOGGER.debug("Disarming group(s) %s", group_ids)
        await self._async_send_command(
            lambda: self._api.disable_group(group_ids), _groups_disarmed(group_ids)
        )

    async def action_register_webhook(self) -> None:
        """Register the webhook for Diagral."""
        entry = self.hass.config_entries.async_get_entry(self._entry_id)
        try:
            webhook_id = await register_webhook(
                self.hass, entry, entry.runtime_data.api, "HA Action", take_over=True
            )
        except WebhookUnavailable as err:
            entry.runtime_data.coordinator.async_set_webhook_status(
                WEBHOOK_STATUS_OF_ISSUE[err.reason]
            )
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key=err.reason
            ) from err
        # Force the webhook_id in the entry runtime data to be sure it is saved
        entry.runtime_data.webhook_id = webhook_id
        entry.runtime_data.coordinator.async_set_webhook_status(WEBHOOK_CONNECTED)

    async def action_unregister_webhook(self) -> None:
        """Unregister the webhook for Diagral."""
        entry = self.hass.config_entries.async_get_entry(self._entry_id)
        # No need to get the webhook_id as it is saved in the entry.runtime_data
        # directly by the unregister_webhook function
        if not await unregister_webhook(
            self.hass,
            entry,
            entry.runtime_data.api,
            entry.runtime_data.webhook_id,
            "HA Action",
        ):
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="webhook_unregistration_failed",
            )
        # The hourly check leaves a webhook the user unregistered alone
        entry.runtime_data.coordinator.async_set_webhook_status(WEBHOOK_UNREGISTERED)

    async def async_added_to_hass(self) -> None:
        """Register callbacks."""
        await super().async_added_to_hass()
        # Register callbacks for webhook events (STATUS)
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                ENTRY_WEBHOOK_SIGNAL.format(
                    entry_id=self._entry_id, alarm_type="STATUS"
                ),
                self._handle_event_status,
            )
        )
        # Register callbacks for webhook events (ALERT)
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                ENTRY_WEBHOOK_SIGNAL.format(
                    entry_id=self._entry_id, alarm_type="ALERT"
                ),
                self._handle_event_alert,
            )
        )

    @callback
    def _handle_event_status(self, event) -> None:
        """Handle incoming event for STATUS events."""
        _LOGGER.debug("Alarm Control Panel Received event: %s", event)
        user_info: WebHookNotificationUser | None = event["data"].get("user", None)
        if user_info:
            changed_by: str = user_info.username
            _LOGGER.debug("Alarm State changed by %s", changed_by)
            self._changed_by = changed_by
            self.async_write_ha_state()

    @callback
    def _handle_event_alert(self, event) -> None:
        """Handle incoming event for ALERT events."""
        _LOGGER.debug("%s received event: %s", self.name, event)
        event_alarm_code = int(event["data"].get("alarm_code"))
        if event_alarm_code in ALARM_INTRUSION_CODES:
            # Set the group name and id
            groups: list[Group] = self._alarm_config.groups
            # An alert may name no group, or a group code rather than an index:
            # the panel must trigger either way.
            raw_group_index = str(event["data"].get("group_index") or "")
            group_index: int | None = (
                int(raw_group_index) if raw_group_index.isdigit() else None
            )
            if group_index:
                group: Group = next(
                    (group for group in groups if group.index == group_index), None
                )
                # Add group name and id to the attributes
                trigger_info = {}
                if group and group.name:
                    trigger_info["group_name"] = group.name
                if group_index:
                    trigger_info["group_id"] = group_index
                if trigger_info:
                    self._attr_extra_state_attributes["trigger"] = trigger_info
            self._attr_alarm_state = AlarmControlPanelState.TRIGGERED
            self.async_write_ha_state()
