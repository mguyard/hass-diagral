"""Regression tests for alarm availability, service failures and confirmation."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, Mock, patch

from custom_components.diagral.alarm_control_panel import (
    CONFIRMATION_ATTEMPTS,
    DiagralAlarmControlPanel,
    async_setup_entry,
)
from custom_components.diagral.const import (
    CONF_ALARMPANEL_ACTIONTYPE_CODE,
    CONF_ALARMPANEL_CODE,
)
from pydiagral.exceptions import DiagralAPIError
import pytest

from homeassistant.components.alarm_control_panel import AlarmControlPanelState
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError


@pytest.fixture
def panel():
    """Create a panel with cloud IO replaced by explicit mocks."""
    result = object.__new__(DiagralAlarmControlPanel)
    result._entry_id = "entry-one"
    result._attr_alarm_state = AlarmControlPanelState.DISARMED
    result._attr_extra_state_attributes = {}
    result._changed_by = ""
    result._command_lock = asyncio.Lock()
    result._config = SimpleNamespace(
        options=SimpleNamespace(
            alarmpanel_options={
                CONF_ALARMPANEL_ACTIONTYPE_CODE: "never",
                CONF_ALARMPANEL_CODE: None,
            }
        )
    )
    result._alarm_config = SimpleNamespace(
        groups=[
            SimpleNamespace(index=1, name="Entry"),
            SimpleNamespace(index=2, name="Upstairs"),
        ],
        alarm=SimpleNamespace(central=SimpleNamespace(serial="serial")),
    )
    result.coordinator = SimpleNamespace(
        data={
            "system_status": SimpleNamespace(status="off", activated_groups=[]),
            "alarm_config": result._alarm_config,
        },
        last_update_success=True,
        async_refresh=AsyncMock(),
        async_set_update_error=Mock(),
    )
    result._api = SimpleNamespace(
        stop_system=AsyncMock(),
        start_system=AsyncMock(),
        presence=AsyncMock(),
        activate_group=AsyncMock(),
        disable_group=AsyncMock(),
    )
    result.async_write_ha_state = Mock()
    return result


def test_failure_and_recovery_publish_same_alarm_state(panel):
    """Both availability transitions must reach HA even with unchanged data."""
    panel.coordinator.last_update_success = False
    panel._handle_coordinator_update()
    assert panel.available is False
    panel.coordinator.last_update_success = True
    panel._handle_coordinator_update()
    assert panel.available is True
    assert panel._attr_alarm_state == AlarmControlPanelState.DISARMED
    assert panel.async_write_ha_state.call_count == 2


def test_intrusion_survives_stale_data_and_clears_on_fresh_disarm(panel):
    """A failed poll must never clear an intrusion using the old off state."""
    panel._attr_alarm_state = AlarmControlPanelState.TRIGGERED
    panel._attr_extra_state_attributes["trigger"] = {"group_id": 1}
    panel.coordinator.last_update_success = False
    panel._handle_coordinator_update()
    assert panel._attr_alarm_state == AlarmControlPanelState.TRIGGERED
    panel.coordinator.last_update_success = True
    panel._handle_coordinator_update()
    assert panel._attr_alarm_state == AlarmControlPanelState.DISARMED
    assert "trigger" not in panel._attr_extra_state_attributes


async def test_setup_does_not_request_second_initial_refresh(panel):
    """The config entry already completed its first refresh."""
    entry = SimpleNamespace(
        entry_id="entry-one",
        runtime_data=SimpleNamespace(
            coordinator=panel.coordinator, config=panel._config, api=panel._api
        ),
    )
    add_entities = Mock()
    with patch(
        "custom_components.diagral.alarm_control_panel.entity_platform.async_get_current_platform",
        return_value=MagicMock(),
    ):
        await async_setup_entry(MagicMock(), entry, add_entities)
    assert len(add_entities.call_args.args) == 1
    assert not add_entities.call_args.kwargs.get("update_before_add", False)


@pytest.mark.parametrize(
    ("method", "api_method", "args"),
    [
        ("async_alarm_disarm", "stop_system", ()),
        ("async_alarm_arm_away", "start_system", ()),
        ("async_alarm_arm_home", "presence", ()),
        ("action_arm_groups", "activate_group", ([1],)),
        ("action_disarm_groups", "disable_group", ([1],)),
    ],
)
async def test_cloud_command_error_propagates_without_replay(
    panel, method, api_method, args
):
    """Callers must see failure; credential-bearing API messages must not leak."""
    command = getattr(panel._api, api_method)
    command.side_effect = DiagralAPIError("secret-url-and-token")
    with pytest.raises(HomeAssistantError) as error:
        await getattr(panel, method)(*args)
    assert "secret-url-and-token" not in str(error.value)
    command.assert_awaited_once()
    panel.coordinator.async_refresh.assert_not_awaited()


@pytest.mark.parametrize("code", [None, "wrong", "9999"])
async def test_invalid_code_is_service_error_before_cloud_io(panel, code):
    """Reject missing or incorrect panel codes without contacting the cloud."""
    panel._config.options.alarmpanel_options = {
        CONF_ALARMPANEL_ACTIONTYPE_CODE: "always",
        CONF_ALARMPANEL_CODE: 1234,
    }
    with pytest.raises(ServiceValidationError):
        await panel.async_alarm_disarm(code)
    panel._api.stop_system.assert_not_awaited()


async def test_arm_confirmation_retries_only_reads(panel):
    """Eventual cloud state propagation may require a second observation."""

    def refresh():
        if panel.coordinator.async_refresh.await_count == 2:
            panel.coordinator.data["system_status"].status = "tempo_group"

    panel.coordinator.async_refresh.side_effect = refresh
    with patch(
        "custom_components.diagral.alarm_control_panel.asyncio.sleep",
        new_callable=AsyncMock,
    ):
        await panel.async_alarm_arm_away()
    panel._api.start_system.assert_awaited_once()
    assert panel.coordinator.async_refresh.await_count == 2


async def test_unconfirmed_command_fails_after_bounded_reads(panel):
    """Stop checking an unchanged state after the confirmation attempt limit."""
    with (
        patch(
            "custom_components.diagral.alarm_control_panel.asyncio.sleep",
            new_callable=AsyncMock,
        ),
        pytest.raises(HomeAssistantError, match="not confirmed"),
    ):
        await panel.async_alarm_arm_away()
    panel._api.start_system.assert_awaited_once()
    assert panel.coordinator.async_refresh.await_count == CONFIRMATION_ATTEMPTS


async def test_partial_arming_does_not_confirm_arm_away(panel):
    """GROUP alone also describes partial arming and cannot confirm full arming."""
    panel.coordinator.data["system_status"].status = "group"
    panel.coordinator.data["system_status"].activated_groups = [1]
    with (
        patch(
            "custom_components.diagral.alarm_control_panel.asyncio.sleep",
            new_callable=AsyncMock,
        ),
        pytest.raises(HomeAssistantError, match="not confirmed"),
    ):
        await panel.async_alarm_arm_away()
    panel._api.start_system.assert_awaited_once()
    assert panel.coordinator.async_refresh.await_count == CONFIRMATION_ATTEMPTS


async def test_all_configured_groups_confirm_arm_away(panel):
    """A fresh full arming observation confirms the command immediately."""
    panel.coordinator.data["system_status"].status = "group"
    panel.coordinator.data["system_status"].activated_groups = [2, 1]
    await panel.async_alarm_arm_away()
    panel._api.start_system.assert_awaited_once()
    panel.coordinator.async_refresh.assert_awaited_once()


async def test_stale_matching_state_does_not_confirm_command(panel):
    """Require a fresh successful poll even when cached state matches."""
    panel.coordinator.last_update_success = False
    with (
        patch(
            "custom_components.diagral.alarm_control_panel.asyncio.sleep",
            new_callable=AsyncMock,
        ),
        pytest.raises(HomeAssistantError, match="not confirmed"),
    ):
        await panel.async_alarm_disarm()
    panel._api.stop_system.assert_awaited_once()


async def test_confirmation_timeout_does_not_replay_command(panel):
    """Report a confirmation timeout without repeating the alarm mutation."""
    panel.coordinator.async_refresh.side_effect = TimeoutError
    with pytest.raises(HomeAssistantError, match="not confirmed"):
        await panel.async_alarm_disarm()
    panel._api.stop_system.assert_awaited_once()
    panel.coordinator.async_set_update_error.assert_called_once()


async def test_group_services_remain_independent_of_panel_code(panel):
    """Preserve group service behavior when panel actions require a code."""
    panel._config.options.alarmpanel_options = {
        CONF_ALARMPANEL_ACTIONTYPE_CODE: "always",
        CONF_ALARMPANEL_CODE: 1234,
    }
    await panel.action_disarm_groups([1])
    panel._api.disable_group.assert_awaited_once_with([1])


@pytest.mark.parametrize("groups", [[], [99], [True]])
async def test_invalid_groups_are_rejected_locally(panel, groups):
    """Reject empty, unknown, or boolean group selections before cloud IO."""
    with pytest.raises(ServiceValidationError):
        await panel.action_arm_groups(groups)
    panel._api.activate_group.assert_not_awaited()


def test_webhook_from_another_entry_does_not_change_panel(panel):
    """Ignore both alerts and user updates belonging to another config entry."""
    panel._handle_event_alert({"entry_id": "entry-two", "data": {"alarm_code": "1130"}})
    panel._handle_event_status(
        {"entry_id": "entry-two", "data": {"user": {"username": "Other"}}}
    )
    assert panel._attr_alarm_state == AlarmControlPanelState.DISARMED
    assert panel._changed_by == ""
    panel.async_write_ha_state.assert_not_called()


def test_intrusion_with_nonnumeric_group_still_sets_triggered(panel):
    """Report intrusion without retaining stale numeric group details."""
    panel._attr_extra_state_attributes["trigger"] = {"group_id": 2}
    panel._handle_event_alert(
        {
            "entry_id": "entry-one",
            "data": {"alarm_code": "1130", "group_index": "NIGHT_MODE_GROUP_CODE"},
        }
    )
    assert panel._attr_alarm_state == AlarmControlPanelState.TRIGGERED
    assert "trigger" not in panel._attr_extra_state_attributes


def test_status_webhook_accepts_serializable_user_dictionary(panel):
    """Read the actor from the JSON-compatible webhook user mapping."""
    panel._handle_event_status(
        {"entry_id": "entry-one", "data": {"user": {"username": "Owner"}}}
    )
    assert panel._changed_by == "Owner"


def test_status_without_user_does_not_attribute_change_to_previous_user(panel):
    """Clear the previous actor when the next status event has no user."""
    panel._changed_by = "Previous user"
    panel._handle_event_status({"entry_id": "entry-one", "data": {}})
    assert panel._changed_by == ""
