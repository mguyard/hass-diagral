"""Module to define the configuration flow for the Diagral integration in Home Assistant."""

from __future__ import annotations

from copy import deepcopy
import logging
import re
from typing import Any

from pydiagral import DiagralAPIError
from pydiagral.api import DiagralAPI
from pydiagral.exceptions import (
    AuthenticationError,
    ClientError,
    ConfigurationError,
    SessionError,
    ValidationError,
)
from pydiagral.models import TryConnectResult
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError

from . import DiagralConfigEntry
from .const import (
    CONF_ALARMPANEL_CODE,
    CONF_API_KEY,
    CONF_PIN_CODE,
    CONF_SECRET_KEY,
    CONF_SERIAL_ID,
    DOMAIN,
)
from .models import ValidateConnectionData

_LOGGER = logging.getLogger(__name__)


def is_valid_email(email: str) -> bool:
    """Check if the email is valid."""
    pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    return re.match(pattern, email) is not None


def is_valid_pin(pin: int) -> bool:
    """Check if the PIN is valid (positive integer)."""
    return isinstance(pin, int) and pin >= 0


async def validate_input(
    hass: HomeAssistant, data: dict[str, str]
) -> ValidateConnectionData:
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
            connection: TryConnectResult = await diagral.try_connection(ephemeral=False)
            alarm_name: str = await diagral.get_alarm_name()
            return ValidateConnectionData(
                title=f"{alarm_name} ({data[CONF_SERIAL_ID]})", keys=connection.keys
            )
    except (
        ConfigurationError,
        AuthenticationError,
        ValidationError,
        ClientError,
        SessionError,
        DiagralAPIError,
    ) as error:
        _LOGGER.error("Error during validation: %s", str(error))
        raise CannotConnect from error
    except Exception:
        _LOGGER.exception("Unexpected error during validation")
        raise


class DiagralConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Diagral."""

    VERSION = 1
    MINOR_VERSION = 1

    def __init__(self):
        """Initialize the config flow."""
        _LOGGER.debug("Initializing DiagralConfigFlow")
        self.serialid: str | None = None
        self.title: str | None = None
        self.account_username: str | None = None
        self.account_password: str | None = None
        self.account_pincode: int | None = None
        self.apikey: str | None = None
        self.secretkey: str | None = None

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: DiagralConfigEntry) -> DiagralOptionsFlow:
        """Create and return an instance of DiagralOptionsFlow for the given config entry."""
        return DiagralOptionsFlow(config_entry)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self.serialid = user_input[CONF_SERIAL_ID]
            return await self.async_step_account()

        # Build form
        STEP_SERIALID = vol.Schema(
            {
                vol.Required(CONF_SERIAL_ID): str,
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_SERIALID,
            errors=errors or {},
            last_step=False,
        )

    async def async_step_account(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the account step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            _LOGGER.debug("Validating input: %s", user_input)
            # Check if the user has entered a valid email and pin code
            if not is_valid_email(user_input[CONF_USERNAME]):
                errors[CONF_USERNAME] = "invalid_email"
            if not is_valid_pin(user_input[CONF_PIN_CODE]):
                errors[CONF_PIN_CODE] = "invalid_pin"

            if not errors:
                try:
                    user_input[CONF_SERIAL_ID] = self.serialid
                    _LOGGER.debug(
                        "Account validation in progress with Diagral Cloud..."
                    )
                    info: ValidateConnectionData = await validate_input(
                        self.hass, user_input
                    )
                    _LOGGER.debug("Account validation successful")
                    self.title = info.title
                    self.account_username = user_input[CONF_USERNAME]
                    self.account_password = user_input[CONF_PASSWORD]
                    self.account_pincode = user_input[CONF_PIN_CODE]
                    self.apikey = info.keys.api_key
                    self.secretkey = info.keys.secret_key
                    return await self.async_step_options()
                except CannotConnect as error:
                    if error.__cause__ is not None:
                        errors["base"] = str(error.__cause__)
                    else:
                        errors["base"] = "cannot_connect"
                except InvalidAuth as error:
                    if error.__cause__ is not None:
                        errors["base"] = str(error.__cause__)
                    else:
                        errors["base"] = "invalid_auth"
                except Exception as error:
                    _LOGGER.exception("Unexpected exception")
                    if error.__cause__ is not None:
                        errors["base"] = str(error.__cause__)
                    else:
                        errors["base"] = "unknown"

        # Build form
        STEP_ACCOUNT = vol.Schema(
            {
                vol.Required(CONF_USERNAME): str,
                vol.Required(CONF_PASSWORD): str,
                vol.Required(CONF_PIN_CODE, default=None): vol.Coerce(int),
            }
        )

        return self.async_show_form(
            step_id="account",
            data_schema=STEP_ACCOUNT,
            errors=errors or {},
            last_step=False,
        )

    async def async_step_options(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the alarm panel step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # Check if the user has entered a valid alarm panel code
            if user_input[CONF_ALARMPANEL_CODE] is not None and not is_valid_pin(
                user_input[CONF_ALARMPANEL_CODE]
            ):
                errors[CONF_ALARMPANEL_CODE] = "invalid_alarmpanel_code"

            _LOGGER.debug("Submitting entry to HA : %s", user_input)
            await self.async_set_unique_id(self.serialid)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title=self.title,
                data={
                    CONF_SERIAL_ID: self.serialid,
                },
                options={
                    CONF_USERNAME: self.account_username,
                    CONF_PASSWORD: self.account_password,
                    CONF_PIN_CODE: self.account_pincode,
                    CONF_API_KEY: self.apikey,
                    CONF_SECRET_KEY: self.secretkey,
                    CONF_ALARMPANEL_CODE: user_input.get(CONF_ALARMPANEL_CODE),
                },
            )

        # Build form
        STEP_OPTIONS = vol.Schema(
            {
                vol.Optional(CONF_ALARMPANEL_CODE, default=None): vol.Any(
                    None, vol.Coerce(int)
                ),
            }
        )

        return self.async_show_form(
            step_id="options",
            data_schema=STEP_OPTIONS,
            errors=errors or {},
            last_step=True,
        )


class DiagralOptionsFlow(config_entries.OptionsFlow):
    """Handle a config flow for Diagral options."""

    def __init__(self, config_entry: DiagralConfigEntry) -> None:
        """Initialize the options flow."""
        _LOGGER.debug("Initializing DiagralOptionsFlow")
        self.options = deepcopy(dict(config_entry.options))
        self.serialid = config_entry.data[CONF_SERIAL_ID]
        self.title = config_entry.title
        self.configuration_changed = False
        self._username_changed = False
        self._password_changed = False
        self._pincode_changed = False
        self._alarmpanel_code_changed = False

    async def async_step_init(self, user_input: None = None) -> ConfigFlowResult:
        """Manage the account options."""
        errors: dict[str, str] = {}

        # Build form
        STEP_ACCOUNT = vol.Schema(
            {
                vol.Required(CONF_USERNAME, default=self.options[CONF_USERNAME]): str,
                vol.Required(CONF_PASSWORD, default=self.options[CONF_PASSWORD]): str,
                vol.Required(
                    CONF_PIN_CODE, default=self.options[CONF_PIN_CODE]
                ): vol.Coerce(int),
            }
        )

        if user_input is not None:
            # Check if the user has changed the username, password or pin code
            # and check if the new values are valid
            if user_input[CONF_USERNAME] is not None and user_input[
                CONF_USERNAME
            ] != self.options.get(CONF_USERNAME):
                if not is_valid_email(user_input[CONF_USERNAME]):
                    errors[CONF_USERNAME] = "invalid_email"
                self._username_changed = True
            if user_input[CONF_PASSWORD] is not None and user_input[
                CONF_PASSWORD
            ] != self.options.get(CONF_PASSWORD):
                self._password_changed = True
            if user_input[CONF_PIN_CODE] is not None and user_input[
                CONF_PIN_CODE
            ] != self.options.get(CONF_PIN_CODE):
                if not is_valid_pin(user_input[CONF_PIN_CODE]):
                    errors[CONF_PIN_CODE] = "invalid_pin"
                self._pincode_changed = True

            if not errors:
                if (
                    self._username_changed
                    or self._password_changed
                    or self._pincode_changed
                ):
                    try:
                        user_input[CONF_SERIAL_ID] = self.serialid
                        _LOGGER.debug(
                            "Account validation in progress with Diagral Cloud..."
                        )
                        info: ValidateConnectionData = await validate_input(
                            self.hass, user_input
                        )
                        _LOGGER.debug("Account validation successful")
                        self.title = info.title
                        self.options[CONF_USERNAME] = user_input[CONF_USERNAME]
                        self.options[CONF_PASSWORD] = user_input[CONF_PASSWORD]
                        self.options[CONF_PIN_CODE] = user_input[CONF_PIN_CODE]
                        self.options[CONF_API_KEY] = info.keys.api_key
                        self.options[CONF_SECRET_KEY] = info.keys.secret_key
                    except CannotConnect as error:
                        if error.__cause__ is not None:
                            errors["base"] = str(error.__cause__)
                        else:
                            errors["base"] = "cannot_connect"
                    except InvalidAuth as error:
                        if error.__cause__ is not None:
                            errors["base"] = str(error.__cause__)
                        else:
                            errors["base"] = "invalid_auth"
                    except Exception as error:
                        _LOGGER.exception("Unexpected exception")
                        if error.__cause__ is not None:
                            errors["base"] = str(error.__cause__)
                        else:
                            errors["base"] = "unknown"

                    if errors:
                        return self.async_show_form(
                            step_id="init",
                            data_schema=STEP_ACCOUNT,
                            errors=errors or {},
                            description_placeholders={"title": self.title},
                            last_step=False,
                        )

                return await self.async_step_options()

        return self.async_show_form(
            step_id="init",
            data_schema=STEP_ACCOUNT,
            errors=errors or {},
            description_placeholders={"title": self.title},
            last_step=False,
        )

    async def async_step_options(self, user_input: None = None) -> ConfigFlowResult:
        """Manage the options."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # Check if the user has changed the alarm panel code
            if (
                user_input[CONF_ALARMPANEL_CODE] is not None
                and user_input[CONF_ALARMPANEL_CODE]
                != self.options[CONF_ALARMPANEL_CODE]
            ):
                # Check if the user has entered a valid alarm panel code
                if not is_valid_pin(user_input[CONF_ALARMPANEL_CODE]):
                    errors[CONF_ALARMPANEL_CODE] = "invalid_alarmpanel_code"
                else:
                    self._alarmpanel_code_changed = True
                    self.options[CONF_ALARMPANEL_CODE] = user_input[
                        CONF_ALARMPANEL_CODE
                    ]

            if (
                self._username_changed
                or self._password_changed
                or self._pincode_changed
                or self._alarmpanel_code_changed
            ):
                _LOGGER.debug(
                    "Submitting data entry to HA : %s", self.config_entry.data
                )
                _LOGGER.debug("Submitting options entry to HA : %s", self.options)
                # self.hass.config_entries.async_update_entry(
                #     entry=self.config_entry,
                #     title=self.title,
                #     data=self.config_entry.data,
                #     options=self.options,
                # )
                # _LOGGER.warning("Updated entry: %s", result)
                # _LOGGER.warning(
                #     "Reloading config entry: %s", self._config_entry.entry_id
                # )
                # await self.hass.config_entries.async_reload(self._config_entry.entry_id)
                return self.async_create_entry(title="", data=self.options)

            _LOGGER.debug("No configuration changes detected, skipping update.")
            return self.async_abort(reason="no_changes")

        # Build form
        STEP_OPTIONS = vol.Schema(
            {
                vol.Optional(
                    CONF_ALARMPANEL_CODE,
                    default=self.options[CONF_ALARMPANEL_CODE],
                ): vol.Any(None, vol.Coerce(int)),
            }
        )

        return self.async_show_form(
            step_id="options",
            data_schema=STEP_OPTIONS,
            errors=errors or {},
            last_step=True,
        )


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth."""
