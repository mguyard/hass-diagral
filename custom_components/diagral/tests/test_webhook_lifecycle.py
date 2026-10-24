"""Offline regression tests for webhook ownership, retries, routing and cleanup."""

import asyncio
import json
import logging
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import custom_components.diagral as integration
from custom_components.diagral import webhook
from custom_components.diagral.models import DiagralData
from pydiagral.exceptions import DiagralAPIError
import pytest


@pytest.fixture
def context(monkeypatch):
    """Build an entry with no real Home Assistant server or external requests."""
    api = SimpleNamespace(
        get_webhook=AsyncMock(return_value=None),
        register_webhook=AsyncMock(),
        update_webhook=AsyncMock(),
        delete_webhook=AsyncMock(),
        __aenter__=AsyncMock(),
        __aexit__=AsyncMock(),
    )
    runtime = DiagralData(
        config=SimpleNamespace(serial_id="TX001"),
        coordinator=SimpleNamespace(
            data={}, async_request_refresh=AsyncMock(), async_shutdown=AsyncMock()
        ),
        api=api,
        webhook_id="stable-secret",
    )
    entry = SimpleNamespace(
        entry_id="entry-a",
        runtime_data=runtime,
        title="Alarm",
        data={"webhook_id": "stable-secret"},
        options={},
    )
    hass = SimpleNamespace(
        data={},
        bus=SimpleNamespace(async_fire=Mock()),
        config_entries=SimpleNamespace(
            async_entries=Mock(return_value=[entry]),
            async_loaded_entries=Mock(return_value=[entry]),
            async_update_entry=Mock(
                side_effect=lambda target, **kwargs: setattr(
                    target, "data", kwargs["data"]
                )
            ),
            async_unload_platforms=AsyncMock(return_value=True),
            async_forward_entry_setups=AsyncMock(),
        ),
        async_create_background_task=lambda coro, name: asyncio.create_task(
            coro, name=name
        ),
    )
    local_register, local_unregister = Mock(), Mock()
    monkeypatch.setattr(integration, "webhook_async_register", local_register)
    monkeypatch.setattr(integration, "webhook_async_unregister", local_unregister)
    monkeypatch.setattr(integration, "get_url", Mock(return_value="https://ha.example"))
    monkeypatch.setattr(integration, "async_dispatcher_send", Mock())
    monkeypatch.setattr(integration, "ir", Mock())
    monkeypatch.setattr(webhook, "async_dispatcher_send", Mock())
    return SimpleNamespace(
        hass=hass,
        entry=entry,
        runtime=runtime,
        api=api,
        local_register=local_register,
        local_unregister=local_unregister,
    )


def subscription(url):
    """Build a subscription with every notification type enabled."""
    return SimpleNamespace(
        webhook_url=url,
        subscriptions=SimpleNamespace(alert=True, anomaly=True, state=True),
    )


def notification(**kwargs):
    """Build a synthetic notification with optional field overrides."""
    data = {
        "transmitter_id": "TX001",
        "alarm_code": "1130",
        "alarm_description": "Alert",
        "group_index": "1",
        "date_time": "2026-10-22T06:00:00Z",
        "detail": {"device_type": "sensor", "device_index": "1"},
        "user": {"username": "Resident", "user_type": "owner"},
    }
    return {**data, **kwargs}


def test_id_is_persisted_once(context, monkeypatch):
    """Id is persisted once."""
    ctx = context
    ctx.entry.data = {"serial_id": "TX001"}
    generate = Mock(return_value="persisted-secret")
    monkeypatch.setattr(integration, "webhook_generate_id", generate)
    assert integration._ensure_webhook_id(ctx.hass, ctx.entry) == "persisted-secret"
    assert integration._ensure_webhook_id(ctx.hass, ctx.entry) == "persisted-secret"
    generate.assert_called_once()
    assert ctx.entry.data["serial_id"] == "TX001"


async def test_local_handler_precedes_remote_and_registration_is_idempotent(context):
    """Local handler precedes remote and registration is idempotent."""
    ctx = context

    async def create(**kwargs):
        assert ctx.runtime.webhook_local_registered
        ctx.local_register.assert_called_once()
        ctx.api.get_webhook.return_value = subscription(kwargs["webhook_url"])

    ctx.api.register_webhook.side_effect = create
    assert await integration._register_webhook_once(ctx.hass, ctx.entry)
    assert await integration._register_webhook_once(ctx.hass, ctx.entry)
    ctx.api.register_webhook.assert_awaited_once()
    ctx.api.update_webhook.assert_not_awaited()
    ctx.local_register.assert_called_once()
    assert ctx.runtime.webhook_status == "registered"
    assert ctx.runtime.webhook_last_received is None


