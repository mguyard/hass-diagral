"""The Diagral integration."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timedelta
from functools import partial
import hashlib
import logging
from urllib.parse import urlparse

from pydiagral.api import DiagralAPI
from pydiagral.exceptions import DiagralAPIError
from pydiagral.models import Webhook

from homeassistant.components.webhook import (
    async_generate_id as webhook_generate_id,
    # SUPPORTED_METHODS,
    async_register as webhook_async_register,
    async_unregister as webhook_async_unregister,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, CONF_WEBHOOK_ID, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.network import NoURLAvailableError, get_url

from .const import (
    CONF_API_KEY,
    CONF_PIN_CODE,
    CONF_SECRET_KEY,
    CONF_SERIAL_ID,
    CONF_WEBHOOK_URL_HASH,
    CONFIG_MINOR_VERSION,
    CONFIG_VERSION,
    DIAGRAL_REQUEST_TIMEOUT,
    DIAGRAL_VENDOR,
    DOMAIN,
    HA_CLOUD_DOMAIN,
    INTERACTIVE_REQUEST_TIMEOUT,
    ISSUE_WEBHOOK_NO_URL,
    ISSUE_WEBHOOK_OWNED_ELSEWHERE,
    ISSUE_WEBHOOK_REGISTRATION_FAILED,
    WEBHOOK_CHECK_INTERVAL,
    WEBHOOK_CONNECTED,
    WEBHOOK_ISSUES,
    WEBHOOK_OWNED_ELSEWHERE,
    WEBHOOK_STATUS_OF_ISSUE,
    WEBHOOK_UNREGISTERED,
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
    # Entries removed before their repairs were deleted with them left some behind
    _delete_orphan_issues(hass)
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
            request_timeout=DIAGRAL_REQUEST_TIMEOUT,
            session=async_get_clientsession(hass),
            vendor=DIAGRAL_VENDOR,
        )
        coordinator = DiagralDataUpdateCoordinator(hass, api)
        await coordinator.async_config_entry_first_refresh()

        try:
            webhook_id = await _async_connect_webhook(
                hass, entry, api, coordinator, "setup_entry"
            )
        except WebhookUnavailable as err:
            # Polling still works; the repair says why events cannot arrive
            report_webhook_unavailable(hass, entry, err.reason)
            webhook_id = None

        entry.runtime_data = DiagralData(
            config=config, coordinator=coordinator, api=api, webhook_id=webhook_id
        )
        entry.async_on_unload(
            async_track_time_interval(
                hass,
                partial(_async_scheduled_check, hass, entry),
                timedelta(seconds=WEBHOOK_CHECK_INTERVAL),
            )
        )
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    except DiagralAPIError as err:
        _LOGGER.error("Failed to set up Diagral integration: %s", err)
        raise ConfigEntryNotReady from err
    except ValueError, TypeError:
        _LOGGER.exception("Unexpected error setting up Diagral integration")
        return False
    else:
        return True


async def async_migrate_entry(hass: HomeAssistant, config_entry: DiagralConfigEntry):
    """Migrate the config entry to a new version."""
    _LOGGER.debug(
        "Migrating configuration from version %s.%s",
        config_entry.version,
        config_entry.minor_version,
    )

    if config_entry.version > CONFIG_VERSION:
        # This means the user has downgraded from a future version
        return False

    if config_entry.version == 1:
        new_data = {**config_entry.data}
        if config_entry.minor_version == 1:
            # A PIN stored as an int has already lost its leading zeros
            new_data[CONF_PIN_CODE] = str(config_entry.data[CONF_PIN_CODE])

        hass.config_entries.async_update_entry(
            config_entry,
            data=new_data,
            version=CONFIG_VERSION,
            minor_version=CONFIG_MINOR_VERSION,
        )

    return True


def _redact_url(url: str | None) -> str:
    """Keep scheme and host of a webhook URL; its path carries the secret id."""
    if not url:
        return str(url)
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}/<redacted>"


def _url_hash(url: str) -> str:
    """Return the fingerprint an entry keeps of the subscription it owns."""
    return hashlib.sha256(url.encode()).hexdigest()


def _owns_subscription(
    entry: DiagralConfigEntry, subscription_url: str, new_url: str
) -> bool:
    """Tell whether the central's subscription was registered by this entry."""
    stored = entry.data.get(CONF_WEBHOOK_URL_HASH)
    if stored is not None:
        return stored == _url_hash(subscription_url)
    # Entries set up before ownership was tracked: same scheme and host
    current, new = urlparse(subscription_url), urlparse(new_url)
    return (current.scheme, current.hostname) == (new.scheme, new.hostname)


