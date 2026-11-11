"""Tests for binary_sensor.py: the Diagral cloud health sensors."""

import json
import pathlib
from types import SimpleNamespace
from unittest.mock import MagicMock

from custom_components.diagral.binary_sensor import (
    CLOUD_CONNECTION,
    CLOUD_REACHABLE,
    FALLBACK_API_CONNECTION,
    PRIMARY_API_CONNECTION,
    DiagralHealthSensor,
    async_setup_entry,
)
import pytest

from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.const import EntityCategory

TRANSLATIONS = pathlib.Path(__file__).parent.parent / "translations"
DESCRIPTIONS = [
    CLOUD_CONNECTION,
    CLOUD_REACHABLE,
    PRIMARY_API_CONNECTION,
    FALLBACK_API_CONNECTION,
]
DESCRIPTION_IDS = ["cloud-connection", "cloud-reachable", "primary-api", "fallback-api"]


def make_sensor(
    description,
    last_update_success: bool = True,
    cloud_reachable: bool | None = True,
    fallback_api_connected: bool | None = None,
) -> DiagralHealthSensor:
    """Return a sensor bound to a coordinator in the given state."""
    coordinator = MagicMock(
        last_update_success=last_update_success,
        cloud_reachable=cloud_reachable,
        fallback_api_connected=fallback_api_connected,
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


class TestPrimaryAPIConnection:
    """A public ping cannot certify authenticated Emerald requests."""

    @pytest.mark.parametrize("connected", [None, False, True])
    @pytest.mark.parametrize("ping", [False, True])
    def test_reports_primary_probe_independently(self, connected, ping):
        """The primary diagnostic follows only the SDK's authenticated probe."""
        sensor = make_sensor(PRIMARY_API_CONNECTION, cloud_reachable=ping)
        sensor.coordinator.api.primary_api_connected = connected
        assert sensor.is_on is connected
        assert sensor.available is True


class TestHealthSensors:
    """Health sensors are diagnostic connectivity sensors with stable unique ids."""

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

    @pytest.mark.parametrize("supports_failover", [False, True])
    async def test_setup_adds_supported_health_sensors(self, supports_failover):
        """A capable client keeps its fallback diagnostic while Emerald is active."""
        coordinator = make_sensor(CLOUD_CONNECTION).coordinator
        coordinator.api.supports_failover = supports_failover
        coordinator.api.uses_topaze = False
        entry = SimpleNamespace(
            entry_id="entry1", runtime_data=SimpleNamespace(coordinator=coordinator)
        )
        entities = []

        await async_setup_entry(MagicMock(), entry, entities.extend)

        expected = DESCRIPTIONS if supports_failover else DESCRIPTIONS[:2]
        assert [entity.entity_description for entity in entities] == expected
        assert len({entity.unique_id for entity in entities}) == len(expected)


class TestFallbackAPIConnection:
    """Fallback connectivity is independent from Emerald and coordinator health."""

    def test_command_preflight_backend_change_is_visible_without_another_poll(self):
        """A command's listener update immediately reflects the SDK's fresh decision."""
        sensor = make_sensor(FALLBACK_API_CONNECTION, fallback_api_connected=True)
        sensor.coordinator.api.supports_failover = True
        for current in (True, False, True, False):
            sensor.coordinator.api.fallback_api_connected = current
            assert sensor.is_on is current
        assert sensor.coordinator.fallback_api_connected is True

    @pytest.mark.parametrize(
        "connected", [True, False, None], ids=["connected", "disconnected", "unread"]
    )
    @pytest.mark.parametrize(
        "cloud_reachable", [True, False], ids=["emerald-up", "emerald-down"]
    )
    @pytest.mark.parametrize(
        "last_update_success", [True, False], ids=["core-up", "core-down"]
    )
    def test_follows_only_fallback_read(
        self, connected, cloud_reachable, last_update_success
    ):
        """Expose unknown before a read and disconnected on failure, never stale green."""
        sensor = make_sensor(
            FALLBACK_API_CONNECTION,
            last_update_success=last_update_success,
            cloud_reachable=cloud_reachable,
            fallback_api_connected=connected,
        )
        sensor.coordinator.reset_mock()

        assert sensor.is_on is connected
        assert sensor.available is True
        assert sensor.coordinator.mock_calls == []

    @pytest.mark.parametrize(
        ("language", "expected"), [("fr", "API de secours"), ("en", "Fallback API")]
    )
    def test_requested_name(self, language, expected):
        """Use the requested diagnostic label in each supported language."""
        translations = json.loads(
            (TRANSLATIONS / f"{language}.json").read_text(encoding="utf-8")
        )
        assert (
            translations["entity"]["binary_sensor"]["fallback_api_connection"]["name"]
            == expected
        )

    def test_unique_id_is_scoped_to_entry_and_central(self):
        """The new sensor cannot collide with another installation or an existing key."""
        first = make_sensor(FALLBACK_API_CONNECTION)
        second = DiagralHealthSensor(
            first.coordinator, MagicMock(entry_id="entry2"), FALLBACK_API_CONNECTION
        )
        first.coordinator.data["alarm_config"].alarm.central.serial = "FAKECENTRAL02"
        third = DiagralHealthSensor(
            first.coordinator, MagicMock(entry_id="entry1"), FALLBACK_API_CONNECTION
        )

        assert first.unique_id == "entry1_diagral_FAKECENTRAL01_fallback_api_connection"
        assert len({first.unique_id, second.unique_id, third.unique_id}) == 3
