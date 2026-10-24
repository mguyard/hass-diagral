"""Tests for pure logic methods of DiagralAlarmControlPanel (Tier 2).

Tests _get_ha_state(), _validate_code(), and _is_code_arm_required()
without making real API calls or instantiating the full entity.
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.diagral import alarm_control_panel as panel_module
from custom_components.diagral.alarm_control_panel import DiagralAlarmControlPanel
from custom_components.diagral.const import (
    CONF_ALARMPANEL_ACTIONTYPE_CODE,
    CONF_ALARMPANEL_CODE,
)
from pydiagral.exceptions import (
    AuthenticationError,
    ClientError,
    DiagralAPIError,
    ServerError,
)
import pytest

from homeassistant.components.alarm_control_panel import AlarmControlPanelState
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError


def make_panel_mock(
    actiontype_code: str, code: int | None, alarm_state: AlarmControlPanelState
) -> DiagralAlarmControlPanel:
    """Return a DiagralAlarmControlPanel with mocked dependencies.

    Bypasses __init__ and sets the minimal attributes needed to test
    _get_ha_state(), _validate_code(), and _is_code_arm_required().
    """
    panel = object.__new__(DiagralAlarmControlPanel)
    panel._config = MagicMock()
    panel._config.options.alarmpanel_options = {
        CONF_ALARMPANEL_ACTIONTYPE_CODE: actiontype_code,
        CONF_ALARMPANEL_CODE: code,
    }
    panel._attr_alarm_state = alarm_state
    return panel


class TestGetHaState:
    """Tests for _get_ha_state()."""

    def test_status_off_returns_disarmed(self, coordinator_mock):
        """Status 'off' must map to DISARMED."""
        panel = make_panel_mock("never", None, AlarmControlPanelState.DISARMED)
        status = MagicMock()
        status.status = "off"
        assert panel._get_ha_state(status) == AlarmControlPanelState.DISARMED

    def test_status_group_returns_armed_away(self, coordinator_mock):
        """Status 'group' must map to ARMED_AWAY."""
        panel = make_panel_mock("never", None, AlarmControlPanelState.DISARMED)
        status = MagicMock()
        status.status = "group"
        assert panel._get_ha_state(status) == AlarmControlPanelState.ARMED_AWAY

    def test_status_tempo_group_returns_arming(self, coordinator_mock):
        """Status 'tempo_group' must map to ARMING."""
        panel = make_panel_mock("never", None, AlarmControlPanelState.DISARMED)
        status = MagicMock()
        status.status = "tempo_group"
        assert panel._get_ha_state(status) == AlarmControlPanelState.ARMING

    def test_status_presence_returns_armed_home(self, coordinator_mock):
        """Status 'presence' must map to ARMED_HOME."""
        panel = make_panel_mock("never", None, AlarmControlPanelState.DISARMED)
        status = MagicMock()
        status.status = "presence"
        assert panel._get_ha_state(status) == AlarmControlPanelState.ARMED_HOME

    def test_status_none_returns_none(self):
        """None system_status must return None."""
        panel = make_panel_mock("never", None, AlarmControlPanelState.DISARMED)
        assert panel._get_ha_state(None) is None

    def test_status_unknown_returns_none(self):
        """Unknown status string must return None."""
        panel = make_panel_mock("never", None, AlarmControlPanelState.DISARMED)
        status = MagicMock()
        status.status = "unknown_state"
        assert panel._get_ha_state(status) is None


class TestIsCodeArmRequired:
    """Tests for _is_code_arm_required()."""

    def test_never_returns_false(self):
        """'never' actiontype must never require code."""
        panel = make_panel_mock("never", None, AlarmControlPanelState.DISARMED)
        assert panel._is_code_arm_required() is False

    def test_always_returns_true(self):
        """'always' actiontype must always require code."""
        panel = make_panel_mock("always", 1234, AlarmControlPanelState.DISARMED)
        assert panel._is_code_arm_required() is True

    def test_disarm_when_armed_away_returns_true(self):
        """'disarm' when ARMED_AWAY must require code."""
        panel = make_panel_mock("disarm", 1234, AlarmControlPanelState.ARMED_AWAY)
        assert panel._is_code_arm_required() is True

    def test_disarm_when_armed_home_returns_true(self):
        """'disarm' when ARMED_HOME must require code."""
        panel = make_panel_mock("disarm", 1234, AlarmControlPanelState.ARMED_HOME)
        assert panel._is_code_arm_required() is True

    def test_disarm_when_arming_returns_true(self):
        """'disarm' when ARMING must require code."""
        panel = make_panel_mock("disarm", 1234, AlarmControlPanelState.ARMING)
        assert panel._is_code_arm_required() is True

    def test_disarm_when_triggered_returns_true(self):
        """'disarm' when TRIGGERED must require code."""
        panel = make_panel_mock("disarm", 1234, AlarmControlPanelState.TRIGGERED)
        assert panel._is_code_arm_required() is True

    def test_disarm_when_disarmed_returns_false(self):
        """'disarm' when already DISARMED must not require code."""
        panel = make_panel_mock("disarm", 1234, AlarmControlPanelState.DISARMED)
        assert panel._is_code_arm_required() is False


class TestValidateCode:
    """Tests for _validate_code()."""

    def test_trigger_never_returns_true_without_code(self):
        """'never' trigger must pass validation regardless of code."""
        panel = make_panel_mock("never", None, AlarmControlPanelState.DISARMED)
        assert panel._validate_code(AlarmControlPanelState.DISARMED, None) is True

    def test_trigger_always_correct_code_returns_true(self):
        """'always' trigger with correct code must pass."""
        panel = make_panel_mock("always", 1234, AlarmControlPanelState.ARMED_AWAY)
        assert panel._validate_code(AlarmControlPanelState.ARMED_AWAY, 1234) is True

    def test_trigger_always_wrong_code_returns_false(self):
        """'always' trigger with wrong code must fail."""
        panel = make_panel_mock("always", 1234, AlarmControlPanelState.ARMED_AWAY)
        assert panel._validate_code(AlarmControlPanelState.ARMED_AWAY, 9999) is False

    def test_trigger_always_no_code_configured_returns_false(self):
        """'always' trigger with no code configured must fail."""
        panel = make_panel_mock("always", None, AlarmControlPanelState.ARMED_AWAY)
        assert panel._validate_code(AlarmControlPanelState.ARMED_AWAY, 1234) is False

    def test_trigger_disarm_correct_code_returns_true(self):
        """'disarm' trigger on DISARMED transition with correct code must pass."""
        panel = make_panel_mock("disarm", 1234, AlarmControlPanelState.ARMED_AWAY)
        assert panel._validate_code(AlarmControlPanelState.DISARMED, 1234) is True

    def test_trigger_disarm_wrong_code_returns_false(self):
        """'disarm' trigger on DISARMED transition with wrong code must fail."""
        panel = make_panel_mock("disarm", 1234, AlarmControlPanelState.ARMED_AWAY)
        assert panel._validate_code(AlarmControlPanelState.DISARMED, 9999) is False

    def test_trigger_disarm_arm_action_returns_true(self):
        """'disarm' trigger on ARM transition must pass (code not required for arming)."""
        panel = make_panel_mock("disarm", 1234, AlarmControlPanelState.DISARMED)
        assert panel._validate_code(AlarmControlPanelState.ARMED_AWAY, None) is True


def make_updating_panel(
    current_state: AlarmControlPanelState, status: str
) -> DiagralAlarmControlPanel:
    """Return a panel whose coordinator reports the given Diagral status."""
    panel = make_panel_mock("never", None, current_state)
    panel.coordinator = MagicMock()
    panel.coordinator.data = {"system_status": MagicMock(status=status)}
    panel._attr_extra_state_attributes = {"trigger": {"group_id": 1}}
    panel.async_write_ha_state = MagicMock()
    return panel


class TestHandleCoordinatorUpdate:
    """Tests for _handle_coordinator_update()."""

    @pytest.mark.parametrize(
        ("current_state", "status", "expected_state", "trigger_kept"),
        [
            (
                AlarmControlPanelState.DISARMED,
                "group",
                AlarmControlPanelState.ARMED_AWAY,
                False,
            ),
            (
                AlarmControlPanelState.TRIGGERED,
                "group",
                AlarmControlPanelState.TRIGGERED,
                True,
            ),
            (
                AlarmControlPanelState.TRIGGERED,
                "off",
                AlarmControlPanelState.DISARMED,
                False,
            ),
        ],
        ids=["state-change", "triggered-sticks", "disarm-clears-trigger"],
    )
    def test_state_change_is_written(
        self, current_state, status, expected_state, trigger_kept
    ):
        """A new Diagral status updates the panel, except a triggered one."""
        panel = make_updating_panel(current_state, status)
        panel._handle_coordinator_update()
        assert panel._attr_alarm_state == expected_state
        assert ("trigger" in panel._attr_extra_state_attributes) is trigger_kept
        panel.async_write_ha_state.assert_called_once()

    @pytest.mark.parametrize(
        ("current_state", "status"),
        [
            (AlarmControlPanelState.ARMED_AWAY, "group"),
            (AlarmControlPanelState.DISARMED, "unknown"),
        ],
        ids=["same-state", "unknown-status"],
    )
    def test_no_change_is_still_written(self, current_state, status):
        """An unchanged or unknown status keeps the state but still writes it.

        Otherwise an entity added while the coordinator was failing stays
        'unavailable' after the coordinator recovers.
        """
        panel = make_updating_panel(current_state, status)
        panel._handle_coordinator_update()
        assert panel._attr_alarm_state == current_state
        assert "trigger" in panel._attr_extra_state_attributes
        panel.async_write_ha_state.assert_called_once()


def make_alerted_panel() -> DiagralAlarmControlPanel:
    """Return an armed panel that knows one group, ready to receive an alert."""
    panel = make_panel_mock("never", None, AlarmControlPanelState.ARMED_AWAY)
    panel._attr_name = "Central"
    panel._alarm_config = SimpleNamespace(
        groups=[SimpleNamespace(index=1, name="Ground floor")]
    )
    panel._attr_extra_state_attributes = {}
    panel.async_write_ha_state = MagicMock()
    return panel


class TestHandleEventAlert:
    """Tests for _handle_event_alert()."""

    def test_intrusion_in_a_group_triggers_with_its_name(self):
        """An intrusion alert triggers the panel and names its group."""
        panel = make_alerted_panel()
        panel._handle_event_alert({"data": {"alarm_code": "1130", "group_index": "01"}})
        assert panel._attr_alarm_state == AlarmControlPanelState.TRIGGERED
        assert panel._attr_extra_state_attributes["trigger"] == {
            "group_name": "Ground floor",
            "group_id": 1,
        }

    @pytest.mark.parametrize(
        "data",
        [
            {"alarm_code": "1130"},
            {"alarm_code": "1130", "group_index": None},
            {"alarm_code": "1130", "group_index": "NIGHT_MODE_GROUP_CODE"},
        ],
        ids=["no-group-key", "group-none", "group-code"],
    )
    def test_intrusion_without_group_still_triggers(self, data):
        """An intrusion alert without a group must still trigger the panel."""
        panel = make_alerted_panel()
        panel._handle_event_alert({"data": data})
        assert panel._attr_alarm_state == AlarmControlPanelState.TRIGGERED
        assert "trigger" not in panel._attr_extra_state_attributes
        panel.async_write_ha_state.assert_called_once()

    def test_other_alert_leaves_the_state(self):
        """An alert that is not an intrusion leaves the panel as it was."""
        panel = make_alerted_panel()
        panel._handle_event_alert({"data": {"alarm_code": "1301", "group_index": "01"}})
        assert panel._attr_alarm_state == AlarmControlPanelState.ARMED_AWAY
        panel.async_write_ha_state.assert_not_called()


def status(value: str, groups: list[int] | None = None) -> SimpleNamespace:
    """Return a Diagral system status."""
    return SimpleNamespace(status=value, activated_groups=groups or [])


def make_commanded_panel() -> DiagralAlarmControlPanel:
    """Return a disarmed panel whose API answers every command."""
    panel = make_panel_mock("never", None, AlarmControlPanelState.DISARMED)
    panel.coordinator = MagicMock()
    panel.coordinator.data = {"system_status": status("OFF")}
    panel._api = MagicMock()
    for command in (
        "stop_system",
        "start_system",
        "presence",
        "activate_group",
        "disable_group",
        "get_system_status",
    ):
        setattr(panel._api, command, AsyncMock())
    return panel


# (panel method, its arguments, API command, status the command returns)
COMMANDS = [
    ("async_alarm_disarm", (), "stop_system", status("OFF")),
    ("async_alarm_arm_away", (), "start_system", status("GROUP", [1, 2])),
    ("async_alarm_arm_home", (), "presence", status("PRESENCE", [1])),
    ("action_arm_groups", ([1, 2],), "activate_group", status("GROUP", [1, 2])),
    ("action_disarm_groups", ([1],), "disable_group", status("GROUP", [2])),
]
COMMAND_IDS = ["disarm", "arm-away", "arm-home", "arm-groups", "disarm-groups"]


def published_status(panel: DiagralAlarmControlPanel):
    """Return the status the panel pushed to the coordinator."""
    data = panel.coordinator.async_set_updated_data.call_args.args[0]
    return data["system_status"]


class TestCommands:
    """Commands publish the status Diagral returns and report failures."""

    @pytest.mark.parametrize(
        ("method", "args", "command", "returned"), COMMANDS, ids=COMMAND_IDS
    )
    async def test_success_publishes_returned_status(
        self, method, args, command, returned
    ):
        """The status a command returns is published at once, without polling."""
        panel = make_commanded_panel()
        getattr(panel._api, command).return_value = returned
        await getattr(panel, method)(*args)
        assert published_status(panel) is returned
        panel.coordinator.async_request_refresh.assert_not_called()
        panel._api.get_system_status.assert_not_awaited()

    async def test_invalid_code_is_refused(self):
        """A wrong code raises a validation error and sends nothing."""
        panel = make_commanded_panel()
        panel._config.options.alarmpanel_options = {
            CONF_ALARMPANEL_ACTIONTYPE_CODE: "always",
            CONF_ALARMPANEL_CODE: 1234,
        }
        with pytest.raises(ServiceValidationError) as raised:
            await panel.async_alarm_arm_away(code="9999")
        assert raised.value.translation_key == "invalid_code"
        panel._api.start_system.assert_not_awaited()

    @pytest.mark.parametrize(
        "error",
        [
            AuthenticationError("Authentication rejected by Diagral"),
            DiagralAPIError("Diagral API error (HTTP 400)", status_code=400),
        ],
        ids=["auth", "bad-request"],
    )
    async def test_rejected_command_fails(self, error):
        """A command Diagral refuses fails without a status read."""
        panel = make_commanded_panel()
        panel._api.start_system.side_effect = error
        with pytest.raises(HomeAssistantError) as raised:
            await panel.async_alarm_arm_away()
        assert raised.value.translation_key == "command_failed"
        panel._api.get_system_status.assert_not_awaited()
        panel.coordinator.async_set_updated_data.assert_not_called()

    @pytest.mark.parametrize(
        "error",
        [
            ServerError("Diagral service error (HTTP 503)"),
            ClientError("timeout"),
            TimeoutError(),
        ],
        ids=["server-error", "network", "timeout"],
    )
    async def test_uncertain_command_confirmed_by_status(self, error):
        """A command whose answer was lost succeeds if the status shows it."""
        panel = make_commanded_panel()
        panel._api.start_system.side_effect = error
        panel._api.get_system_status.return_value = status("GROUP", [1, 2])
        await panel.async_alarm_arm_away()
        panel._api.start_system.assert_awaited_once()
        assert published_status(panel).status == "GROUP"

    @pytest.mark.parametrize(
        "read",
        [status("OFF"), ServerError("Diagral service error (HTTP 503)")],
        ids=["status-unchanged", "status-unreadable"],
    )
    async def test_uncertain_command_not_confirmed(self, read):
        """Without proof the command took effect, it fails and is not resent."""
        panel = make_commanded_panel()
        panel._api.start_system.side_effect = ServerError(
            "Diagral service error (HTTP 503)"
        )
        if isinstance(read, Exception):
            panel._api.get_system_status.side_effect = read
        else:
            panel._api.get_system_status.return_value = read
        with pytest.raises(HomeAssistantError) as raised:
            await panel.async_alarm_arm_away()
        assert raised.value.translation_key == "command_not_confirmed"
        panel._api.start_system.assert_awaited_once()

    async def test_slow_command_is_cut_then_checked(self):
        """A command that outlives its deadline is checked, not resent."""
        panel = make_commanded_panel()

        async def hang():
            await asyncio.Event().wait()

        panel._api.presence.side_effect = hang
        panel._api.get_system_status.return_value = status("PRESENCE", [1])
        with patch.object(panel_module, "COMMAND_TIMEOUT", 0.01):
            await panel.async_alarm_arm_home()
        panel._api.presence.assert_awaited_once()
        assert published_status(panel).status == "PRESENCE"

    @pytest.mark.parametrize(
        ("method", "args", "command", "read"),
        [
            ("action_arm_groups", ([1, 2],), "activate_group", status("GROUP", [1])),
            ("action_disarm_groups", ([1],), "disable_group", status("GROUP", [1, 2])),
        ],
        ids=["arm-groups-partial", "disarm-groups-still-active"],
    )
    async def test_group_command_needs_every_group(self, method, args, command, read):
        """A group command is confirmed only if every group changed."""
        panel = make_commanded_panel()
        getattr(panel._api, command).side_effect = TimeoutError()
        panel._api.get_system_status.return_value = read
        with pytest.raises(HomeAssistantError) as raised:
            await getattr(panel, method)(*args)
        assert raised.value.translation_key == "command_not_confirmed"


class TestExitDelay:
    """Arming goes through TEMPO_GROUP during the central's exit delay."""

    async def test_arming_status_is_published(self):
        """The exit delay status is published, so the panel shows arming."""
        panel = make_commanded_panel()
        panel._api.start_system.return_value = status("TEMPO_GROUP", [1, 2])
        await panel.async_alarm_arm_away()
        assert published_status(panel).status == "TEMPO_GROUP"
        assert panel._get_ha_state(published_status(panel)) == (
            AlarmControlPanelState.ARMING
        )

    @pytest.mark.parametrize(
        ("method", "args", "command", "read"),
        [
            ("async_alarm_arm_away", (), "start_system", status("TEMPO_GROUP", [1, 2])),
            (
                "action_arm_groups",
                ([1, 2],),
                "activate_group",
                status("TEMPO_GROUP", [1, 2]),
            ),
            ("action_arm_groups", ([1, 2],), "activate_group", status("TEMPO_GROUP")),
        ],
        ids=["arm-away", "arm-groups-listed", "arm-groups-not-listed-yet"],
    )
    async def test_exit_delay_confirms_a_lost_answer(self, method, args, command, read):
        """A command whose answer was lost is confirmed by an exit delay."""
        panel = make_commanded_panel()
        getattr(panel._api, command).side_effect = TimeoutError()
        panel._api.get_system_status.return_value = read
        await getattr(panel, method)(*args)
        assert published_status(panel).status == "TEMPO_GROUP"


