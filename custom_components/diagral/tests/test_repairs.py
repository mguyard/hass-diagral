"""Tests for repairs.py: taking over a webhook subscription owned elsewhere."""

from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.diagral import WebhookUnavailable
from custom_components.diagral.repairs import (
    RetryWebhookFlow,
    TakeOverWebhookFlow,
    async_create_fix_flow,
)
import pytest

from homeassistant.config_entries import ConfigEntryState


def make_flow(entry: MagicMock | None) -> TakeOverWebhookFlow:
    """Return the fix flow bound to a hass whose registry holds the entry."""
    flow = TakeOverWebhookFlow("entry1")
    flow.hass = MagicMock()
    flow.hass.config_entries.async_get_entry.return_value = entry
    flow.handler = "diagral"
    flow.issue_id = "webhook_owned_elsewhere_entry1"
    flow.flow_id = "flow"
    return flow


def make_loaded_entry() -> MagicMock:
    """Return a loaded config entry mock."""
    entry = MagicMock()
    entry.state = ConfigEntryState.LOADED
    entry.runtime_data.webhook_id = None
    return entry


async def test_fix_flow_is_created_for_the_entry():
    """The fix flow targets the entry named in the issue data."""
    flow = await async_create_fix_flow(
        MagicMock(), "webhook_owned_elsewhere_entry1", {"entry_id": "entry1"}
    )
    assert isinstance(flow, TakeOverWebhookFlow)


async def test_confirm_takes_over_the_subscription():
    """Confirming registers the webhook with take_over and stores its id."""
    entry = make_loaded_entry()
    flow = make_flow(entry)
    with patch(
        "custom_components.diagral.repairs.register_webhook",
        AsyncMock(return_value="NEWID"),
    ) as register:
        result = await flow.async_step_confirm({})

    register.assert_awaited_once()
    assert register.call_args.kwargs["take_over"] is True
    assert entry.runtime_data.webhook_id == "NEWID"
    assert result["type"] == "create_entry"


async def test_confirm_aborts_when_entry_not_loaded():
    """Without a loaded entry there is no API session to take over with."""
    entry = make_loaded_entry()
    entry.state = ConfigEntryState.NOT_LOADED
    flow = make_flow(entry)
    with patch("custom_components.diagral.repairs.register_webhook") as register:
        result = await flow.async_step_confirm({})

    register.assert_not_called()
    assert result["type"] == "abort"
    assert result["reason"] == "entry_not_loaded"


async def test_confirm_aborts_when_take_over_fails():
    """A refused registration ends the flow with a reason, not a traceback."""
    flow = make_flow(make_loaded_entry())
    with patch(
        "custom_components.diagral.repairs.register_webhook",
        AsyncMock(side_effect=WebhookUnavailable("webhook_registration_failed")),
    ):
        result = await flow.async_step_confirm({})

    assert result["type"] == "abort"
    assert result["reason"] == "take_over_failed"


def make_retry_flow(entry: MagicMock | None) -> RetryWebhookFlow:
    """Return the retry flow bound to a hass whose registry holds the entry."""
    flow = RetryWebhookFlow("entry1")
    flow.hass = MagicMock()
    flow.hass.config_entries.async_get_entry.return_value = entry
    flow.handler = "diagral"
    flow.issue_id = "webhook_registration_failed_entry1"
    flow.flow_id = "flow"
    return flow


async def test_registration_failure_gets_the_retry_flow():
    """The registration-failure issue is fixed by retrying, not taking over."""
    flow = await async_create_fix_flow(
        MagicMock(), "webhook_registration_failed_entry1", {"entry_id": "entry1"}
    )
    assert isinstance(flow, RetryWebhookFlow)