def _remember_subscription(
    hass: HomeAssistant,
    entry: DiagralConfigEntry,
    url: str | None,
    webhook_id: str | None = None,
) -> None:
    """Store, or forget, the fingerprint of the subscription this entry owns."""
    data = {k: v for k, v in entry.data.items() if k != CONF_WEBHOOK_URL_HASH}
    if url is not None:
        data[CONF_WEBHOOK_URL_HASH] = _url_hash(url)
    if webhook_id is not None:
        data[CONF_WEBHOOK_ID] = webhook_id
    hass.config_entries.async_update_entry(entry, data=data)


def _issue_id(issue: str, entry: DiagralConfigEntry) -> str:
    return f"{issue}_{entry.entry_id}"


def _delete_issues(hass: HomeAssistant, entry_id: str) -> None:
    """Delete the webhook repair issues of a config entry."""
    for issue in WEBHOOK_ISSUES:
        ir.async_delete_issue(hass, DOMAIN, f"{issue}_{entry_id}")


def _delete_orphan_issues(hass: HomeAssistant) -> None:
    """Delete the webhook repair issues whose config entry no longer exists."""
    entry_ids = {entry.entry_id for entry in hass.config_entries.async_entries(DOMAIN)}
    for domain, issue_id in list(ir.async_get(hass).issues):
        if domain != DOMAIN:
            continue
        for issue in WEBHOOK_ISSUES:
            prefix = f"{issue}_"
            if issue_id.startswith(prefix) and issue_id[len(prefix) :] not in entry_ids:
                ir.async_delete_issue(hass, DOMAIN, issue_id)


class WebhookUnavailable(Exception):
    """The webhook could not be registered, so no Diagral event can arrive."""

    def __init__(self, reason: str) -> None:
        """Keep the repair issue key that explains the failure."""
        super().__init__(reason)
        self.reason = reason


def report_webhook_unavailable(
    hass: HomeAssistant, entry: DiagralConfigEntry, reason: str
) -> None:
    """Raise the repair issue that explains why no event can arrive."""
    ir.async_create_issue(
        hass,
        DOMAIN,
        _issue_id(reason, entry),
        # Only a Diagral or cloud error can be fixed by retrying
        is_fixable=reason == ISSUE_WEBHOOK_REGISTRATION_FAILED,
        # Intrusion alerts only arrive by webhook, never by polling
        severity=ir.IssueSeverity.ERROR,
        translation_key=reason,
        translation_placeholders={"entry_title": entry.title},
        data={"entry_id": entry.entry_id},
    )


def _report_owned_elsewhere(
    hass: HomeAssistant, entry: DiagralConfigEntry, subscription_url: str
) -> None:
    """Raise the repair for a subscription owned by another installation."""
    ir.async_create_issue(
        hass,
        DOMAIN,
        _issue_id(ISSUE_WEBHOOK_OWNED_ELSEWHERE, entry),
        is_fixable=True,
        # Intrusion alerts only arrive by webhook, never by polling
        severity=ir.IssueSeverity.ERROR,
        translation_key=ISSUE_WEBHOOK_OWNED_ELSEWHERE,
        translation_placeholders={
            "entry_title": entry.title,
            "other_host": urlparse(subscription_url).hostname or "?",
        },
        data={"entry_id": entry.entry_id},
    )