def make_webhook_panel() -> DiagralAlarmControlPanel:
    """Return a panel whose loaded entry can (un)register the webhook."""
    panel = make_panel_mock("never", None, AlarmControlPanelState.DISARMED)
    panel._entry_id = "entry1"
    panel.hass = MagicMock()
    panel.hass.config_entries.async_get_entry.return_value.runtime_data.webhook_id = (
        "WEBHOOKID"
    )
    return panel


class TestWebhookActions:
    """The webhook actions fail visibly instead of only logging."""

    @pytest.mark.parametrize(
        "reason", ["webhook_registration_failed", "webhook_no_url"]
    )
    async def test_register_failure_raises(self, reason):
        """A registration that cannot succeed raises a translated error."""
        panel = make_webhook_panel()
        with (
            patch.object(
                panel_module,
                "register_webhook",
                AsyncMock(side_effect=panel_module.WebhookUnavailable(reason)),
            ),
            pytest.raises(HomeAssistantError) as raised,
        ):
            await panel.action_register_webhook()
        assert raised.value.translation_key == reason

    async def test_unregister_failure_raises(self):
        """An unregistration Diagral refuses raises a translated error."""
        panel = make_webhook_panel()
        with (
            patch.object(
                panel_module, "unregister_webhook", AsyncMock(return_value=False)
            ),
            pytest.raises(HomeAssistantError) as raised,
        ):
            await panel.action_unregister_webhook()
        assert raised.value.translation_key == "webhook_unregistration_failed"
