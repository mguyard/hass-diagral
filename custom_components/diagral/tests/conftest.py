"""Shared test fixtures for hass-diagral."""
import pytest
from unittest.mock import MagicMock
from homeassistant.core import HomeAssistant


@pytest.fixture
def mock_hass():
    """Return a mock Home Assistant instance."""
    return MagicMock(spec=HomeAssistant)


@pytest.fixture
def alarm_config_mock():
    """Return a mock AlarmConfiguration."""
    mock = MagicMock()
    mock.alarm.central.serial = "SERIAL123"
    return mock


@pytest.fixture
def system_status_mock():
    """Return a mock SystemStatus in disarmed state."""
    mock = MagicMock()
    mock.status = "off"
    return mock


@pytest.fixture
def coordinator_mock(alarm_config_mock, system_status_mock):
    """Return a fully populated coordinator mock."""
    mock = MagicMock()
    mock.data = {
        "alarm_config": alarm_config_mock,
        "system_status": system_status_mock,
        "anomalies": None,
        "groups": [],
        "devices_infos": MagicMock(),
    }
    return mock


@pytest.fixture
def diagral_config():
    """Return a mock DiagralConfigData with default options."""
    from custom_components.diagral.const import (
        CONF_ALARMPANEL_ACTIONTYPE_CODE,
        CONF_ALARMPANEL_CODE,
    )
    config = MagicMock()
    config.options.alarmpanel_options = {
        CONF_ALARMPANEL_ACTIONTYPE_CODE: "never",
        CONF_ALARMPANEL_CODE: None,
    }
    return config