async def test_remote_failure_has_bounded_retries_and_safe_logs(
    context, monkeypatch, caplog
):
    """Remote failure has bounded retries and safe logs."""
    ctx = context
    ctx.api.get_webhook.side_effect = DiagralAPIError(
        "credential-secret https://private.example/secret"
    )
    monkeypatch.setattr(integration, "_WEBHOOK_RETRY_DELAYS", (0, 0))
    with caplog.at_level(logging.WARNING):
        await integration._webhook_registration_worker(ctx.hass, ctx.entry)
    assert ctx.api.get_webhook.await_count == 3
    assert ctx.runtime.webhook_retry_attempts == 2
    assert ctx.runtime.webhook_status == "retry_exhausted"
    assert "credential-secret" not in caplog.text
    assert "private.example" not in caplog.text


async def test_retry_recovers_without_touching_polling(context, monkeypatch):
    """Retry recovers without touching polling."""
    ctx = context
    ctx.api.get_webhook.side_effect = [TimeoutError(), None]
    monkeypatch.setattr(integration, "_WEBHOOK_RETRY_DELAYS", (0, 0))
    await integration._webhook_registration_worker(ctx.hass, ctx.entry)
    assert ctx.api.get_webhook.await_count == 2
    assert ctx.runtime.webhook_status == "registered"
    assert ctx.runtime.webhook_last_error is None
    ctx.runtime.coordinator.async_shutdown.assert_not_awaited()


async def test_different_subscription_requires_explicit_action(context):
    """Different subscription requires explicit action."""
    ctx = context
    ctx.api.get_webhook.return_value = subscription(
        "https://other.example/api/webhook/private"
    )
    assert not await integration._register_webhook_once(ctx.hass, ctx.entry)
    assert ctx.runtime.webhook_status == "conflict"
    ctx.api.update_webhook.assert_not_awaited()
    await integration.register_webhook(ctx.hass, ctx.entry, ctx.api, "HA Action")
    ctx.api.update_webhook.assert_awaited_once()


async def test_old_same_origin_random_id_is_migrated(context):
    """Old same origin random id is migrated."""
    ctx = context
    ctx.api.get_webhook.return_value = subscription(
        "https://ha.example/api/webhook/old-random-id"
    )
    assert await integration._register_webhook_once(ctx.hass, ctx.entry)
    ctx.api.update_webhook.assert_awaited_once()
    assert ctx.runtime.webhook_id == "stable-secret"


def test_shared_cloudhook_origin_does_not_prove_ownership():
    """Shared cloudhook origin does not prove ownership."""
    assert not integration._same_local_webhook_origin(
        "https://hooks.nabu.casa/old", "https://hooks.nabu.casa/new"
    )
    assert not integration._same_local_webhook_origin(
        "https://ha.example.evil/api/webhook/old", "https://ha.example/api/webhook/new"
    )


@pytest.mark.parametrize(
    ("stored_url", "actual_url", "new_url"),
    [
        (None, "https://hooks.nabu.casa/foreign", "https://hooks.nabu.casa/ours"),
        (
            "https://ha.example/api/webhook/ours",
            "https://ha.example/api/webhook/foreign",
            "https://ha.example/api/webhook/new",
        ),
    ],
    ids=["untracked-shared-cloud-host", "tracked-same-direct-host"],
)
def test_foreign_url_cannot_be_adopted_by_origin_alone(
    context, stored_url, actual_url, new_url
):
    """Shared hosts never override a known fingerprint or prove cloud ownership."""
    ctx = context
    if stored_url is not None:
        integration._remember_subscription(ctx.hass, ctx.entry, stored_url)
    assert not integration._owns_subscription(ctx.entry, actual_url, new_url)


async def test_unload_removes_handler_but_preserves_cloudhook_identity_after_remote_error(
    context, monkeypatch
):
    """Unload removes handler but preserves cloudhook identity after remote error."""
    ctx = context
    ctx.runtime.webhook_url = "https://hooks.nabu.casa/secret"
    ctx.runtime.webhook_is_cloudhook = True
    ctx.runtime.webhook_local_registered = True
    ctx.api.get_webhook.side_effect = TimeoutError()
    delete_cloudhook = AsyncMock()
    monkeypatch.setitem(
        sys.modules,
        "homeassistant.components.cloud",
        SimpleNamespace(async_delete_cloudhook=delete_cloudhook),
    )
    assert await integration.async_unload_entry(ctx.hass, ctx.entry)
    ctx.local_unregister.assert_called_once_with(ctx.hass, "stable-secret")
    delete_cloudhook.assert_not_awaited()
    ctx.runtime.coordinator.async_shutdown.assert_awaited_once()
    ctx.api.__aexit__.assert_awaited_once()
    assert ctx.runtime.webhook_id == "stable-secret"


