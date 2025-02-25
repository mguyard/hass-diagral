"""The Diagral integration."""

from __future__ import annotations

from dataclasses import asdict
import logging

from pydiagral.api import DiagralAPI
from pydiagral.exceptions import DiagralAPIError

from homeassistant.components.cloud import (
    async_active_subscription as cloud_active_subscription,
)
from homeassistant.components.webhook import (
    async_generate_id as webhook_generate_id,
    # SUPPORTED_METHODS,
    async_register as webhook_async_register,
    async_unregister as webhook_async_unregister,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.network import NoURLAvailableError, get_url

from .const import CONF_API_KEY, CONF_PIN_CODE, CONF_SECRET_KEY, CONF_SERIAL_ID, DOMAIN
from .coordinator import DiagralDataUpdateCoordinator
from .models import DiagralConfigData, DiagralData
from .webhook import handle_webhook

_LOGGER: logging.Logger = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.ALARM_CONTROL_PANEL,
    Platform.BINARY_SENSOR,
    Platform.SENSOR,
]

type DiagralConfigEntry = ConfigEntry[DiagralData]


async def async_setup_entry(hass: HomeAssistant, entry: DiagralConfigEntry) -> bool:
    """Set up Diagral from a config entry."""
    config = DiagralConfigData(**entry.data)
    # Convert DiagralConfigData to a standard dictionary
    config_dict = asdict(config)

    try:
        api = DiagralAPI(
            username=config_dict[CONF_USERNAME],
            password=config_dict[CONF_PASSWORD],
            serial_id=config_dict[CONF_SERIAL_ID],
            apikey=config_dict[CONF_API_KEY],
            secret_key=config_dict[CONF_SECRET_KEY],
            pincode=config_dict[CONF_PIN_CODE],
        )

        await api.__aenter__()  # Open the session explicitly  # pylint: disable=C2801
        coordinator = DiagralDataUpdateCoordinator(hass, api)
        await coordinator.async_config_entry_first_refresh()

        # Register the webhook
        webhook_id = await register_webhook(hass, entry, api)

        entry.runtime_data = DiagralData(
            config=config, coordinator=coordinator, api=api, webhook_id=webhook_id
        )
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
        entry.async_on_unload(entry.add_update_listener(async_update_options))

    except DiagralAPIError as err:
        _LOGGER.error("Failed to set up Diagral integration: %s", err)
        raise ConfigEntryNotReady from err
    except (ValueError, TypeError):
        _LOGGER.exception("Unexpected error setting up Diagral integration")
        return False
    else:
        return True


async def register_webhook(
    hass: HomeAssistant, entry: DiagralConfigEntry, api: DiagralAPI
) -> str:
    """Register the webhook for Diagral."""
    webhook_id: str = webhook_generate_id()
    if cloud_active_subscription(hass):
        webhook_url = await hass.components.cloud.async_create_cloudhook(webhook_id)
    else:
        try:
            external_url = get_url(
                hass,
                require_ssl=True,
                allow_internal=False,
                allow_cloud=True,
                prefer_external=True,
            )
            webhook_url = f"{external_url}/api/webhook/{webhook_id}"
            webhook_set_needed = True
            try:
                # Check if the webhook is already registered
                actual_webhook = await api.get_webhook()
                # If the webhook is already registered, update the URL
                # or if no subscription found, pass
                if actual_webhook.webhook_url.startswith(
                    f"{external_url}/api/webhook/"
                ):
                    _LOGGER.info(
                        "Webhook already registered for %s on %s. Updating URL to %s",
                        entry.title,
                        actual_webhook.webhook_url,
                        webhook_url,
                    )
                    await api.update_webhook(
                        webhook_url=webhook_url,
                        subscribe_to_anomaly=True,
                        subscribe_to_alert=True,
                        subscribe_to_state=True,
                    )
                    webhook_set_needed = False
            except DiagralAPIError as err:
                if "No subscription found for" in str(err):
                    pass
                else:
                    raise

            # If the webhook is not registered, create it
            if webhook_set_needed:
                await api.register_webhook(
                    webhook_url=webhook_url,
                    subscribe_to_anomaly=True,
                    subscribe_to_alert=True,
                    subscribe_to_state=True,
                )
                _LOGGER.info(
                    "Webhook successfully created for %s on %s",
                    entry.title,
                    webhook_url,
                )
        except NoURLAvailableError:
            _LOGGER.error(
                "No URL available for Diagral webhook matching criteria (ssl, external). Webhook will not be created"
            )

    webhook_async_register(hass, DOMAIN, "Diagral Webhook", webhook_id, handle_webhook)
    _LOGGER.info("Webhook successfully registered for %s", entry.title)
    return webhook_id


async def async_update_options(hass: HomeAssistant, entry: DiagralConfigEntry) -> None:
    """Update options."""
    # Retrieve the current configuration
    current_config: DiagralConfigData = entry.runtime_data.config

    # Convert DiagralConfigData to a standard dictionary
    current_config_dict = asdict(current_config)

    # Create a new configuration by combining current data and new options
    new_config = {
        **current_config_dict,
        CONF_USERNAME: entry.options.get(
            CONF_USERNAME, current_config_dict[CONF_USERNAME]
        ),
        CONF_PASSWORD: entry.options.get(
            CONF_PASSWORD, current_config_dict[CONF_PASSWORD]
        ),
        CONF_PIN_CODE: entry.options.get(
            CONF_PIN_CODE, current_config_dict[CONF_PIN_CODE]
        ),
    }

    # Update configuration data
    entry.runtime_data.config = DiagralConfigData(**new_config)

    # Update the configuration entry
    hass.config_entries.async_update_entry(entry, data=new_config)

    # Reload the configuration entry
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: DiagralConfigEntry) -> bool:
    """Unload a config entry."""

    api: DiagralAPI = entry.runtime_data.api
    webhook_id: str = entry.runtime_data.webhook_id

    if webhook_id:
        try:
            await api.delete_webhook()
        except DiagralAPIError as e:
            _LOGGER.error(
                "Failed to delete webhook for %s during entry unloading: %s",
                entry.title,
                e,
            )
        _LOGGER.info(
            "Webhook successfully deleted for %s during entry unloading", entry.title
        )
        webhook_async_unregister(hass, webhook_id)

    await api.__aexit__(None, None, None)  # Close explicitly the session

    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        if DOMAIN in hass.data and entry.entry_id in hass.data[DOMAIN]:
            hass.data[DOMAIN].pop(entry.entry_id)
        return unload_ok
    return False


async def async_remove_entry(hass: HomeAssistant, entry: DiagralConfigEntry) -> None:
    """Handle removal of an entry."""
    # Retrieve the stored API key
    apikey = entry.data.get(CONF_API_KEY)

    if apikey:
        try:
            async with DiagralAPI(
                username=entry.data[CONF_USERNAME],
                password=entry.data[CONF_PASSWORD],
                serial_id=entry.data[CONF_SERIAL_ID],
            ) as diagral:
                await diagral.login()
                try:
                    await diagral.delete_apikey(apikey=apikey)
                    _LOGGER.info(
                        "API key %s successfully deleted for %s during entry removal",
                        apikey,
                        entry.title,
                    )
                except DiagralAPIError as e:
                    _LOGGER.error("Failed to delete API key for %s: %s", entry.title, e)
        except DiagralAPIError as e:
            _LOGGER.error("Failed to interact with API for %s: %s", entry.title, e)
    else:
        _LOGGER.warning("No API key found for %s, skipping deletion", entry.title)
