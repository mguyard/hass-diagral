"""Tests for logbook.py: received webhooks described in the activity log."""

from types import SimpleNamespace
from unittest.mock import MagicMock

from custom_components.diagral.const import DIAGRAL_EVENT, DOMAIN
from custom_components.diagral.logbook import async_describe_events
import pytest

from homeassistant.components.logbook import (
    LOGBOOK_ENTRY_ENTITY_ID,
    LOGBOOK_ENTRY_MESSAGE,
    LOGBOOK_ENTRY_NAME,
)

PANEL = "alarm_control_panel.fake_home_central"


def describer():
    """Register the platform and return the describer of DIAGRAL_EVENT."""
    registered = {}

    def describe_event(domain, event_type, describe):
        registered[(domain, event_type)] = describe

    async_describe_events(MagicMock(), describe_event)
    return registered[(DOMAIN, DIAGRAL_EVENT)]


def describe(event_data: dict) -> dict:
    """Describe one DIAGRAL_EVENT published for the fake panel."""
    return describer()(SimpleNamespace(data={"entity_id": PANEL, **event_data}))


def user(name):
    """Return the user as a model (live event) and as a dict (from the database)."""
    return [SimpleNamespace(username=name, user_type="owner"), {"username": name}]


class TestDescribe:
    """Each received webhook becomes a readable logbook entry."""

    @pytest.mark.parametrize("who", user("Fake User"), ids=["live", "recorded"])
    def test_status_names_the_user(self, who):
        """A state change says what Diagral reported and who did it."""
        entry = describe(
            {
                "type": "STATUS",
                "entry_id": "entry1",
                "data": {
                    "alarm_code": "3407",
                    "alarm_description": "REMOTE-ARMING-OF-GROUP",
                    "user": who,
                },
            }
        )
        assert entry[LOGBOOK_ENTRY_NAME] == "Diagral"
        assert entry[LOGBOOK_ENTRY_MESSAGE] == (
            "STATUS webhook: REMOTE-ARMING-OF-GROUP (3407), by Fake User"
        )
        assert entry[LOGBOOK_ENTRY_ENTITY_ID] == PANEL

    @pytest.mark.parametrize(
        "detail",
        [SimpleNamespace(device_label="Hall sensor"), {"device_label": "Hall sensor"}],
        ids=["live", "recorded"],
    )
    def test_alert_names_the_device(self, detail):
        """An alert says which device raised it."""
        entry = describe(
            {
                "type": "ALERT",
                "entry_id": "entry1",
                "data": {
                    "alarm_code": "1130",
                    "alarm_description": "Intrusion",
                    "detail": detail,
                },
            }
        )
        assert entry[LOGBOOK_ENTRY_MESSAGE] == (
            "ALERT webhook: Intrusion (1130), Hall sensor"
        )

    def test_event_without_entity_is_not_attached(self):
        """An event recorded before entity_id existed is still described."""
        entry = describer()(
            SimpleNamespace(
                data={"type": "ANOMALY", "data": {"alarm_description": "Low battery"}}
            )
        )
        assert entry[LOGBOOK_ENTRY_MESSAGE] == "ANOMALY webhook: Low battery"
        assert entry[LOGBOOK_ENTRY_ENTITY_ID] is None