async def _async_webhook_url(hass: HomeAssistant, webhook_id: str) -> str:
    """Return the URL Diagral should call: a cloudhook behind Nabu Casa."""
    from homeassistant.components.cloud import (  # noqa: PLC0415
        CloudNotAvailable,
        CloudNotConnected,
        async_active_subscription as cloud_active_subscription,
        async_get_or_create_cloudhook as cloud_get_or_create_cloudhook,
    )

    try:
        external_url = get_url(
            hass,
            require_ssl=True,
            allow_internal=False,
            allow_cloud=True,
            prefer_external=True,
        )
    except NoURLAvailableError as err:
        _LOGGER.error(
            "No URL available for Diagral webhook matching criteria (ssl, external). Webhook will not be created"
        )
        raise WebhookUnavailable(ISSUE_WEBHOOK_NO_URL) from err
    _LOGGER.debug("Returned external URL for webhook : %s", external_url)

    if not external_url.endswith(HA_CLOUD_DOMAIN):
        webhook_url = f"{external_url}/api/webhook/{webhook_id}"
        _LOGGER.debug(
            "Selected external URL for webhook : %s", _redact_url(webhook_url)
        )
        return webhook_url

    _LOGGER.debug(
        "Recommanded external URL is Nabu Casa URL (%s). Selected for webhook",
        external_url,
    )
    try:
        if not cloud_active_subscription(hass):
            _LOGGER.error("Cloud subscription not active. Webhook will not be created")
            raise WebhookUnavailable(ISSUE_WEBHOOK_NO_URL)
        return await cloud_get_or_create_cloudhook(hass, webhook_id)
    except CloudNotAvailable as err:
        _LOGGER.error("Cloud not available. Webhook will not be created")
        raise WebhookUnavailable(ISSUE_WEBHOOK_NO_URL) from err
    except (CloudNotConnected, ValueError) as err:
        _LOGGER.error("Failed to create cloudhook: %s", type(err).__name__)
        raise WebhookUnavailable(ISSUE_WEBHOOK_REGISTRATION_FAILED) from err


async def _async_subscribe(
    hass: HomeAssistant,
    entry: DiagralConfigEntry,
    api: DiagralAPI,
    webhook_url: str,
    *,
    take_over: bool,
) -> bool:
    """Point the central's subscription to webhook_url, unless owned elsewhere."""
    try:
        actual_webhook: Webhook | None = await api.get_webhook()
    except DiagralAPIError as err:
        if "No subscription found for" not in str(err):
            raise
        actual_webhook = None

    if actual_webhook is None:
        await api.register_webhook(
            webhook_url=webhook_url,
            subscribe_to_anomaly=True,
            subscribe_to_alert=True,
            subscribe_to_state=True,
        )
        _LOGGER.info(
            "Webhook successfully created for %s on : %s",
            entry.title,
            _redact_url(webhook_url),
        )
        return True

    _LOGGER.debug(
        "Actual Webhook : %s / New Webhook : %s",
        _redact_url(actual_webhook.webhook_url),
        _redact_url(webhook_url),
    )
    owned = _owns_subscription(entry, actual_webhook.webhook_url, webhook_url)
    if not owned and not take_over:
        _LOGGER.warning(
            "The Diagral webhook subscription of %s points to another "
            "installation (%s). It was left untouched: open Settings > "
            "Repairs to take it over",
            entry.title,
            _redact_url(actual_webhook.webhook_url),
        )
        _report_owned_elsewhere(hass, entry, actual_webhook.webhook_url)
        return False
    if actual_webhook.webhook_url == webhook_url:
        _LOGGER.debug("Webhook subscription of %s is already current", entry.title)
        return True
    if owned:
        _LOGGER.info(
            "Webhook already registered for %s on %s. Updating URL to %s",
            entry.title,
            _redact_url(actual_webhook.webhook_url),
            _redact_url(webhook_url),
        )
    else:
        _LOGGER.warning(
            "Taking over the Diagral webhook subscription of %s from %s",
            entry.title,
            _redact_url(actual_webhook.webhook_url),
        )
    await api.update_webhook(
        webhook_url=webhook_url,
        subscribe_to_anomaly=True,
        subscribe_to_alert=True,
        subscribe_to_state=True,
    )
    return True


