"""The Diagral integration models."""

from __future__ import annotations

from dataclasses import dataclass

from pydiagral import DiagralAPI
from pydiagral.models import ApiKeyWithSecret

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME

from .const import CONF_API_KEY, CONF_PIN_CODE, CONF_SECRET_KEY, CONF_SERIAL_ID
from .coordinator import DiagralDataUpdateCoordinator


@dataclass
class DiagralData:
    """DiagralData is a TypedDict that defines the data stored for Diagral integration."""

    config: DiagralConfigData
    coordinator: DiagralDataUpdateCoordinator
    api: DiagralAPI
    webhook_id: str


@dataclass
class DiagralOptionsAlarmPanelData:
    """DiagralOptionsAlarmPanelData is a TypedDict that defines the options data for the alarm panel."""

    alarmpanel_actiontype_code: str
    alarmpanel_code: int | None = None


@dataclass
class DiagralOptionsData:
    """DiagralOptionsData is a TypedDict that defines the options data for Diagral integration."""

    alarmpanel_options: DiagralOptionsAlarmPanelData


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
        options (DiagralOptionsData): The options for the Diagral integration.

    """

    username: str
    password: str
    serial_id: str
    pin_code: str
    api_key: str
    secret_key: str
    options: DiagralOptionsData

    @classmethod
    def from_config_entry(cls, entry: ConfigEntry) -> DiagralConfigData:
        """Create instance from configuration entry."""
        return cls(
            serial_id=entry.data[CONF_SERIAL_ID],
            username=entry.data.get(CONF_USERNAME),
            password=entry.data.get(CONF_PASSWORD),
            pin_code=entry.data.get(CONF_PIN_CODE),
            api_key=entry.data.get(CONF_API_KEY),
            secret_key=entry.data.get(CONF_SECRET_KEY),
            options=DiagralOptionsData(**entry.options),
        )


@dataclass
class AccountInfoData:
    """A class to store account information for Diagral API.

    This class provides structure for account information including a username, password, serial ID, and PIN code.

    Attributes:
        username (str): The username for the Diagral account.
        password (str): The password for the Diagral account.
        serial_id (str): The serial ID of the Diagral device.
        pin_code (str): The PIN code for the Diagral device.
        api_key (str): The API key for the Diagral account.
        secret_key (str): The secret key for the Diagral account.

    """

    username: str
    password: str
    serial_id: str
    pin_code: str
    api_key: str | None = None
    secret_key: str | None = None


@dataclass
class ValidateConnectionData:
    """A class to validate connection parameters for Diagral API.

    This class provides structure for connection validation credentials including a title and API keys.

    Attributes:
        title (str): A descriptive name or title for the connection.
        keys (ApiKeyWithSecret): API key credentials containing access key and secret.

    """

    title: str
    keys: ApiKeyWithSecret
