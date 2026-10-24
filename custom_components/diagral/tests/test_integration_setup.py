"""Load the real HA platforms with a simulated Diagral transport.

Uses the Home Assistant test helper context directly, so no global pytest HA
plugin (and none of its autouse fixtures) is required by the unit test suite.
"""

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import custom_components.diagral as integration
from custom_components.diagral.const import CONFIG_MINOR_VERSION, CONFIG_VERSION, DOMAIN
from custom_components.diagral.webhook import handle_webhook
from pydiagral.exceptions import AuthenticationError
from pydiagral.models import AlarmConfiguration, DeviceList, SystemStatus
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_test_home_assistant,
    mock_component,
)

from homeassistant import loader
from homeassistant.config_entries import ConfigEntryState
from homeassistant.helpers import entity_registry as er, frame
from homeassistant.helpers.dispatcher import async_dispatcher_connect


@pytest.fixture
async def real_setup(tmp_path, monkeypatch):
    """Run real registry/platform setup, event dispatch and unload without network."""
    api = MagicMock()
    alarm_config = AlarmConfiguration.from_dict(
        {
            "alarm": {
                "name": "Test Alarm",
                "central": {
                    "serial": "CENTRAL001",
                    "firmwares": {"CENTRAL": "1.0", "CENTRALRADIO": "2"},
                },
                "box": {"serial": "TX001"},
            },
            "groups": [
                {"name": "Zone 1", "index": 1, "inputDelay": 0, "outputDelay": 0}
            ],
            "presenceGroup": [1],
        }
    )
    api.__aenter__ = AsyncMock(return_value=api)
    api.__aexit__ = AsyncMock()
    api.get_configuration = AsyncMock(return_value=alarm_config)
    api.get_devices_info = AsyncMock(
        return_value=DeviceList(
            cameras=[], commands=[], sensors=[], sirens=[], transmitters=[]
        )
    )
    api.get_system_status = AsyncMock(
        return_value=SystemStatus(status="OFF", activated_groups=[])
    )
    api.get_anomalies = AsyncMock(return_value=None)
    api.get_webhook = AsyncMock(return_value=None)
    api.register_webhook = AsyncMock()
    api.delete_webhook = AsyncMock()
    monkeypatch.setattr(integration, "DiagralAPI", MagicMock(return_value=api))
    monkeypatch.setattr(
        integration, "get_url", lambda *args, **kwargs: "https://ha.example"
    )

    async with async_test_home_assistant(config_dir=str(tmp_path)) as hass:
        frame.async_setup(hass)
        # Keep cloud services offline, but load the real Diagral and HA platforms.
        mock_component(hass, "cloud")
        integration_path = Path(integration.__file__).parent
        manifest = json.loads((integration_path / "manifest.json").read_text())
        custom_integration = loader.Integration(
            hass,
            "custom_components.diagral",
            integration_path,
            manifest,
            {path.name for path in integration_path.iterdir()},
        )
        hass.data[loader.DATA_CUSTOM_COMPONENTS][DOMAIN] = custom_integration
        hass.data[loader.DATA_INTEGRATIONS][DOMAIN] = custom_integration
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="Test Alarm",
            unique_id="TX001",
            version=CONFIG_VERSION,
            minor_version=CONFIG_MINOR_VERSION,
            data={
                "username": "offline@example.test",
                "password": "offline-password",
                "serial_id": "TX001",
                "pin_code": "0123",
                "api_key": "offline-key",
                "secret_key": "offline-secret",
            },
            options={
                "alarmpanel_options": {
                    "alarmpanel_actiontype_code": "never",
                    "alarmpanel_code": None,
                }
            },
        )
        entry.add_to_hass(hass)
        try:
            assert await hass.config_entries.async_setup(entry.entry_id)
            await hass.async_block_till_done()
            if entry.runtime_data.webhook_task is not None:
                await entry.runtime_data.webhook_task
            await hass.async_block_till_done()
            registry = er.async_get(hass)
            entities = er.async_entries_for_config_entry(registry, entry.entry_id)
            yield SimpleNamespace(hass=hass, entry=entry, api=api, entities=entities)
        finally:
            if entry.state is ConfigEntryState.LOADED:
                await hass.config_entries.async_unload(entry.entry_id)
                await hass.async_block_till_done()
            await hass.async_stop(force=True)


def entity_id(ctx, suffix):
    """Find an entity by its stable unique ID, independently of translations."""
    return next(
        entity.entity_id for entity in ctx.entities if entity.unique_id.endswith(suffix)
    )


async def test_real_setup_loads_seven_entities_and_initial_health(real_setup):
    """All shipped platforms must publish useful states immediately after setup."""
    ctx = real_setup
    assert ctx.entry.state is ConfigEntryState.LOADED
    assert len(ctx.entities) == 7
    assert (
        len([item for item in ctx.entities if item.domain == "alarm_control_panel"])
        == 1
    )
    assert (
        ctx.hass.states.get(entity_id(ctx, "alarm_control_panel")).state == "disarmed"
    )
    assert ctx.hass.states.get(entity_id(ctx, "anomalies")).state == "0"
    assert ctx.hass.states.get(entity_id(ctx, "active_groups")).state == "0"
    assert ctx.hass.states.get(entity_id(ctx, "cloud_connection")).state == "connected"
    assert ctx.hass.states.get(entity_id(ctx, "last_success")).state not in (
        "unknown",
        "unavailable",
    )
    assert ctx.hass.states.get(entity_id(ctx, "webhook_status")).state == "registered"
    assert (
        ctx.hass.states.get(entity_id(ctx, "webhook_last_received")).state == "unknown"
    )
    assert ctx.entry.data["webhook_id"] == ctx.entry.runtime_data.webhook_id
    ctx.api.get_system_status.assert_awaited_once()


