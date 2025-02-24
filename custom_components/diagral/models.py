"""The Diagral integration models."""

from __future__ import annotations

from dataclasses import dataclass

from pydiagral import DiagralAPI

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

    """

    username: str
    password: str
    serial_id: str
    pin_code: str
    api_key: str
    secret_key: str
