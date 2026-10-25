"""Tests for binary_sensor.py: the Diagral cloud health sensors."""

import json
import pathlib
from types import SimpleNamespace
from unittest.mock import MagicMock

from custom_components.diagral.binary_sensor import (
    CLOUD_CONNECTION,
    CLOUD_REACHABLE,
    DiagralHealthSensor,
)
import pytest

from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.const import EntityCategory

TRANSLATIONS = pathlib.Path(__file__).parent.parent / "translations"
DESCRIPTIONS = [CLOUD_CONNECTION, CLOUD_REACHABLE]
DESCRIPTION_IDS = ["cloud-connection", "cloud-reachable"]


def make_sensor(
    description, last_update_success: bool = True, cloud_reachable: bool | None = True
) -> DiagralHealthSensor:
    """Return a sensor bound to a coordinator in the given state."""
    coordinator = MagicMock(
        last_update_success=last_update_success, cloud_reachable=cloud_reachable
    )
    coordinator.data = {
        "alarm_config": SimpleNamespace(
            alarm=SimpleNamespace(central=SimpleNamespace(serial="FAKECENTRAL01"))
        )
    }
    return DiagralHealthSensor(coordinator, MagicMock(entry_id="entry1"), description)


class TestCloudConnection:
    """The sensor reports a Diagral outage instead of disappearing with it."""

    @pytest.mark.parametrize("reachable", [True, False], ids=["up", "down"])
    def test_follows_the_last_refresh(self, reachable):
        """Connected while polling works, disconnected otherwise, never unavailable."""
        sensor = make_sensor(CLOUD_CONNECTION, last_update_success=reachable)

        assert sensor.is_on is reachable
        assert sensor.available is True


class TestCloudReachable:
    """The sensor tells whether the cloud answers at all, credentials aside."""

    @pytest.mark.parametrize(
        "reachable", [True, False, None], ids=["answers", "silent", "not-yet-pinged"]
    )
    def test_follows_the_last_ping(self, reachable):
        """It mirrors the last ping, and stays available through an outage."""
        sensor = make_sensor(
            CLOUD_REACHABLE, last_update_success=False, cloud_reachable=reachable
        )

        assert sensor.is_on is reachable
        assert sensor.available is True


class TestHealthSensors:
    """Both sensors are diagnostic connectivity sensors with a stable unique id."""

    @pytest.mark.parametrize("description", DESCRIPTIONS, ids=DESCRIPTION_IDS)
    def test_is_a_diagnostic_connectivity_sensor(self, description):
        """It is a connectivity sensor in the diagnostic section."""
        sensor = make_sensor(description)

        assert sensor.unique_id == f"entry1_diagral_FAKECENTRAL01_{description.key}"
        assert sensor.device_class == BinarySensorDeviceClass.CONNECTIVITY
        assert sensor.entity_category == EntityCategory.DIAGNOSTIC

    def test_existing_key_is_kept(self):
        """Renaming a key would orphan the entity users already have."""
        assert CLOUD_CONNECTION.key == "cloud_connection"

    @pytest.mark.parametrize("description", DESCRIPTIONS, ids=DESCRIPTION_IDS)
    @pytest.mark.parametrize("language", ["en", "fr"])
    def test_is_translated(self, language, description):
        """Both languages name the sensor."""
        translations = json.loads(
            (TRANSLATIONS / f"{language}.json").read_text(encoding="utf-8")
        )
        name = translations["entity"]["binary_sensor"][description.translation_key]
        assert name["name"]
