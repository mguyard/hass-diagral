"""Diagral Alarm Control Panel integration for Home Assistant."""

import asyncio
from collections.abc import Awaitable, Callable
from functools import partial
import logging
from typing import Any

from aiohttp import ClientError
from pydiagral.api import DiagralAPI
from pydiagral.exceptions import DiagralAPIError
from pydiagral.models import AlarmConfiguration, Group, SystemStatus
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

from . import DiagralConfigEntry, register_webhook, unregister_webhook
from .const import (
    ALARM_INTRUSION_CODES,
    COMMAND_TIMEOUT,
    CONF_ALARMPANEL_ACTIONTYPE_CODE,
    CONF_ALARMPANEL_CODE,
    CONFIRMATION_ATTEMPTS,
    CONFIRMATION_DELAY,
    CONFIRMATION_TIMEOUT,
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
        self._command_lock = asyncio.Lock()
        self._attr_code_arm_required: bool = self._is_code_arm_required()
        self._attr_supported_features = (
            AlarmControlPanelEntityFeature.ARM_AWAY
            | AlarmControlPanelEntityFeature.ARM_HOME
        )
        self._attr_extra_state_attributes: dict[str, Any] = {}

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        if self.coordinator.last_update_success:
            self._alarm_config = self.coordinator.data["alarm_config"]
            system_status: SystemStatus = self.coordinator.data.get("system_status")
            new_state = self._get_ha_state(system_status)
            # Preserve a confirmed intrusion until a fresh disarmed state arrives.
            if new_state is not None and not (
                self._attr_alarm_state == AlarmControlPanelState.TRIGGERED
                and new_state != AlarmControlPanelState.DISARMED
            ):
                if new_state != self._attr_alarm_state:
                    self._attr_extra_state_attributes.pop("trigger", None)
                self._attr_alarm_state = new_state
            self._attr_code_arm_required = self._is_code_arm_required()

        # Availability can change even when the physical alarm state has not.
        self.async_write_ha_state()

    def _get_ha_state(
        self, system_status: SystemStatus
    ) -> AlarmControlPanelState | None:
        """Convert Diagral status to Home Assistant state."""
        if system_status and isinstance(system_status.status, str):
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

    def _validate_code(
        self,
        to_state: AlarmControlPanelState,
        code_provided: str | int | None = None,
    ) -> bool:
        """Validate given code."""
        code = self._config.options.alarmpanel_options[CONF_ALARMPANEL_CODE]
        trigger = self._config.options.alarmpanel_options[
            CONF_ALARMPANEL_ACTIONTYPE_CODE
        ]

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
            try:
                return code_provided is not None and int(code_provided) == int(code)
            except TypeError, ValueError:
                return False
        return True

    def _require_valid_code(
        self, to_state: AlarmControlPanelState, code: str | int | None
    ) -> None:
        """Reject an invalid panel code before making any cloud request."""
        if not self._validate_code(to_state, code):
            raise ServiceValidationError("Invalid or missing Diagral alarm panel code")

    async def _async_execute_command(
        self,
        command: Callable[[], Awaitable[SystemStatus]],
        expected: Callable[[SystemStatus], bool],
    ) -> None:
        """Send once, then confirm using fresh reads without replaying a mutation."""
        async with self._command_lock:
            try:
                async with asyncio.timeout(COMMAND_TIMEOUT):
                    await command()
            except DiagralAPIError, ClientError, TimeoutError:
                raise HomeAssistantError(
                    "Diagral command could not be confirmed. Check the alarm state "
                    "before retrying."
                ) from None

            try:
                async with asyncio.timeout(CONFIRMATION_TIMEOUT):
                    for attempt in range(CONFIRMATION_ATTEMPTS):
                        # async_refresh waits for an actual new read; the debounced
                        # async_request_refresh may return before a scheduled read.
                        await self.coordinator.async_refresh()
                        status = (self.coordinator.data or {}).get("system_status")
                        if (
                            self.coordinator.last_update_success
                            and status is not None
                            and expected(status)
                        ):
                            return
                        if attempt + 1 < CONFIRMATION_ATTEMPTS:
                            await asyncio.sleep(CONFIRMATION_DELAY)
            except TimeoutError as err:
                # A confirmation deadline may cancel a coordinator refresh before
                # its normal listener notification. Publish unavailable explicitly.
                self.coordinator.async_set_update_error(err)
            except DiagralAPIError, ClientError:
                pass
            raise HomeAssistantError(
                "Diagral command was sent, but the requested state was not confirmed. "
                "Check the alarm state before retrying."
            )

    async def async_alarm_disarm(self, code: str | None = None) -> None:
        """Send disarm command."""
        self._require_valid_code(AlarmControlPanelState.DISARMED, code)
        await self._async_execute_command(
            self._api.stop_system, lambda status: status.status.lower() == "off"
        )

    async def async_alarm_arm_away(self, code: str | None = None) -> None:
        """Send arm away command."""
        self._require_valid_code(AlarmControlPanelState.ARMED_AWAY, code)
        expected_groups = {group.index for group in self._alarm_config.groups}
        await self._async_execute_command(
            self._api.start_system,
            # During the exit delay Diagral reports TEMPO_GROUP with an empty
            # activated_groups list. Once armed, GROUP also describes partial
            # arming, so it confirms away mode only when every configured group
            # is active.
            lambda status: (
                status.status.lower() == "tempo_group"
                or (
                    status.status.lower() == "group"
                    and bool(expected_groups)
                    and expected_groups.issubset(status.activated_groups)
                )
            ),
        )

    async def async_alarm_arm_home(self, code: str | None = None) -> None:
        """Send arm home command."""
        self._require_valid_code(AlarmControlPanelState.ARMED_HOME, code)
        await self._async_execute_command(
            self._api.presence, lambda status: status.status.lower() == "presence"
        )

    def _validate_group_ids(self, group_ids: int | list[int]) -> list[int]:
        """Reject empty or unknown group selections locally."""
        if isinstance(group_ids, int):
            group_ids = [group_ids]
        known_groups = {group.index for group in self._alarm_config.groups}
        if (
            not isinstance(group_ids, list)
            or not group_ids
            or any(
                isinstance(group_id, bool)
                or not isinstance(group_id, int)
                or group_id not in known_groups
                for group_id in group_ids
            )
        ):
            raise ServiceValidationError("Select one or more configured Diagral groups")
        return list(dict.fromkeys(group_ids))

    async def action_arm_groups(self, group_ids: int | list[int]) -> None:
        """Activate one or more groups."""
        group_ids = self._validate_group_ids(group_ids)
        await self._async_execute_command(
            partial(self._api.activate_group, group_ids),
            lambda status: set(group_ids).issubset(status.activated_groups),
        )

    async def action_disarm_groups(self, group_ids: int | list[int]) -> None:
        """Disarm one or more groups."""
        group_ids = self._validate_group_ids(group_ids)
        await self._async_execute_command(
            partial(self._api.disable_group, group_ids),
            lambda status: set(group_ids).isdisjoint(status.activated_groups),
        )

    async def action_register_webhook(self) -> None:
        """Register the webhook for Diagral."""
        entry = self.hass.config_entries.async_get_entry(self._entry_id)
        webhook_id = await register_webhook(
            self.hass, entry, entry.runtime_data.api, "HA Action", take_over=True
        )
        # Force the webhook_id in the entry runtime data to be sure it is saved
        if webhook_id is not None:
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
        # Register callbacks for webhook events (STATUS)
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                f"signal-{DOMAIN}-{self._entry_id}-webhook-STATUS",
                self._handle_event_status,
            )
        )
        # Register callbacks for webhook events (ALERT)
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                f"signal-{DOMAIN}-{self._entry_id}-webhook-ALERT",
                self._handle_event_alert,
            )
        )

    @callback
    def _handle_event_status(self, event) -> None:
        """Handle incoming event for STATUS events."""
        if event.get("entry_id") != self._entry_id:
            return
        user_info = event["data"].get("user")
        self._changed_by = (
            user_info.get("username", "") if isinstance(user_info, dict) else ""
        )
        self.async_write_ha_state()

    @callback
    def _handle_event_alert(self, event) -> None:
        """Handle incoming event for ALERT events."""
        if event.get("entry_id") != self._entry_id:
            return
        try:
            event_alarm_code = int(event["data"].get("alarm_code"))
        except TypeError, ValueError:
            return
        if event_alarm_code in ALARM_INTRUSION_CODES:
            self._attr_extra_state_attributes.pop("trigger", None)
            # Set the group name and id
            groups: list[Group] = self._alarm_config.groups
            try:
                group_index = int(event["data"].get("group_index"))
            except TypeError, ValueError:
                group_index = None
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
            self._attr_code_arm_required = self._is_code_arm_required()
            self.async_write_ha_state()
