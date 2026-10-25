"""Repairs for the Diagral integration."""

from __future__ import annotations

from homeassistant.components.repairs import (
    ConfirmRepairFlow,
    RepairsFlow,
    RepairsFlowResult,
)
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir

from . import WebhookUnavailable, register_webhook
from .const import DOMAIN, ISSUE_WEBHOOK_REGISTRATION_FAILED, WEBHOOK_CONNECTED


class TakeOverWebhookFlow(ConfirmRepairFlow):
    """Point the central's webhook subscription back to this installation."""

    take_over = True
    failed_reason = "take_over_failed"

    def __init__(self, entry_id: str) -> None:
        """Initialize the flow for one config entry."""
        super().__init__()
        self._entry_id = entry_id

    async def async_step_init(
        self, user_input: dict[str, str] | None = None
    ) -> RepairsFlowResult:
        """Offer to take the webhook over, or to leave it to the other installation."""
        issue = ir.async_get(self.hass).async_get_issue(DOMAIN, self.issue_id)
        # Opened from the ignored repairs, the second choice shows it again
        ignored = issue is not None and issue.dismissed_version is not None
        return self.async_show_menu(
            step_id="init",
            menu_options=["confirm", "unignore" if ignored else "ignore"],
            description_placeholders=self._placeholders(),
        )

    async def async_step_ignore(
        self, user_input: dict[str, str] | None = None
    ) -> RepairsFlowResult:
        """Hide the issue; the hourly check recreating it keeps it hidden."""
        placeholders = self._placeholders()
        ir.async_ignore_issue(self.hass, DOMAIN, self.issue_id, True)
        # An abort keeps the issue: finishing the flow would delete it
        return self.async_abort(reason="ignored", description_placeholders=placeholders)

    async def async_step_unignore(
        self, user_input: dict[str, str] | None = None
    ) -> RepairsFlowResult:
        """Show an ignored issue in the repairs again."""
        placeholders = self._placeholders()
        ir.async_ignore_issue(self.hass, DOMAIN, self.issue_id, False)
        return self.async_abort(
            reason="unignored", description_placeholders=placeholders
        )

    def _placeholders(self) -> dict[str, str] | None:
        """Return the entry title and other host the issue was raised with."""
        issue = ir.async_get(self.hass).async_get_issue(DOMAIN, self.issue_id)
        return issue.translation_placeholders if issue else None

    async def async_step_confirm(
        self, user_input: dict[str, str] | None = None
    ) -> RepairsFlowResult:
        """Register the webhook once the user confirms."""
        if user_input is None:
            return await super().async_step_confirm()

        entry = self.hass.config_entries.async_get_entry(self._entry_id)
        if entry is None or entry.state is not ConfigEntryState.LOADED:
            return self.async_abort(reason="entry_not_loaded")
        try:
            webhook_id = await register_webhook(
                self.hass,
                entry,
                entry.runtime_data.api,
                "Repair",
                take_over=self.take_over,
            )
        except WebhookUnavailable:
            return self.async_abort(reason=self.failed_reason)
        if webhook_id is None:
            return self.async_abort(reason=self.failed_reason)
        entry.runtime_data.webhook_id = webhook_id
        entry.runtime_data.coordinator.async_set_webhook_status(WEBHOOK_CONNECTED)
        return self.async_create_entry(data={})


class RetryWebhookFlow(TakeOverWebhookFlow):
    """Retry a webhook registration that failed, still sparing a foreign one."""

    take_over = False
    failed_reason = "retry_failed"

    async def async_step_init(
        self, user_input: dict[str, str] | None = None
    ) -> RepairsFlowResult:
        """Retrying spares any foreign subscription: nothing to choose."""
        return await self.async_step_confirm()


async def async_create_fix_flow(
    hass: HomeAssistant,
    issue_id: str,
    data: dict[str, str | int | float | None] | None,
) -> RepairsFlow:
    """Create the fix flow of a webhook repair issue."""
    assert data is not None
    if issue_id.startswith(ISSUE_WEBHOOK_REGISTRATION_FAILED):
        return RetryWebhookFlow(str(data["entry_id"]))
    return TakeOverWebhookFlow(str(data["entry_id"]))
