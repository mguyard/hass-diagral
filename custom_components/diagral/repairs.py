"""Repairs for the Diagral integration."""

from __future__ import annotations

from pydiagral.exceptions import DiagralAPIError

from homeassistant.components.repairs import (
    ConfirmRepairFlow,
    RepairsFlow,
    RepairsFlowResult,
)
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant

from . import register_webhook


class TakeOverWebhookFlow(ConfirmRepairFlow):
    """Point the central's webhook subscription back to this installation."""

    def __init__(self, entry_id: str) -> None:
        """Initialize the flow for one config entry."""
        super().__init__()
        self._entry_id = entry_id

    async def async_step_confirm(
        self, user_input: dict[str, str] | None = None
    ) -> RepairsFlowResult:
        """Take over the subscription once the user confirms."""
        if user_input is None:
            return await super().async_step_confirm()

        entry = self.hass.config_entries.async_get_entry(self._entry_id)
        if entry is None or entry.state is not ConfigEntryState.LOADED:
            return self.async_abort(reason="entry_not_loaded")
        try:
            webhook_id = await register_webhook(
                self.hass, entry, entry.runtime_data.api, "Repair", take_over=True
            )
        except DiagralAPIError:
            return self.async_abort(reason="take_over_failed")
        if webhook_id is None:
            return self.async_abort(reason="take_over_failed")
        entry.runtime_data.webhook_id = webhook_id
        return self.async_create_entry(data={})


async def async_create_fix_flow(
    hass: HomeAssistant,
    issue_id: str,
    data: dict[str, str | int | float | None] | None,
) -> RepairsFlow:
    """Create the fix flow for a webhook owned by another installation."""
    assert data is not None
    return TakeOverWebhookFlow(str(data["entry_id"]))
