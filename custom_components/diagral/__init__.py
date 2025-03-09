"""The Diagral integration."""

from __future__ import annotations

from dataclasses import asdict
import logging
from urllib.parse import urlparse

from pydiagral.api import DiagralAPI
from pydiagral.exceptions import DiagralAPIError
from pydiagral.models import Webhook

from homeassistant.components.cloud import (
    CloudNotAvailable,
    CloudNotConnected,
    async_active_subscription as cloud_active_subscription,
    async_delete_cloudhook as cloud_delete_cloudhook,
    async_get_or_create_cloudhook as cloud_get_or_create_cloudhook,
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

from .const import (
    CONF_API_KEY,
    CONF_PIN_CODE,
    CONF_SECRET_KEY,
    CONF_SERIAL_ID,
    DOMAIN,
    HA_CLOUD_DOMAIN,
)
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
    config = DiagralConfigData.from_config_entry(entry)
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
        webhook_id = await register_webhook(hass, entry, api, "setup_entry")

        entry.runtime_data = DiagralData(
            config=config, coordinator=coordinator, api=api, webhook_id=webhook_id
        )
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    except DiagralAPIError as err:
        _LOGGER.error("Failed to set up Diagral integration: %s", err)
        raise ConfigEntryNotReady from err
    except (ValueError, TypeError):
        _LOGGER.exception("Unexpected error setting up Diagral integration")
        return False
    else:
        return True


async def register_webhook(
    hass: HomeAssistant,
    entry: DiagralConfigEntry,
    api: DiagralAPI,
    source: str = "Unknown",
) -> str | None:
    """Register the webhook for Diagral."""
    _LOGGER.debug("Webhook registration requested by '%s' for %s", source, entry.title)
    webhook_id: str = webhook_generate_id()
    # Get the external URL recommended for the webhook (priority to external before cloud)
    try:
        external_url = get_url(
            hass,
            require_ssl=True,
            allow_internal=False,
            allow_cloud=True,
            prefer_external=True,
        )
        _LOGGER.debug("Returned external URL for webhook : %s", external_url)
    except NoURLAvailableError:
        _LOGGER.error(
            "No URL available for Diagral webhook matching criteria (ssl, external). Webhook will not be created"
        )
        return None

    if external_url is not None:
        webhook_set_needed = True
        # If the external URL is a Nabu Casa URL, use the cloudhook
        if external_url.endswith(HA_CLOUD_DOMAIN):
            _LOGGER.debug(
                "Recommanded external URL is Nabu Casa URL (%s). Selected for webhook",
                external_url,
            )
            try:
                if cloud_active_subscription(hass):
                    webhook_url = await cloud_get_or_create_cloudhook(hass, webhook_id)
                else:
                    _LOGGER.error(
                        "Cloud subscription not active. Webhook will not be created"
                    )
            except (CloudNotConnected, CloudNotAvailable):
                _LOGGER.error(
                    "Cloud not connected or not available. Webhook will not be created"
                )
                return None
            except ValueError as e:
                _LOGGER.error("Failed to create cloudhook: %s", e)
                return None
        else:  # Use the external URL
            webhook_url = f"{external_url}/api/webhook/{webhook_id}"
            _LOGGER.debug("Selected external URL for webhook : %s", webhook_url)

        # Check if the webhook is already registered
        try:
            actual_webhook: Webhook = await api.get_webhook()
            # If the webhook is already registered, update the URL
            # Trigger warning if the URL is different (not same scheme and hostname)
            if actual_webhook is not None:
                _LOGGER.debug(
                    "Actual Webhook : %s / New Webhook : %s",
                    actual_webhook,
                    webhook_url,
                )
                if actual_webhook.webhook_url.startswith(
                    f"{urlparse(webhook_url).scheme}://{urlparse(webhook_url).hostname}"
                ):
                    _LOGGER.info(
                        "Webhook already registered for %s on %s. Updating URL to %s",
                        entry.title,
                        actual_webhook.webhook_url,
                        webhook_url,
                    )
                else:
                    _LOGGER.warning(
                        "A Webhook subscription already exists for another URL (%s). Integration will force update of webhook_url to %s",
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

        # If the webhook is not registered, register it
        if webhook_set_needed:
            try:
                await api.register_webhook(
                    webhook_url=webhook_url,
                    subscribe_to_anomaly=True,
                    subscribe_to_alert=True,
                    subscribe_to_state=True,
                )
            except DiagralAPIError as e:
                _LOGGER.error(
                    "Failed to create webhook for %s on %s : %s",
                    entry.title,
                    webhook_url,
                    e,
                )
                return None
            else:
                _LOGGER.info(
                    "Webhook successfully created for %s on : %s",
                    entry.title,
                    webhook_url,
                )
                webhook_async_register(
                    hass, DOMAIN, "Diagral Webhook", webhook_id, handle_webhook
                )
                _LOGGER.info("Webhook successfully registered for %s", entry.title)

    return webhook_id


async def unregister_webhook(
    hass: HomeAssistant,
    entry: DiagralConfigEntry,
    api: DiagralAPI,
    webhook_id: str,
    source: str = "Unknown",
) -> None:
    """Unregister the webhook for Diagral."""
    _LOGGER.debug(
        "Webhook unregistration requested by '%s' for %s", source, entry.title
    )
    if webhook_id:
        try:
            actual_webhook: Webhook = await api.get_webhook()
            await api.delete_webhook()
        except DiagralAPIError as e:
            _LOGGER.error(
                "Failed to delete webhook for %s : %s",
                entry.title,
                e,
            )
        else:
            _LOGGER.info("Webhook successfully deleted for %s", entry.title)
            if actual_webhook is not None and actual_webhook.webhook_url.startswith(
                "https://hooks.nabu.casa/"
            ):
                _LOGGER.debug(
                    "Webhook was a cloudhook. Deleting cloudhook %s", webhook_id
                )
                try:
                    await cloud_delete_cloudhook(hass, webhook_id)
                except ValueError as e:
                    _LOGGER.error("Failed to delete cloudhook: %s", e)
            else:
                webhook_async_unregister(hass, webhook_id)
            # Force the webhook_id in the entry runtime data to be sure it is saved
            entry.runtime_data.webhook_id = None


async def async_unload_entry(hass: HomeAssistant, entry: DiagralConfigEntry) -> bool:
    """Unload a config entry."""

    api: DiagralAPI = entry.runtime_data.api
    webhook_id: str = entry.runtime_data.webhook_id

    await unregister_webhook(hass, entry, api, webhook_id, "unload_entry")

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