async def test_explicit_unregister_removes_cloudhook_even_when_remote_fails(
    context, monkeypatch
):
    """Explicit unregister removes cloudhook even when remote fails."""
    ctx = context
    ctx.runtime.webhook_url = "https://hooks.nabu.casa/secret"
    ctx.runtime.webhook_is_cloudhook = True
    ctx.runtime.webhook_local_registered = True
    ctx.api.get_webhook.side_effect = TimeoutError()
    delete_cloudhook = AsyncMock()
    monkeypatch.setitem(
        sys.modules,
        "homeassistant.components.cloud",
        SimpleNamespace(async_delete_cloudhook=delete_cloudhook),
    )
    await integration.unregister_webhook(
        ctx.hass, ctx.entry, ctx.api, "stable-secret", "HA Action"
    )
    ctx.local_unregister.assert_called_once_with(ctx.hass, "stable-secret")
    delete_cloudhook.assert_awaited_once_with(ctx.hass, "stable-secret")


async def test_unload_does_not_delete_someone_elses_subscription(context):
    """Unload does not delete someone elses subscription."""
    ctx = context
    ctx.runtime.webhook_url = "https://ha.example/api/webhook/stable-secret"
    ctx.api.get_webhook.return_value = subscription("https://other.example/secret")
    await integration.async_unload_entry(ctx.hass, ctx.entry)
    ctx.api.delete_webhook.assert_not_awaited()


async def test_failed_platform_unload_keeps_resources(context):
    """Failed platform unload keeps resources."""
    ctx = context
    ctx.hass.config_entries.async_unload_platforms.return_value = False
    assert not await integration.async_unload_entry(ctx.hass, ctx.entry)
    ctx.api.__aexit__.assert_not_awaited()
    ctx.local_unregister.assert_not_called()
    assert not ctx.runtime.stopping


async def test_unregister_cancels_pending_retry_and_prevents_later_requests(
    context, monkeypatch
):
    """Unregister cancels pending retry and prevents later requests."""
    ctx = context
    waiting = asyncio.Event()

    async def fail(*args, **kwargs):
        waiting.set()
        return False

    attempt = AsyncMock(side_effect=fail)
    monkeypatch.setattr(integration, "_register_webhook_once", attempt)
    integration._start_webhook_registration(ctx.hass, ctx.entry)
    await waiting.wait()
    task = ctx.runtime.webhook_task
    await integration.unregister_webhook(
        ctx.hass, ctx.entry, ctx.api, ctx.runtime.webhook_id
    )
    assert task.done()
    assert ctx.runtime.webhook_task is None
    attempt.assert_awaited_once()


async def test_setup_failure_closes_session_and_coordinator(context, monkeypatch):
    """Setup failure closes session and coordinator."""
    ctx = context
    ctx.entry.data.update(
        username="user",
        password="secret",
        serial_id="TX001",
        pin_code="1234",
        api_key="key",
        secret_key="secret",
    )
    ctx.entry.options = {"alarmpanel_options": {}}
    coordinator = SimpleNamespace(
        async_config_entry_first_refresh=AsyncMock(
            side_effect=RuntimeError("setup failed")
        ),
        async_shutdown=AsyncMock(),
    )
    monkeypatch.setattr(integration, "DiagralAPI", Mock(return_value=ctx.api))
    monkeypatch.setattr(
        integration, "DiagralDataUpdateCoordinator", Mock(return_value=coordinator)
    )
    with pytest.raises(RuntimeError, match="setup failed"):
        await integration.async_setup_entry(ctx.hass, ctx.entry)
    ctx.api.__aexit__.assert_awaited_once()
    coordinator.async_shutdown.assert_awaited_once()


