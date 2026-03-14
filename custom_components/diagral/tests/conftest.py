"""Shared test fixtures for hass-diagral."""
import sys
import pytest
from unittest.mock import AsyncMock, MagicMock

# Mock heavy transitive HA dependencies before any diagral code is imported.
# homeassistant.components.cloud pulls in alexa → camera → stream → numpy (+ av/FFmpeg)
# which are not installed in the CI test environment and are not needed for unit tests.
_cloud_mock = MagicMock()
_cloud_mock.CloudNotAvailable = type("CloudNotAvailable", (Exception,), {})
_cloud_mock.CloudNotConnected = type("CloudNotConnected", (Exception,), {})
_cloud_mock.async_active_subscription = AsyncMock(return_value=True)
_cloud_mock.async_delete_cloudhook = AsyncMock()
_cloud_mock.async_get_or_create_cloudhook = AsyncMock(return_value="https://mock.nabu.casa/webhook/test")
sys.modules.setdefault("homeassistant.components.cloud", _cloud_mock)

from homeassistant.core import HomeAssistant  # noqa: E402


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