async def test_real_webhook_publishes_health_and_alarm_state(real_setup):
    """The actual dispatcher connections must update both health and the alarm."""
    ctx = real_setup
    request = SimpleNamespace(
        json=AsyncMock(
            return_value={
                "transmitter_id": "TX001",
                "alarm_code": 1130,
                "alarm_description": "Offline intrusion fixture",
                "group_index": 1,
                "date_time": "2026-10-22T06:00:00Z",
                "detail": None,
                "user": None,
            }
        )
    )
    await handle_webhook(ctx.hass, ctx.entry.runtime_data.webhook_id, request)
    await ctx.hass.async_block_till_done()
    assert (
        ctx.hass.states.get(entity_id(ctx, "alarm_control_panel")).state == "triggered"
    )
    assert ctx.hass.states.get(entity_id(ctx, "webhook_status")).state == "received"
    assert ctx.hass.states.get(entity_id(ctx, "webhook_last_received")).state not in (
        "unknown",
        "unavailable",
    )


async def test_real_legacy_event_does_not_trigger_another_entry(real_setup):
    """Publish the public signal once while only the owning panel reacts."""
    ctx = real_setup
    other = MockConfigEntry(
        domain=DOMAIN,
        title="Other Test Alarm",
        unique_id="TX002",
        version=CONFIG_VERSION,
        minor_version=CONFIG_MINOR_VERSION,
        data={**ctx.entry.data, "serial_id": "TX002", "webhook_id": "other-secret"},
        options=ctx.entry.options,
    )
    other.add_to_hass(ctx.hass)
    legacy_events = []
    unsubscribe = async_dispatcher_connect(
        ctx.hass, "signal-diagral-webhook-ALERT", legacy_events.append
    )
    try:
        assert await ctx.hass.config_entries.async_setup(other.entry_id)
        await ctx.hass.async_block_till_done()
        if other.runtime_data.webhook_task is not None:
            await other.runtime_data.webhook_task
        registry = er.async_get(ctx.hass)
        other_entities = er.async_entries_for_config_entry(registry, other.entry_id)
        other_panel = next(
            item.entity_id
            for item in other_entities
            if item.domain == "alarm_control_panel"
        )
        request = SimpleNamespace(
            json=AsyncMock(
                return_value={
                    "transmitter_id": "TX001",
                    "alarm_code": "1130",
                    "date_time": "2026-10-22T06:00:00Z",
                }
            )
        )
        await handle_webhook(ctx.hass, ctx.entry.runtime_data.webhook_id, request)
        await ctx.hass.async_block_till_done()
        assert (
            ctx.hass.states.get(entity_id(ctx, "alarm_control_panel")).state
            == "triggered"
        )
        assert ctx.hass.states.get(other_panel).state == "disarmed"
        assert len(legacy_events) == 1
        assert legacy_events[0]["entry_id"] == ctx.entry.entry_id
    finally:
        unsubscribe()
        if other.state is ConfigEntryState.LOADED:
            await ctx.hass.config_entries.async_unload(other.entry_id)


async def test_real_cloud_failure_recovery_and_unload(real_setup):
    """Real coordinator notifications must publish unavailability and recovery."""
    ctx = real_setup
    coordinator = ctx.entry.runtime_data.coordinator
    ctx.api.get_configuration.side_effect = AuthenticationError("offline failure")
    await coordinator.async_refresh()
    await ctx.hass.async_block_till_done()
    assert (
        ctx.hass.states.get(entity_id(ctx, "alarm_control_panel")).state
        == "unavailable"
    )
    assert (
        ctx.hass.states.get(entity_id(ctx, "cloud_connection")).state == "unavailable"
    )
    cloud_health = ctx.hass.states.get(entity_id(ctx, "cloud_connection"))
    assert cloud_health.attributes["last_error"] == "authentication_failed"
    ctx.api.get_configuration.side_effect = None
    await coordinator.async_refresh()
    await ctx.hass.async_block_till_done()
    assert (
        ctx.hass.states.get(entity_id(ctx, "alarm_control_panel")).state == "disarmed"
    )
    assert ctx.hass.states.get(entity_id(ctx, "cloud_connection")).state == "connected"
    runtime = ctx.entry.runtime_data
    assert await ctx.hass.config_entries.async_unload(ctx.entry.entry_id)
    await ctx.hass.async_block_till_done()
    # HA intentionally retains unavailable placeholders for enabled registry
    # entries on unload (Entity.async_remove), instead of deleting their states.
    for item in ctx.entities:
        state = ctx.hass.states.get(item.entity_id)
        assert state.state == "unavailable"
        assert state.attributes["restored"] is True
    assert runtime.webhook_task is None
    assert not runtime.webhook_local_registered
    ctx.api.__aexit__.assert_awaited_once()
