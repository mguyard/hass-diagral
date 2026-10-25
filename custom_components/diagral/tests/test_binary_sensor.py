"""Tests for binary_sensor.py: the Diagral cloud connectivity sensor."""

import json
import pathlib
from types import SimpleNamespace
from unittest.mock import MagicMock

from custom_components.diagral.binary_sensor import DiagralCloudConnection
import pytest

from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.const import EntityCategory

TRANSLATIONS = pathlib.Path(__file__).parent.parent / "translations"


def make_connection(last_update_success: bool) -> DiagralCloudConnection:
    """Return the sensor bound to a coordinator in the given state."""
    coordinator = MagicMock(last_update_success=last_update_success)
    coordinator.data = {
        "alarm_config": SimpleNamespace(
            alarm=SimpleNamespace(central=SimpleNamespace(serial="FAKECENTRAL01"))
        )
    }
    return DiagralCloudConnection(coordinator, MagicMock(entry_id="entry1"))


class TestCloudConnection:
    """The sensor reports a Diagral outage instead of disappearing with it."""

    @pytest.mark.parametrize("reachable", [True, False], ids=["up", "down"])
    def test_follows_the_last_refresh(self, reachable):
        """Connected while polling works, disconnected otherwise, never unavailable."""
        sensor = make_connection(reachable)

        assert sensor.is_on is reachable
        assert sensor.available is True

    def test_is_a_diagnostic_connectivity_sensor(self):
        """It is a connectivity sensor in the diagnostic section."""
        sensor = make_connection(True)

        assert sensor.unique_id == "entry1_diagral_FAKECENTRAL01_cloud_connection"
        assert sensor.device_class == BinarySensorDeviceClass.CONNECTIVITY
        assert sensor.entity_category == EntityCategory.DIAGNOSTIC

    @pytest.mark.parametrize("language", ["en", "fr"])
    def test_is_translated(self, language):
        """Both languages name the sensor."""
        translations = json.loads(
            (TRANSLATIONS / f"{language}.json").read_text(encoding="utf-8")
        )
        assert translations["entity"]["binary_sensor"]["cloud_connection"]["name"]