async def test_platform_failure_cleans_partial_setup(context, monkeypatch):
    """Platform failure cleans partial setup."""
    ctx = context
    ctx.entry.data.update(
        username="user",
        password="secret",
        serial_id="TX001",
        pin_code="1234",
        api_key="key",
        secret_key="secret",
    )
    ctx.entry.options = {"alarmpanel_options": {}}
    coordinator = SimpleNamespace(
        async_config_entry_first_refresh=AsyncMock(), async_shutdown=AsyncMock()
    )
    ctx.hass.config_entries.async_forward_entry_setups.side_effect = RuntimeError(
        "platform failed"
    )
    monkeypatch.setattr(integration, "DiagralAPI", Mock(return_value=ctx.api))
    monkeypatch.setattr(
        integration, "DiagralDataUpdateCoordinator", Mock(return_value=coordinator)
    )
    with pytest.raises(RuntimeError, match="platform failed"):
        await integration.async_setup_entry(ctx.hass, ctx.entry)
    ctx.api.__aexit__.assert_awaited_once()
    ctx.hass.config_entries.async_unload_platforms.assert_awaited_once()
    assert ctx.entry.runtime_data.stopping


@pytest.mark.parametrize(
    "payload",
    [
        [],
        None,
        {},
        notification(alarm_code="oops"),
        notification(detail=[]),
        notification(date_time="not-a-date"),
    ],
)
async def test_invalid_payload_does_not_publish_or_mark_received(context, payload):
    """Invalid payload does not publish or mark received."""
    ctx = context
    ctx.runtime.webhook_local_registered = True
    await webhook.handle_webhook(
        ctx.hass,
        ctx.runtime.webhook_id,
        SimpleNamespace(json=AsyncMock(return_value=payload)),
    )
    ctx.hass.bus.async_fire.assert_not_called()
    assert ctx.runtime.webhook_last_received is None


async def test_unloaded_entries_are_skipped(context):
    """Unloaded entries are skipped."""
    ctx = context
    ctx.hass.config_entries.async_entries.return_value = [
        SimpleNamespace(entry_id="unloaded"),
        ctx.entry,
    ]
    ctx.runtime.webhook_local_registered = True
    await webhook.handle_webhook(
        ctx.hass,
        ctx.runtime.webhook_id,
        SimpleNamespace(json=AsyncMock(return_value=notification())),
    )
    ctx.hass.bus.async_fire.assert_called_once()
    ctx.hass.config_entries.async_loaded_entries.assert_called_once_with("diagral")
    ctx.hass.config_entries.async_entries.assert_not_called()


async def test_wrong_transmitter_cannot_trigger_another_panel(context):
    """Wrong transmitter cannot trigger another panel."""
    ctx = context
    ctx.runtime.webhook_local_registered = True
    await webhook.handle_webhook(
        ctx.hass,
        ctx.runtime.webhook_id,
        SimpleNamespace(
            json=AsyncMock(return_value=notification(transmitter_id="TX999"))
        ),
    )
    ctx.hass.bus.async_fire.assert_not_called()
    assert ctx.runtime.webhook_last_received is None


async def test_valid_event_is_json_serializable_and_entry_scoped(context):
    """Valid event is json serializable and entry scoped."""
    ctx = context
    ctx.runtime.webhook_local_registered = True
    await webhook.handle_webhook(
        ctx.hass,
        ctx.runtime.webhook_id,
        SimpleNamespace(json=AsyncMock(return_value=notification())),
    )
    signal = webhook.async_dispatcher_send.call_args.args
    assert signal[1] == "signal-diagral-entry-a-webhook-ALERT"
    event_type, envelope = ctx.hass.bus.async_fire.call_args.args
    assert event_type == "DIAGRAL_EVENT"
    assert envelope["entry_id"] == "entry-a"
    assert envelope["data"]["user"]["username"] == "Resident"
    assert json.loads(json.dumps(envelope)) == envelope
    assert ctx.runtime.webhook_status == "received"
    assert ctx.runtime.webhook_last_received.tzinfo is not None


async def test_status_refreshes_only_own_coordinator(context):
    """Status refreshes only own coordinator."""
    ctx = context
    ctx.runtime.webhook_local_registered = True
    await webhook.handle_webhook(
        ctx.hass,
        ctx.runtime.webhook_id,
        SimpleNamespace(
            json=AsyncMock(return_value=notification(alarm_code="3401", detail=None))
        ),
    )
    ctx.runtime.coordinator.async_request_refresh.assert_awaited_once()


async def test_integer_codes_and_indexes_are_accepted(context):
    """Integer codes and indexes are accepted."""
    ctx = context
    ctx.runtime.webhook_local_registered = True
    payload = notification(
        alarm_code=1130,
        group_index=1,
        detail={"device_type": "sensor", "device_index": 1},
    )
    await webhook.handle_webhook(
        ctx.hass,
        ctx.runtime.webhook_id,
        SimpleNamespace(json=AsyncMock(return_value=payload)),
    )
    ctx.hass.bus.async_fire.assert_called_once()
    assert ctx.runtime.webhook_status == "received"
