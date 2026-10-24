"""Repairs for the Diagral integration."""

from __future__ import annotations

from homeassistant.components.repairs import (
    ConfirmRepairFlow,
    RepairsFlow,
    RepairsFlowResult,
)
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant

from . import WebhookUnavailable, register_webhook
from .const import ISSUE_WEBHOOK_REGISTRATION_FAILED


class TakeOverWebhookFlow(ConfirmRepairFlow):
    """Point the central's webhook subscription back to this installation."""

    take_over = True
    failed_reason = "take_over_failed"

    def __init__(self, entry_id: str) -> None:
        """Initialize the flow for one config entry."""
        super().__init__()
        self._entry_id = entry_id

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
        return self.async_create_entry(data={})


class RetryWebhookFlow(TakeOverWebhookFlow):
    """Retry a webhook registration that failed, still sparing a foreign one."""

    take_over = False
    failed_reason = "retry_failed"


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
