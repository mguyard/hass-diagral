"""Module to define the configuration flow for the Diagral integration in Home Assistant."""

from __future__ import annotations

from collections.abc import Mapping
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
from homeassistant.data_entry_flow import section
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from . import DiagralConfigEntry
from .const import (
    ALARMPANEL_CODE_MIN_LENGTH,
    BRAND,
    CONF_ALARMPANEL_ACTIONTYPE_CODE,
    CONF_ALARMPANEL_ACTIONTYPE_CODE_OPTIONS,
    CONF_ALARMPANEL_CODE,
    CONF_API_KEY,
    CONF_PIN_CODE,
    CONF_SECRET_KEY,
    CONF_SERIAL_ID,
    CONFIG_MINOR_VERSION,
    CONFIG_VERSION,
    DIAGRAL_VENDOR,
    DOMAIN,
    SERIAL_GUIDE_URL,
    SERIAL_IMAGE_URL,
)
from .models import AccountInfoData, DiagralOptionsData, ValidateConnectionData

_LOGGER = logging.getLogger(__name__)

SECRET_SELECTOR = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))


def is_valid_email(email: str) -> bool:
    """Check if the email is valid."""
    pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    return re.match(pattern, email) is not None


def is_valid_pin(pin: str) -> bool:
    """Check if the pin code is valid.

    The pin code must be a string of digits and must be greater than or equal to 0.
    """
    return isinstance(pin, str) and pin.isdigit() and int(pin) >= 0


def is_valid_alarmpanel_code(code: int) -> bool:
    """Check if the alarm panel code is valid."""
    return isinstance(code, int) and len(str(code)) >= ALARMPANEL_CODE_MIN_LENGTH