async def register_webhook(
    hass: HomeAssistant,
    entry: DiagralConfigEntry,
    api: DiagralAPI,
    source: str = "Unknown",
    *,
    take_over: bool = False,
) -> str | None:
    """Register the webhook for Diagral.

    Home Assistant listens before Diagral is told where to send, so no event
    is lost. A subscription this entry cannot prove it owns is left untouched
    and reported as a repair issue, unless take_over is set; None is then
    returned. Raises WebhookUnavailable when no event can be received.
    """
    _LOGGER.debug("Webhook registration requested by '%s' for %s", source, entry.title)
    # A stable id keeps the URL, so a restart does not rewrite the subscription
    webhook_id: str = entry.data.get(CONF_WEBHOOK_ID) or webhook_generate_id()
    webhook_url = await _async_webhook_url(hass, webhook_id)

    # The register action re-registers an id that may already be listening
    webhook_async_unregister(hass, webhook_id)
    webhook_async_register(hass, DOMAIN, "Diagral Webhook", webhook_id, handle_webhook)
    try:
        subscribed = await _async_subscribe(
            hass, entry, api, webhook_url, take_over=take_over
        )
    except DiagralAPIError as err:
        webhook_async_unregister(hass, webhook_id)
        _LOGGER.error(
            "Failed to register the Diagral webhook for %s on %s : %s",
            entry.title,
            _redact_url(webhook_url),
            err,
        )
        raise WebhookUnavailable(ISSUE_WEBHOOK_REGISTRATION_FAILED) from err
    if not subscribed:
        webhook_async_unregister(hass, webhook_id)
        return None

    _remember_subscription(hass, entry, webhook_url, webhook_id)
    _delete_issues(hass, entry.entry_id)
    _LOGGER.info("Webhook successfully registered for %s", entry.title)
    return webhook_id


async def _async_connect_webhook(
    hass: HomeAssistant,
    entry: DiagralConfigEntry,
    api: DiagralAPI,
    coordinator: DiagralDataUpdateCoordinator,
    source: str,
) -> str | None:
    """Register the webhook and record its state for the diagnostics."""
    try:
        webhook_id = await register_webhook(hass, entry, api, source)
    except WebhookUnavailable as err:
        coordinator.async_set_webhook_status(WEBHOOK_STATUS_OF_ISSUE[err.reason])
        raise
    coordinator.async_set_webhook_status(
        WEBHOOK_CONNECTED if webhook_id else WEBHOOK_OWNED_ELSEWHERE
    )
    return webhook_id


async def async_check_webhook(hass: HomeAssistant, entry: DiagralConfigEntry) -> None:
    """Notice a subscription taken over or deleted since the last check.

    A working webhook is only read: register_webhook drops the local handler
    when Diagral fails, which a passing outage must never do. Any other state
    is retried, so the webhook recovers by itself.
    """
    runtime = entry.runtime_data
    coordinator = runtime.coordinator
    if coordinator.webhook_status == WEBHOOK_UNREGISTERED:
        return
    if coordinator.webhook_status == WEBHOOK_CONNECTED:
        try:
            subscription: Webhook | None = await runtime.api.get_webhook()
        except DiagralAPIError as err:
            if "No subscription found for" not in str(err):
                _LOGGER.debug("Webhook check skipped: %s", type(err).__name__)
                return
            subscription = None
        stored = entry.data.get(CONF_WEBHOOK_URL_HASH)
        if subscription is not None and stored == _url_hash(subscription.webhook_url):
            return
        if subscription is not None:
            _LOGGER.warning(
                "The Diagral webhook subscription of %s was taken by another "
                "installation (%s): open Settings > Repairs to take it back",
                entry.title,
                _redact_url(subscription.webhook_url),
            )
            _report_owned_elsewhere(hass, entry, subscription.webhook_url)
            coordinator.async_set_webhook_status(WEBHOOK_OWNED_ELSEWHERE)
            return
    try:
        runtime.webhook_id = await _async_connect_webhook(
            hass, entry, runtime.api, coordinator, "hourly_check"
        )
    except WebhookUnavailable:
        _LOGGER.debug("Webhook still unavailable for %s", entry.title)