async def test_retry_registers_without_taking_over():
    """Retrying registers the webhook, still leaving a foreign one alone."""
    entry = make_loaded_entry()
    register = AsyncMock(return_value="NEWID")
    with patch("custom_components.diagral.repairs.register_webhook", register):
        result = await make_retry_flow(entry).async_step_confirm({})

    assert result["type"] == "create_entry"
    assert register.call_args.kwargs.get("take_over", False) is False
    assert entry.runtime_data.webhook_id == "NEWID"
    entry.runtime_data.coordinator.async_set_webhook_status.assert_called_with(
        "connected"
    )


async def test_retry_aborts_when_it_fails_again():
    """A retry that fails again keeps the issue and says so."""
    register = AsyncMock(side_effect=WebhookUnavailable("webhook_registration_failed"))
    with patch("custom_components.diagral.repairs.register_webhook", register):
        result = await make_retry_flow(make_loaded_entry()).async_step_confirm({})

    assert result["type"] == "abort"
    assert result["reason"] == "retry_failed"


def registry_with(issue: MagicMock):
    """Patch the issue registry so it returns the given issue."""
    return patch(
        "custom_components.diagral.repairs.ir.async_get",
        return_value=MagicMock(async_get_issue=MagicMock(return_value=issue)),
    )


@pytest.mark.parametrize(
    ("dismissed_version", "second_option"),
    [(None, "ignore"), ("2026.11.0", "unignore")],
    ids=["shown", "ignored"],
)
async def test_take_over_flow_offers_to_ignore_or_unignore(
    dismissed_version, second_option
):
    """The second choice ignores a shown issue, or shows an ignored one again."""
    flow = make_flow(make_loaded_entry())
    issue = MagicMock(dismissed_version=dismissed_version, translation_placeholders={})

    with registry_with(issue):
        result = await flow.async_step_init({"issue_id": flow.issue_id})

    assert result["type"] == "menu"
    assert result["menu_options"] == ["confirm", second_option]


async def test_unignoring_shows_the_issue_again_without_taking_over():
    """Showing an ignored issue again leaves the subscription where it is."""
    flow = make_flow(make_loaded_entry())
    issue = MagicMock(translation_placeholders={"other_host": "prod.example.net"})
    with (
        patch("custom_components.diagral.repairs.ir.async_ignore_issue") as ignore,
        registry_with(issue),
        patch("custom_components.diagral.repairs.register_webhook") as register,
    ):
        result = await flow.async_step_unignore()

    ignore.assert_called_once_with(
        flow.hass, "diagral", "webhook_owned_elsewhere_entry1", False
    )
    register.assert_not_called()
    assert result["type"] == "abort"
    assert result["reason"] == "unignored"
    assert result["description_placeholders"] == {"other_host": "prod.example.net"}


async def test_ignoring_hides_the_issue_without_taking_over():
    """Ignoring keeps the other installation's subscription and hides the issue."""
    flow = make_flow(make_loaded_entry())
    issue = MagicMock(translation_placeholders={"other_host": "prod.example.net"})
    with (
        patch("custom_components.diagral.repairs.ir.async_ignore_issue") as ignore,
        patch(
            "custom_components.diagral.repairs.ir.async_get",
            return_value=MagicMock(async_get_issue=MagicMock(return_value=issue)),
        ),
        patch("custom_components.diagral.repairs.register_webhook") as register,
    ):
        result = await flow.async_step_ignore()

    ignore.assert_called_once_with(
        flow.hass, "diagral", "webhook_owned_elsewhere_entry1", True
    )
    register.assert_not_called()
    # An abort leaves the issue in place, ignored; finishing would delete it
    assert result["type"] == "abort"
    assert result["reason"] == "ignored"
    # The message names the installation that keeps the events
    assert result["description_placeholders"] == {"other_host": "prod.example.net"}


async def test_retry_flow_still_asks_for_confirmation_only():
    """A failed registration has nothing to ignore: retrying stays one step."""
    flow = make_retry_flow(make_loaded_entry())

    result = await flow.async_step_init({"issue_id": flow.issue_id})

    assert result["type"] == "form"
    assert result["step_id"] == "confirm"
