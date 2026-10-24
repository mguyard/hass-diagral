"""The Diagral integration."""

from __future__ import annotations

import asyncio
from contextlib import suppress
from dataclasses import asdict
import hashlib
from http import HTTPStatus
import logging
from urllib.parse import urlparse

from pydiagral.api import DiagralAPI
from pydiagral.exceptions import DiagralAPIError

from homeassistant.components.webhook import (
    async_generate_id as webhook_generate_id,
    async_register as webhook_async_register,
    async_unregister as webhook_async_unregister,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.network import NoURLAvailableError, get_url

from .const import (
    CONF_API_KEY,
    CONF_PIN_CODE,
    CONF_SECRET_KEY,
    CONF_SERIAL_ID,
    CONF_WEBHOOK_ID as _WEBHOOK_ID,
    CONF_WEBHOOK_URL_HASH,
    CONFIG_MINOR_VERSION,
    CONFIG_VERSION,
    DOMAIN,
    HA_CLOUD_DOMAIN,
    ISSUE_WEBHOOK_OWNED_ELSEWHERE,
    WEBHOOK_REQUEST_TIMEOUT as _WEBHOOK_REQUEST_TIMEOUT,
    WEBHOOK_RETRY_DELAYS as _WEBHOOK_RETRY_DELAYS,
)
from .coordinator import DiagralDataUpdateCoordinator
from .models import DiagralConfigData, DiagralData
from .webhook import handle_webhook

_LOGGER = logging.getLogger(__name__)
PLATFORMS = [Platform.ALARM_CONTROL_PANEL, Platform.SENSOR]

type DiagralConfigEntry = ConfigEntry[DiagralData]


def _ensure_webhook_id(hass: HomeAssistant, entry: DiagralConfigEntry) -> str:
    """Persist the bearer identifier once, including across integration reloads."""
    webhook_id = entry.data.get(_WEBHOOK_ID)
    if not isinstance(webhook_id, str) or not webhook_id:
        webhook_id = webhook_generate_id()
        hass.config_entries.async_update_entry(
            entry, data={**entry.data, _WEBHOOK_ID: webhook_id}
        )
    return webhook_id


def _webhook_health(hass: HomeAssistant, entry: DiagralConfigEntry) -> None:
    """Notify diagnostics entities without sending callback URLs or credentials."""
    async_dispatcher_send(hass, f"signal-{DOMAIN}-{entry.entry_id}-webhook-health")


async def async_setup_entry(hass: HomeAssistant, entry: DiagralConfigEntry) -> bool:
    """Set up polling first; webhook availability must not prevent it."""
    config = DiagralConfigData.from_config_entry(entry)
    config_dict = asdict(config)
    api = DiagralAPI(
        username=config_dict[CONF_USERNAME],
        password=config_dict[CONF_PASSWORD],
        serial_id=config_dict[CONF_SERIAL_ID],
        apikey=config_dict[CONF_API_KEY],
        secret_key=config_dict[CONF_SECRET_KEY],
        pincode=config_dict[CONF_PIN_CODE],
    )
    coordinator = None
    runtime = None
    platforms_started = False
    setup_complete = False
    try:
        await api.__aenter__()
        coordinator = DiagralDataUpdateCoordinator(hass, api, config_entry=entry)
        await coordinator.async_config_entry_first_refresh()
        runtime = DiagralData(
            config=config,
            coordinator=coordinator,
            api=api,
            webhook_id=_ensure_webhook_id(hass, entry),
        )
        entry.runtime_data = runtime
        platforms_started = True
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
        _start_webhook_registration(hass, entry)
        setup_complete = True
        return True
    except (DiagralAPIError, TimeoutError, OSError) as err:
        raise ConfigEntryNotReady("Unable to contact the Diagral service") from err
    finally:
        if not setup_complete:
            try:
                if platforms_started:
                    try:
                        await hass.config_entries.async_unload_platforms(
                            entry, PLATFORMS
                        )
                    except Exception as err:
                        _LOGGER.warning(
                            "Unable to unload partially set up Diagral platforms (%s)",
                            type(err).__name__,
                        )
                if runtime is not None:
                    runtime.stopping = True
                    await unregister_webhook(
                        hass, entry, api, runtime.webhook_id, "setup_failure"
                    )
            finally:
                try:
                    if coordinator is not None:
                        await coordinator.async_shutdown()
                finally:
                    await api.__aexit__(None, None, None)


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
    return subscription_url == new_url or _same_local_webhook_origin(
        subscription_url, new_url
    )


def _remember_subscription(
    hass: HomeAssistant, entry: DiagralConfigEntry, url: str | None
) -> None:
    """Store, or forget, the fingerprint of the subscription this entry owns."""
    data = {k: v for k, v in entry.data.items() if k != CONF_WEBHOOK_URL_HASH}
    if url is not None:
        data[CONF_WEBHOOK_URL_HASH] = _url_hash(url)
    hass.config_entries.async_update_entry(entry, data=data)


def _owned_elsewhere_issue_id(entry: DiagralConfigEntry) -> str:
    return f"{ISSUE_WEBHOOK_OWNED_ELSEWHERE}_{entry.entry_id}"


async def _resolve_webhook_url(hass: HomeAssistant, runtime: DiagralData) -> str | None:
    """Resolve the callback URL without logging its secret path."""
    try:
        external_url = get_url(
            hass,
            require_ssl=True,
            allow_internal=False,
            allow_cloud=True,
            prefer_external=True,
        )
    except NoURLAvailableError:
        runtime.webhook_last_error = "no_external_url"
        return None
    if not external_url:
        runtime.webhook_last_error = "no_external_url"
        return None
    hostname = urlparse(external_url).hostname or ""
    cloud_domain = HA_CLOUD_DOMAIN.lstrip(".")
    if hostname == cloud_domain or hostname.endswith(f".{cloud_domain}"):
        from homeassistant.components.cloud import (  # noqa: PLC0415
            async_active_subscription as cloud_active_subscription,
            async_get_or_create_cloudhook as cloud_get_or_create_cloudhook,
        )

        if not cloud_active_subscription(hass):
            runtime.webhook_last_error = "cloud_subscription_inactive"
            return None
        runtime.webhook_is_cloudhook = True
        return await cloud_get_or_create_cloudhook(hass, runtime.webhook_id)
    return f"{external_url.rstrip('/')}/api/webhook/{runtime.webhook_id}"


def _same_local_webhook_origin(old_url: str, new_url: str) -> bool:
    """Allow migration of an old random ID only on the same HA external origin."""
    old, new = urlparse(old_url), urlparse(new_url)
    return (
        (old.scheme, old.netloc) == (new.scheme, new.netloc)
        and old.path.startswith("/api/webhook/")
        and new.path.startswith("/api/webhook/")
    )


async def _register_webhook_once(
    hass: HomeAssistant,
    entry: DiagralConfigEntry,
    *,
    allow_replace: bool = False,
) -> bool:
    """Register locally before enabling delivery remotely; serialize all changes."""
    runtime = entry.runtime_data
    async with runtime.webhook_lock:
        if runtime.stopping:
            return False
        try:
            if not runtime.webhook_local_registered:
                webhook_async_register(
                    hass,
                    DOMAIN,
                    "Diagral Webhook",
                    runtime.webhook_id,
                    handle_webhook,
                    allowed_methods=("POST", "PUT"),
                )
                runtime.webhook_local_registered = True
            async with asyncio.timeout(_WEBHOOK_REQUEST_TIMEOUT):
                webhook_url = await _resolve_webhook_url(hass, runtime)
                if not webhook_url:
                    return False
                runtime.webhook_url = webhook_url
                try:
                    actual_webhook = await runtime.api.get_webhook()
                except DiagralAPIError as err:
                    if (
                        err.status_code != HTTPStatus.NOT_FOUND
                        and "No subscription found for" not in str(err)
                    ):
                        raise
                    actual_webhook = None
                if actual_webhook is not None:
                    owned = _owns_subscription(
                        entry, actual_webhook.webhook_url, webhook_url
                    )
                    if not owned and not allow_replace:
                        runtime.webhook_status = "conflict"
                        runtime.webhook_last_error = "another_subscription_exists"
                        other_host = (
                            urlparse(actual_webhook.webhook_url).hostname or "?"
                        )
                        _LOGGER.warning(
                            "A different Diagral webhook subscription exists on %s; open Settings > Repairs to take it over",
                            other_host,
                        )
                        ir.async_create_issue(
                            hass,
                            DOMAIN,
                            _owned_elsewhere_issue_id(entry),
                            is_fixable=True,
                            severity=ir.IssueSeverity.ERROR,
                            translation_key=ISSUE_WEBHOOK_OWNED_ELSEWHERE,
                            translation_placeholders={
                                "entry_title": entry.title,
                                "other_host": other_host,
                            },
                            data={"entry_id": entry.entry_id},
                        )
                        return False
                    subscriptions = actual_webhook.subscriptions
                    if actual_webhook.webhook_url != webhook_url or not all(
                        getattr(subscriptions, kind, False)
                        for kind in ("alert", "anomaly", "state")
                    ):
                        await runtime.api.update_webhook(
                            webhook_url=webhook_url,
                            subscribe_to_anomaly=True,
                            subscribe_to_alert=True,
                            subscribe_to_state=True,
                        )
                else:
                    await runtime.api.register_webhook(
                        webhook_url=webhook_url,
                        subscribe_to_anomaly=True,
                        subscribe_to_alert=True,
                        subscribe_to_state=True,
                    )
            _remember_subscription(hass, entry, webhook_url)
            ir.async_delete_issue(hass, DOMAIN, _owned_elsewhere_issue_id(entry))
            runtime.webhook_status = "registered"
            runtime.webhook_last_error = None
            _LOGGER.debug(
                "Diagral webhook subscription registered; registration alone does not verify delivery"
            )
            return True
        except Exception as err:
            runtime.webhook_last_error = type(err).__name__
            _LOGGER.warning(
                "Diagral webhook registration failed (%s); polling remains active",
                type(err).__name__,
            )
            return False
        finally:
            _webhook_health(hass, entry)


async def _webhook_registration_worker(
    hass: HomeAssistant, entry: DiagralConfigEntry
) -> None:
    """Try once then retry with bounded backoff."""
    runtime = entry.runtime_data
    try:
        for attempt, delay in enumerate((0, *_WEBHOOK_RETRY_DELAYS)):
            if delay:
                await asyncio.sleep(delay)
            if runtime.stopping:
                return
            runtime.webhook_retry_attempts = attempt
            if await _register_webhook_once(hass, entry):
                return
            if runtime.webhook_status == "conflict":
                return
            runtime.webhook_status = (
                "retrying"
                if attempt < len(_WEBHOOK_RETRY_DELAYS)
                else "retry_exhausted"
            )
            _webhook_health(hass, entry)
    finally:
        if runtime.webhook_task is asyncio.current_task():
            runtime.webhook_task = None


def _start_webhook_registration(hass: HomeAssistant, entry: DiagralConfigEntry) -> None:
    """Keep exactly one registration worker for this entry."""
    runtime = entry.runtime_data
    if runtime.stopping or (runtime.webhook_task and not runtime.webhook_task.done()):
        return
    runtime.webhook_status = "pending"
    runtime.webhook_task = hass.async_create_background_task(
        _webhook_registration_worker(hass, entry), f"diagral webhook {entry.entry_id}"
    )


async def _cancel_webhook_registration(runtime: DiagralData) -> None:
    """Cancel and await the worker before releasing its session/handler."""
    task = runtime.webhook_task
    if task is not None and task is not asyncio.current_task():
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
    runtime.webhook_task = None


async def register_webhook(
    hass: HomeAssistant,
    entry: DiagralConfigEntry,
    api: DiagralAPI,
    source: str = "Unknown",
    *,
    take_over: bool = False,
) -> str | None:
    """Explicitly register using the stable identifier; retry transient failures."""
    runtime = entry.runtime_data
    await _cancel_webhook_registration(runtime)
    runtime.webhook_status = "pending"
    runtime.webhook_retry_attempts = 0
    registered = await _register_webhook_once(
        hass, entry, allow_replace=take_over or source == "HA Action"
    )
    if not registered and runtime.webhook_status != "conflict":
        _start_webhook_registration(hass, entry)
    return runtime.webhook_id if registered else None


async def unregister_webhook(
    hass: HomeAssistant,
    entry: DiagralConfigEntry,
    api: DiagralAPI,
    webhook_id: str,
    source: str = "Unknown",
) -> None:
    """Remove only our subscription and always release the local handler."""
    runtime = entry.runtime_data
    await _cancel_webhook_registration(runtime)
    async with runtime.webhook_lock:
        try:
            if entry.data.get(CONF_WEBHOOK_URL_HASH):
                async with asyncio.timeout(_WEBHOOK_REQUEST_TIMEOUT):
                    actual_webhook = await api.get_webhook()
                    if (
                        actual_webhook
                        and _url_hash(actual_webhook.webhook_url)
                        == entry.data[CONF_WEBHOOK_URL_HASH]
                    ):
                        await api.delete_webhook()
                        _remember_subscription(hass, entry, None)
        except Exception as err:
            _LOGGER.warning(
                "Unable to remove Diagral webhook subscription (%s)", type(err).__name__
            )
        finally:
            if runtime.webhook_local_registered:
                webhook_async_unregister(hass, webhook_id)
                runtime.webhook_local_registered = False
            # Preserve the opaque cloud URL across reloads. If the remote delete
            # failed, the stable mapping lets the next setup reclaim its own URL.
            if runtime.webhook_is_cloudhook and source != "unload_entry":
                try:
                    from homeassistant.components.cloud import (  # noqa: PLC0415
                        async_delete_cloudhook as cloud_delete_cloudhook,
                    )

                    async with asyncio.timeout(_WEBHOOK_REQUEST_TIMEOUT):
                        await cloud_delete_cloudhook(hass, webhook_id)
                except Exception as err:
                    _LOGGER.warning(
                        "Unable to remove Diagral cloudhook (%s)", type(err).__name__
                    )
                runtime.webhook_is_cloudhook = False
            runtime.webhook_status = "disabled"
            runtime.webhook_url = None
            _webhook_health(hass, entry)


async def async_unload_entry(hass: HomeAssistant, entry: DiagralConfigEntry) -> bool:
    """Unload platforms before releasing the resources they still depend on."""
    if not await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        return False
    runtime = entry.runtime_data
    runtime.stopping = True
    try:
        await unregister_webhook(
            hass, entry, runtime.api, runtime.webhook_id, "unload_entry"
        )
    finally:
        try:
            await runtime.coordinator.async_shutdown()
        finally:
            await runtime.api.__aexit__(None, None, None)
    hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    return True


async def async_remove_entry(hass: HomeAssistant, entry: DiagralConfigEntry) -> None:
    """Remove the API key without exposing it in logs."""
    webhook_id = entry.data.get(_WEBHOOK_ID)
    if webhook_id:
        try:
            from homeassistant.components.cloud import (  # noqa: PLC0415
                async_delete_cloudhook as cloud_delete_cloudhook,
            )

            async with asyncio.timeout(_WEBHOOK_REQUEST_TIMEOUT):
                await cloud_delete_cloudhook(hass, webhook_id)
        except Exception as err:
            _LOGGER.debug(
                "Cloudhook cleanup during Diagral removal unavailable (%s)",
                type(err).__name__,
            )
    apikey = entry.data.get(CONF_API_KEY)
    if not apikey:
        return
    try:
        async with DiagralAPI(
            username=entry.data[CONF_USERNAME],
            password=entry.data[CONF_PASSWORD],
            serial_id=entry.data[CONF_SERIAL_ID],
        ) as api:
            await api.login()
            await api.delete_apikey(apikey=apikey)
            _LOGGER.info("Diagral API key deleted during entry removal")
    except (DiagralAPIError, TimeoutError, OSError) as err:
        _LOGGER.warning("Unable to remove Diagral API key (%s)", type(err).__name__)