async def validate_account(
    hass: HomeAssistant,
    account_info: AccountInfoData,
    previous_data: Mapping[str, Any] | None = None,
    ephemeral: bool = True,
) -> ValidateConnectionData | None:
    """Validate the user input allows us to connect to Diagral API."""
    previous_data = previous_data or {}

    # Need to identify if submitted informations was modified
    username_changed = account_info.username != previous_data.get(CONF_USERNAME, None)
    password_changed = account_info.password != previous_data.get(CONF_PASSWORD, None)
    pincode_changed = account_info.pin_code != previous_data.get(CONF_PIN_CODE, None)
    account_info_changed = username_changed or password_changed or pincode_changed

    if account_info_changed:
        # Set the parameters for the Diagral API without API key and secret key
        # (also if they exist in configuration)
        diagral_api_params = {
            "username": account_info.username,
            "password": account_info.password,
            "serial_id": account_info.serial_id,
            "pincode": account_info.pin_code,
            "session": async_get_clientsession(hass),
            "vendor": DIAGRAL_VENDOR,
        }

        # With ephemeral mode, we create API key, test the connection and remove them
        # Without ephemeral mode, we create API key and return alarm name and
        #    API key and secret key

        try:
            async with DiagralAPI(**diagral_api_params) as diagral:
                _LOGGER.debug("Attempting to test connection with Diagral Cloud...")
                connection: TryConnectResult = await diagral.try_connection(
                    ephemeral=ephemeral
                )
                _LOGGER.debug("Connection successful")

                # If ephemeral mode is disabled, we get the alarm name
                # else, we set the alarm name to None (as keys are removed)
                if not ephemeral:
                    alarm_name = await diagral.get_alarm_name() or BRAND
                else:
                    alarm_name = None

                return ValidateConnectionData(
                    title=f"{alarm_name} ({account_info.serial_id})",
                    keys=connection.keys,
                )
        except AuthenticationError as error:
            _LOGGER.error("Error during validation: %s", str(error))
            raise InvalidAuth from error
        except (
            ConfigurationError,
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
    else:
        _LOGGER.debug("No account information has changed, skipping validation")
        return None


async def list_serials(hass: HomeAssistant, username: str, password: str) -> list[str]:
    """Return the serials of the account's centrals; asking needs no serial."""
    try:
        async with DiagralAPI(
            username=username,
            password=password,
            session=async_get_clientsession(hass),
            vendor=DIAGRAL_VENDOR,
        ) as diagral:
            systems = await diagral.get_systems()
    except AuthenticationError as error:
        raise InvalidAuth from error
    except DiagralAPIError as error:
        _LOGGER.warning(
            "Could not list the Diagral centrals of the account (%s)",
            type(error).__name__,
        )
        raise CannotConnect from error
    _LOGGER.debug("The Diagral account has %d centrals", len(systems))
    return [system.serial_id for system in systems]


class DiagralConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Diagral."""

    VERSION = CONFIG_VERSION
    MINOR_VERSION = CONFIG_MINOR_VERSION

    def __init__(self):
        """Initialize the config flow."""
        _LOGGER.debug("Initializing DiagralConfigFlow")
        self.serialid: str | None = None
        self.serials: list[str] = []
        self.title: str | None = None
        self.account_username: str | None = None
        self.account_password: str | None = None
        self.account_pincode: str | None = None
        self.apikey: str | None = None
        self.secretkey: str | None = None

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: DiagralConfigEntry) -> DiagralOptionsFlow:
        """Create and return an instance of DiagralOptionsFlow for the given config entry."""
        return DiagralOptionsFlow()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the account first: it lists the centrals to choose from."""
        errors: dict[str, str] = {}

        if user_input is not None:
            _LOGGER.debug("Validating account credentials")
            # Check if the user has entered a valid email and pin code
            if not is_valid_email(user_input[CONF_USERNAME]):
                errors[CONF_USERNAME] = "invalid_email"
            if not is_valid_pin(user_input[CONF_PIN_CODE]):
                errors[CONF_PIN_CODE] = "invalid_pin"

            if not errors:
                self.account_username = user_input[CONF_USERNAME]
                self.account_password = user_input[CONF_PASSWORD]
                self.account_pincode = user_input[CONF_PIN_CODE]
                try:
                    self.serials = await list_serials(
                        self.hass, self.account_username, self.account_password
                    )
                except InvalidAuth:
                    errors["base"] = "invalid_auth"
                except CannotConnect:
                    return await self.async_step_serial()
                except Exception:
                    _LOGGER.exception("Unexpected exception")
                    errors["base"] = "unknown"
                else:
                    if not self.serials:
                        return await self.async_step_serial()
                    return await self.async_step_central()

        # Build form
        account_schema = vol.Schema(
            {
                vol.Required(CONF_USERNAME): str,
                vol.Required(CONF_PASSWORD): SECRET_SELECTOR,
                vol.Required(CONF_PIN_CODE): SECRET_SELECTOR,
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=account_schema,
            errors=errors or {},
            last_step=False,
        )

    async def async_step_central(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Offer the account's centrals that are not in Home Assistant yet."""
        errors: dict[str, str] = {}

        if user_input is not None:
            errors = await self._async_check_central(user_input[CONF_SERIAL_ID])
            if not errors:
                return await self.async_step_options()

        # An entry title is already "Name (Serial)"
        configured = {
            entry.unique_id.upper(): entry.title
            for entry in self._async_current_entries()
            if entry.unique_id
        }
        available = [s for s in self.serials if s.upper() not in configured]
        if not available:
            return self.async_abort(reason="already_configured")

        return self.async_show_form(
            step_id="central",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_SERIAL_ID): SelectSelector(
                        SelectSelectorConfig(
                            options=available, mode=SelectSelectorMode.LIST
                        )
                    ),
                }
            ),
            errors=errors or {},
            description_placeholders={
                "configured": ", ".join(
                    configured[s.upper()]
                    for s in self.serials
                    if s.upper() in configured
                )
                or "-",
                "setup_guide_url": SERIAL_GUIDE_URL,
                "serial_id_image_url": SERIAL_IMAGE_URL,
            },
            last_step=False,
        )

    async def async_step_serial(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the serial when the account's centrals cannot be listed."""
        errors: dict[str, str] = {}

        if user_input is not None:
            errors = await self._async_check_central(user_input[CONF_SERIAL_ID])
            if not errors:
                return await self.async_step_options()

        return self.async_show_form(
            step_id="serial",
            data_schema=vol.Schema({vol.Required(CONF_SERIAL_ID): str}),
            errors=errors or {},
            description_placeholders={
                "setup_guide_url": SERIAL_GUIDE_URL,
                "serial_id_image_url": SERIAL_IMAGE_URL,
            },
            last_step=False,
        )

    async def _async_check_central(self, serial_id: str) -> dict[str, str]:
        """Claim the central, then check the account drives it; return form errors."""
        # A duplicate must stop here, before the options step creates an API key
        await self.async_set_unique_id(serial_id)
        self._abort_if_unique_id_configured()
        try:
            # Ephemeral: the final API key and secret key come with the last step
            await validate_account(
                self.hass,
                account_info=AccountInfoData(
                    username=self.account_username,
                    password=self.account_password,
                    pin_code=self.account_pincode,
                    serial_id=serial_id,
                ),
                ephemeral=True,
            )
        except CannotConnect:
            return {"base": "cannot_connect"}
        except InvalidAuth:
            return {"base": "invalid_auth"}
        except Exception:
            _LOGGER.exception("Unexpected exception")
            return {"base": "unknown"}
        self.serialid = serial_id
        return {}

    async def async_step_options(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the alarm panel step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # Set variables for the alarm panel options
            alarmpaneltypecode = user_input["alarmpanel_options"][
                CONF_ALARMPANEL_ACTIONTYPE_CODE
            ]
            alarmpanelcode = user_input["alarmpanel_options"].get(CONF_ALARMPANEL_CODE)
            if alarmpanelcode is None:
                user_input["alarmpanel_options"][CONF_ALARMPANEL_CODE] = None
            if alarmpanelcode is not None:
                alarmpanelcode = int(alarmpanelcode)
                user_input["alarmpanel_options"][CONF_ALARMPANEL_CODE] = alarmpanelcode

            # Check if the user has entered a valid alarm panel code
            _LOGGER.debug("Validating options (code required: %s)", alarmpaneltypecode)

            # If the user has selected "never" as action type, we set the code to None
            if alarmpaneltypecode == "never" and alarmpanelcode is not None:
                user_input["alarmpanel_options"][CONF_ALARMPANEL_CODE] = None

            # If the user has selected something else than "never" as action type,
            # and don't set a code, we trigger an error
            elif alarmpaneltypecode != "never" and alarmpanelcode is None:
                errors["base"] = "missing_alarmpanel_code"

            # Check if the user has entered a valid alarm panel code
            if alarmpanelcode is not None and not is_valid_alarmpanel_code(
                alarmpanelcode
            ):
                errors["base"] = "invalid_alarmpanel_code"

            if not errors:
                try:
                    # Validate the account credentials
                    # not in ephemeral mode as final keys (API key and secret key)
                    # is requested in this step
                    info: ValidateConnectionData = await validate_account(
                        self.hass,
                        account_info=AccountInfoData(
                            username=self.account_username,
                            password=self.account_password,
                            pin_code=self.account_pincode,
                            serial_id=self.serialid,
                        ),
                        ephemeral=False,
                    )
                    await self.async_set_unique_id(self.serialid)
                    self._abort_if_unique_id_configured()
                    return self.async_create_entry(
                        title=info.title,
                        data={
                            CONF_SERIAL_ID: self.serialid,
                            CONF_USERNAME: self.account_username,
                            CONF_PASSWORD: self.account_password,
                            CONF_PIN_CODE: self.account_pincode,
                            CONF_API_KEY: info.keys.api_key,
                            CONF_SECRET_KEY: info.keys.secret_key,
                        },
                        options=user_input,
                    )
                except CannotConnect:
                    errors["base"] = "cannot_connect"
                except InvalidAuth:
                    errors["base"] = "invalid_auth"
                except Exception:
                    _LOGGER.exception("Unexpected exception")
                    errors["base"] = "unknown"

        # Build form
        options_schema = vol.Schema(
            {
                vol.Required("alarmpanel_options"): section(
                    vol.Schema(
                        {
                            vol.Optional(
                                CONF_ALARMPANEL_ACTIONTYPE_CODE,
                                default="never",
                            ): SelectSelector(
                                SelectSelectorConfig(
                                    translation_key=CONF_ALARMPANEL_ACTIONTYPE_CODE,
                                    options=[
                                        {"value": k, "label": k}
                                        for k in CONF_ALARMPANEL_ACTIONTYPE_CODE_OPTIONS
                                    ],
                                )
                            ),
                            vol.Optional(
                                CONF_ALARMPANEL_CODE, default=vol.UNDEFINED
                            ): vol.Any(
                                None,
                                vol.All(
                                    vol.Coerce(int),
                                    NumberSelector(
                                        NumberSelectorConfig(
                                            mode=NumberSelectorMode.BOX, step=1
                                        )
                                    ),
                                ),
                            ),
                        }
                    ),
                    {"collapsed": False},
                )
            }
        )

        return self.async_show_form(
            step_id="options",
            data_schema=options_schema,
            errors=errors or {},
            description_placeholders={
                "options_url": "https://docs.page/mguyard/hass-diagral/integration/setup#options"
            },
            last_step=True,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle reconfiguration of the integration."""
        _LOGGER.debug("Reconfiguring Diagral integration")
        errors: dict[str, str] = {}

        config_entry = self.hass.config_entries.async_get_entry(
            self.context["entry_id"]
        )
        self.serialid = config_entry.data[CONF_SERIAL_ID]

        if user_input is not None:
            user_input = {
                CONF_USERNAME: user_input[CONF_USERNAME],
                CONF_PASSWORD: user_input.get(CONF_PASSWORD)
                or config_entry.data[CONF_PASSWORD],
                CONF_PIN_CODE: user_input.get(CONF_PIN_CODE)
                or config_entry.data[CONF_PIN_CODE],
            }
            _LOGGER.debug("Validating account credentials")
            # Check if the user has entered a valid email and pin code
            if not is_valid_email(user_input[CONF_USERNAME]):
                errors[CONF_USERNAME] = "invalid_email"
            if not is_valid_pin(user_input[CONF_PIN_CODE]):
                errors[CONF_PIN_CODE] = "invalid_pin"

            if not errors:
                try:
                    info: ValidateConnectionData | None = await validate_account(
                        self.hass,
                        account_info=AccountInfoData(
                            username=user_input[CONF_USERNAME],
                            password=user_input[CONF_PASSWORD],
                            pin_code=user_input[CONF_PIN_CODE],
                            serial_id=self.serialid,
                        ),
                        previous_data=config_entry.data,
                        ephemeral=True,
                    )
                except CannotConnect:
                    errors["base"] = "cannot_connect"
                except InvalidAuth:
                    errors["base"] = "invalid_auth"
                except Exception:
                    _LOGGER.exception("Unexpected exception")
                    errors["base"] = "unknown"
                else:
                    if info is None:
                        return self.async_abort(reason="no_changes")

                    return self.async_update_reload_and_abort(
                        config_entry,
                        unique_id=config_entry.unique_id,
                        data={**config_entry.data, **user_input},
                        reason="reconfigure_successful",
                    )

        # Build form
        reconfigure_schema = vol.Schema(
            {
                vol.Required(
                    CONF_USERNAME, default=config_entry.data[CONF_USERNAME]
                ): str,
                # Never sent back to the browser; left empty, they are kept
                vol.Optional(CONF_PASSWORD): SECRET_SELECTOR,
                vol.Optional(CONF_PIN_CODE): SECRET_SELECTOR,
            }
        )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=reconfigure_schema,
            errors=errors or {},
        )


class DiagralOptionsFlow(config_entries.OptionsFlow):
    """Handle a config flow for Diagral options."""

    async def async_step_init(self, user_input: None = None) -> ConfigFlowResult:
        """Manage the options."""
        _LOGGER.debug("Initializing DiagralOptionsFlow")
        options: DiagralOptionsData = deepcopy(dict(self.config_entry.options))
        errors: dict[str, str] = {}

        if user_input is not None:
            # Check if the user has changed the alarm panel action type
            alarmpaneltypecode = user_input["alarmpanel_options"][
                CONF_ALARMPANEL_ACTIONTYPE_CODE
            ]
            alarmpaneltypecode_updated = (
                alarmpaneltypecode
                != options["alarmpanel_options"][CONF_ALARMPANEL_ACTIONTYPE_CODE]
            )
            # Check if the user has changed the alarm panel code
            alarmpanelcode = user_input["alarmpanel_options"].get(CONF_ALARMPANEL_CODE)
            if alarmpanelcode is None:
                user_input["alarmpanel_options"][CONF_ALARMPANEL_CODE] = None
            if alarmpanelcode is not None:
                alarmpanelcode = int(alarmpanelcode)
                user_input["alarmpanel_options"][CONF_ALARMPANEL_CODE] = alarmpanelcode
            alarmpanelcode_updated = (
                alarmpanelcode is not None
                and alarmpanelcode
                != options["alarmpanel_options"][CONF_ALARMPANEL_CODE]
            )
            # Set a global variable to check if options have been updated
            options_updated = alarmpaneltypecode_updated or alarmpanelcode_updated

            if options_updated:
                if alarmpaneltypecode:
                    # If the user has selected "never" as action type, we set the code to None
                    if alarmpaneltypecode == "never" and alarmpanelcode is not None:
                        user_input["alarmpanel_options"][CONF_ALARMPANEL_CODE] = None
                        alarmpanelcode_updated = False
                    # If the user has selected something else than "never" as action type,
                    # and don't set a code, we trigger an error
                    elif alarmpaneltypecode != "never" and alarmpanelcode is None:
                        errors["base"] = "missing_alarmpanel_code"

                # If the alarm panel code has been updated, we need to validate it
                if alarmpanelcode_updated:
                    # Check if the user has entered a valid alarm panel code
                    if not is_valid_alarmpanel_code(alarmpanelcode):
                        errors["base"] = "invalid_alarmpanel_code"

                    # If alarm panel code is 0, set it to None (to disable usage of code)
                    if alarmpanelcode == 0:
                        user_input["alarmpanel_options"][CONF_ALARMPANEL_CODE] = None

                if not errors:
                    self.hass.config_entries.async_schedule_reload(
                        self.config_entry.entry_id
                    )
                    return self.async_create_entry(title="", data=user_input)
            else:
                _LOGGER.debug("No configuration changes detected, skipping update.")
                return self.async_abort(reason="no_changes")

        # Build form
        stored_code = options["alarmpanel_options"][CONF_ALARMPANEL_CODE]
        code_default = stored_code if stored_code is not None else vol.UNDEFINED
        options_schema = vol.Schema(
            {
                vol.Required("alarmpanel_options"): section(
                    vol.Schema(
                        {
                            vol.Optional(
                                CONF_ALARMPANEL_ACTIONTYPE_CODE,
                                default=options["alarmpanel_options"][
                                    CONF_ALARMPANEL_ACTIONTYPE_CODE
                                ],
                            ): SelectSelector(
                                SelectSelectorConfig(
                                    translation_key=CONF_ALARMPANEL_ACTIONTYPE_CODE,
                                    options=[
                                        {"value": k, "label": k}
                                        for k in CONF_ALARMPANEL_ACTIONTYPE_CODE_OPTIONS
                                    ],
                                )
                            ),
                            vol.Optional(
                                CONF_ALARMPANEL_CODE,
                                default=code_default,
                            ): vol.Any(
                                None,
                                vol.All(
                                    vol.Coerce(int),
                                    NumberSelector(
                                        NumberSelectorConfig(
                                            mode=NumberSelectorMode.BOX, step=1
                                        )
                                    ),
                                ),
                            ),
                        }
                    ),
                    {"collapsed": True},
                )
            }
        )

        return self.async_show_form(
            step_id="init",
            data_schema=options_schema,
            errors=errors or {},
            description_placeholders={
                "options_url": "https://docs.page/mguyard/hass-diagral/integration/setup#options"
            },
            last_step=True,
        )


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth."""
