"""Module to define the configuration flow for the Diagral integration in Home Assistant."""

from __future__ import annotations

import logging
import re
from typing import Any, cast

from pydiagral.api import DiagralAPI
from pydiagral.exceptions import (
    AuthenticationError,
    ClientError,
    ConfigurationError,
    SessionError,
    ValidationError,
)
from pydiagral.models import AlarmConfiguration, ApiKeyWithSecret
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError

from . import DiagralConfigEntry
from .const import CONF_API_KEY, CONF_PIN_CODE, CONF_SECRET_KEY, CONF_SERIAL_ID, DOMAIN

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
        vol.Required(CONF_SERIAL_ID): str,
        vol.Required(CONF_PIN_CODE, default=1234): vol.Coerce(int),
    }
)


def is_valid_email(email: str) -> bool:
    """Check if the email is valid."""
    pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    return re.match(pattern, email) is not None


def is_valid_pin(pin: int) -> bool:
    """Check if the PIN is valid (positive integer)."""
    return isinstance(pin, int) and pin >= 0


async def validate_input(hass: HomeAssistant, data: dict[str, str]) -> dict[str, str]:
    """Validate the user input allows us to connect."""
    _LOGGER.debug("Starting validation of input: %s", data)
    try:
        _LOGGER.debug("Initializing DiagralAPI")
        # Define the base parameters to initialize the DiagralAPI
        diagral_api_params = {
            "username": data[CONF_USERNAME],
            "password": data[CONF_PASSWORD],
            "serial_id": data[CONF_SERIAL_ID],
            "pincode": data[CONF_PIN_CODE],
        }
        # If the API key and secret key are already set, we use them
        if CONF_API_KEY in data:
            diagral_api_params["apikey"] = data[CONF_API_KEY]
        if CONF_SECRET_KEY in data:
            diagral_api_params["secret_key"] = data[CONF_SECRET_KEY]
        # Initialize the DiagralAPI
        async with DiagralAPI(**diagral_api_params) as diagral:
            _LOGGER.debug("Attempting to login")
            await diagral.login()
            if CONF_API_KEY not in data or CONF_SECRET_KEY not in data:
                _LOGGER.debug("Login successful, attempting to set API key")
                api_keys: ApiKeyWithSecret = await diagral.set_apikey()
                # If we get here, the authentication was successful
                _LOGGER.info("Authentication and API key generation successful")
            else:
                _LOGGER.debug("Login successful, using existing API key")
                api_keys = ApiKeyWithSecret(
                    api_key=data[CONF_API_KEY], secret_key=data[CONF_SECRET_KEY]
                )
            alarm_config: AlarmConfiguration = await diagral.get_configuration()

            return {
                "title": f"{alarm_config.alarm.name} ({data[CONF_SERIAL_ID]})",
                CONF_API_KEY: api_keys.api_key,
                CONF_SECRET_KEY: api_keys.secret_key,
            }
    except (
        ConfigurationError,
        AuthenticationError,
        ValidationError,
        ClientError,
        SessionError,
    ) as error:
        _LOGGER.error("Error during validation: %s", str(error))
        raise CannotConnect from error
    except Exception:
        _LOGGER.exception("Unexpected error during validation")
        raise


class DiagralConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Diagral."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            if not is_valid_email(user_input[CONF_USERNAME]):
                errors[CONF_USERNAME] = "invalid_email"
            if not is_valid_pin(user_input[CONF_PIN_CODE]):
                errors[CONF_PIN_CODE] = "invalid_pin"

            if not errors:
                try:
                    info = await validate_input(self.hass, user_input)
                except CannotConnect:
                    errors["base"] = "cannot_connect"
                except InvalidAuth:
                    errors["base"] = "invalid_auth"
                except Exception:
                    _LOGGER.exception("Unexpected exception")
                    errors["base"] = "unknown"
                else:
                    await self.async_set_unique_id(user_input[CONF_SERIAL_ID])
                    self._abort_if_unique_id_configured()
                    return self.async_create_entry(
                        title=info["title"],
                        data={
                            CONF_USERNAME: user_input[CONF_USERNAME],
                            CONF_PASSWORD: user_input[CONF_PASSWORD],
                            CONF_SERIAL_ID: user_input[CONF_SERIAL_ID],
                            CONF_PIN_CODE: user_input[CONF_PIN_CODE],
                            CONF_API_KEY: info["api_key"],
                            CONF_SECRET_KEY: info["secret_key"],
                        },
                    )

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: DiagralConfigEntry) -> DiagralOptionsFlow:
        """Create and return an instance of DiagralOptionsFlow for the given config entry."""
        return DiagralOptionsFlow(config_entry)


class DiagralOptionsFlow(config_entries.OptionsFlow):
    """Handle a config flow for Diagral options."""

    def __init__(self, config_entry: DiagralConfigEntry) -> None:
        """Initialize the options flow."""
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        errors = {}
        if user_input is not None:
            if not is_valid_email(user_input[CONF_USERNAME]):
                errors[CONF_USERNAME] = "invalid_email"
            if not is_valid_pin(user_input[CONF_PIN_CODE]):
                errors[CONF_PIN_CODE] = "invalid_pin"

            if not errors:
                # Validate the new configuration
                try:
                    # Create a temporary configuration with the new values
                    temp_config = {**self._config_entry.data, **user_input}
                    # Attempt to validate the new configuration
                    await validate_input(self.hass, temp_config)
                except CannotConnect:
                    errors["base"] = "cannot_connect"
                except InvalidAuth:
                    errors["base"] = "invalid_auth"
                except Exception:
                    _LOGGER.exception("Unexpected exception")
                    errors["base"] = "unknown"
                else:
                    # If validation succeeds, update the configuration
                    self.hass.config_entries.async_update_entry(
                        self._config_entry, data=temp_config
                    )
                    return self.async_create_entry(title="", data=user_input)

        return cast(
            ConfigFlowResult,
            self.async_show_form(
                step_id="init",
                data_schema=vol.Schema(
                    {
                        vol.Required(
                            CONF_USERNAME,
                            default=self._config_entry.data.get(CONF_USERNAME),
                        ): str,
                        vol.Required(
                            CONF_PASSWORD,
                            default=self._config_entry.data.get(CONF_PASSWORD),
                        ): str,
                        vol.Required(
                            CONF_PIN_CODE,
                            default=self._config_entry.data.get(CONF_PIN_CODE, 1234),
                        ): vol.Coerce(int),
                    }
                ),
                errors=errors,
                description_placeholders={
                    "username": self._config_entry.data.get(CONF_USERNAME, ""),
                    "serial_id": self._config_entry.data.get(CONF_SERIAL_ID, ""),
                },
            ),
        )


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth."""