async def _async_scheduled_check(
    hass: HomeAssistant, entry: DiagralConfigEntry, _now: datetime
) -> None:
    await async_check_webhook(hass, entry)


async def unregister_webhook(
    hass: HomeAssistant,
    entry: DiagralConfigEntry,
    api: DiagralAPI,
    webhook_id: str,
    source: str = "Unknown",
) -> bool:
    """Unregister the webhook for Diagral.

    The central's subscription is only deleted when this entry owns it.
    Returns False when the subscription could not be read or deleted.
    """
    from homeassistant.components.cloud import (  # noqa: PLC0415
        async_delete_cloudhook as cloud_delete_cloudhook,
    )

    _LOGGER.debug(
        "Webhook unregistration requested by '%s' for %s", source, entry.title
    )
    if not webhook_id:
        return True

    done = True
    try:
        actual_webhook: Webhook | None = await api.get_webhook()
    except DiagralAPIError as err:
        if "No subscription found for" not in str(err):
            _LOGGER.error("Failed to read webhook for %s : %s", entry.title, err)
            done = False
        actual_webhook = None

    stored = entry.data.get(CONF_WEBHOOK_URL_HASH)
    if (
        actual_webhook is not None
        and stored is not None
        and stored == _url_hash(actual_webhook.webhook_url)
    ):
        try:
            await api.delete_webhook()
        except DiagralAPIError as e:
            _LOGGER.error("Failed to delete webhook for %s : %s", entry.title, e)
            done = False
        else:
            _LOGGER.info("Webhook successfully deleted for %s", entry.title)
            _remember_subscription(hass, entry, None)
        if actual_webhook.webhook_url.startswith("https://hooks.nabu.casa/"):
            _LOGGER.debug("Webhook was a cloudhook. Deleting cloudhook")
            try:
                await cloud_delete_cloudhook(hass, webhook_id)
            except ValueError as e:
                _LOGGER.error("Failed to delete cloudhook: %s", e)
                done = False
    elif actual_webhook is not None:
        _LOGGER.info(
            "The Diagral webhook subscription of %s is not owned by this "
            "installation; it was left untouched",
            entry.title,
        )

    webhook_async_unregister(hass, webhook_id)
    # Force the webhook_id in the entry runtime data to be sure it is saved
    entry.runtime_data.webhook_id = None
    return done


async def async_unload_entry(hass: HomeAssistant, entry: DiagralConfigEntry) -> bool:
    """Unload a config entry."""

    api: DiagralAPI = entry.runtime_data.api
    webhook_id: str = entry.runtime_data.webhook_id

    await unregister_webhook(hass, entry, api, webhook_id, "unload_entry")

    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        if DOMAIN in hass.data and entry.entry_id in hass.data[DOMAIN]:
            hass.data[DOMAIN].pop(entry.entry_id)
        return unload_ok
    return False


async def async_remove_entry(hass: HomeAssistant, entry: DiagralConfigEntry) -> None:
    """Handle removal of an entry."""
    # First, so a Diagral outage below cannot leave them behind
    _delete_issues(hass, entry.entry_id)
    # Retrieve the stored API key
    apikey = entry.data.get(CONF_API_KEY)

    if apikey:
        try:
            async with DiagralAPI(
                username=entry.data[CONF_USERNAME],
                password=entry.data[CONF_PASSWORD],
                serial_id=entry.data[CONF_SERIAL_ID],
                request_timeout=INTERACTIVE_REQUEST_TIMEOUT,
                session=async_get_clientsession(hass),
                vendor=DIAGRAL_VENDOR,
            ) as diagral:
                await diagral.login()
                try:
                    await diagral.delete_apikey(apikey=apikey)
                    _LOGGER.info(
                        "API key successfully deleted for %s during entry removal",
                        entry.title,
                    )
                except DiagralAPIError as e:
                    _LOGGER.error("Failed to delete API key for %s: %s", entry.title, e)
        except DiagralAPIError as e:
            _LOGGER.error("Failed to interact with API for %s: %s", entry.title, e)
    else:
        _LOGGER.warning("No API key found for %s, skipping deletion", entry.title)
