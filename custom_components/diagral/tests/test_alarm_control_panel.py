"""Tests for pure logic methods of DiagralAlarmControlPanel (Tier 2).

Tests _get_ha_state(), _validate_code(), and _is_code_arm_required()
without making real API calls or instantiating the full entity.
"""
import pytest
from unittest.mock import MagicMock
from homeassistant.components.alarm_control_panel import AlarmControlPanelState

from custom_components.diagral.alarm_control_panel import DiagralAlarmControlPanel
from custom_components.diagral.const import (
    CONF_ALARMPANEL_ACTIONTYPE_CODE,
    CONF_ALARMPANEL_CODE,
)


def make_panel_mock(actiontype_code: str, code: int | None, alarm_state: AlarmControlPanelState) -> DiagralAlarmControlPanel:
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
