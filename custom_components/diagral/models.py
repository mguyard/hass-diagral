"""The Diagral integration models."""

from __future__ import annotations

from dataclasses import dataclass

from pydiagral import DiagralAPI

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME

from .const import (
    CONF_ALARMPANEL_CODE,
    CONF_API_KEY,
    CONF_PIN_CODE,
    CONF_SECRET_KEY,
    CONF_SERIAL_ID,
)
from .coordinator import DiagralDataUpdateCoordinator


@dataclass
class DiagralData:
    """DiagralData is a TypedDict that defines the data stored for Diagral integration."""

    config: DiagralConfigData
    coordinator: DiagralDataUpdateCoordinator
    api: DiagralAPI
    webhook_id: str


@dataclass
class DiagralConfigData:
    """DiagralConfigData is a TypedDict that defines the configuration data required for Diagral integration.

    Attributes:
        username (str): The username for the Diagral account.
        password (str): The password for the Diagral account.
        serial_id (str): The serial ID of the Diagral device.
        pin_code (str): The PIN code for the Diagral device.
        api_key (str): The API key for the Diagral account.
        secret_key (str): The secret key for the Diagral account.
        alarmpanel_code (int): The alarm panel code for the Diagral device.

    """

    username: str
    password: str
    serial_id: str
    pin_code: str
    api_key: str
    secret_key: str
    alarmpanel_code: int

    @classmethod
    def from_config_entry(cls, entry: ConfigEntry) -> DiagralConfigData:
        """Create instance from configuration entry."""
        return cls(
            serial_id=entry.data[CONF_SERIAL_ID],
            username=entry.options.get(CONF_USERNAME, entry.data.get(CONF_USERNAME)),
            password=entry.options.get(CONF_PASSWORD, entry.data.get(CONF_PASSWORD)),
            pin_code=entry.options.get(CONF_PIN_CODE, entry.data.get(CONF_PIN_CODE)),
            api_key=entry.options.get(CONF_API_KEY, entry.data.get(CONF_API_KEY)),
            secret_key=entry.options.get(
                CONF_SECRET_KEY, entry.data.get(CONF_SECRET_KEY)
            ),
            alarmpanel_code=entry.options.get(CONF_ALARMPANEL_CODE),
        )
