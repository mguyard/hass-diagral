"""Fake Diagral cloud for live validation of hass-diagral.

Implements the part of the Diagral API that pydiagral 1.6.0 calls, keeps all
state in memory, and lets a tester drive it through /_control endpoints:
force a status, publish anomalies, or push a webhook notification to Home
Assistant. Every exchange is logged to stdout, so `docker logs -f` shows it.

All data is synthetic. Nothing here talks to the real Diagral cloud.
"""

from __future__ import annotations

import asyncio
import contextlib
from datetime import UTC, datetime
import itertools
import json
import logging
import os
import re
import secrets
from typing import Any
from urllib.parse import urlparse

from aiohttp import ClientSession, ClientTimeout, web

PORT = int(os.environ.get("FAKE_CLOUD_PORT", "8099"))
# Where Home Assistant listens, as seen from this container. The webhook URL
# Home Assistant registers is its external URL; only its path is kept.
HA_URL = os.environ.get("HA_URL", "http://host.docker.internal:8123").rstrip("/")
USERNAME = os.environ.get("FAKE_USERNAME", "fake@example.com")
PASSWORD = os.environ.get("FAKE_PASSWORD", "fake-password")
PIN_CODE = os.environ.get("FAKE_PIN_CODE", "1234")
MAX_BODY_LOG = 4000

_LOGGER = logging.getLogger("fake_cloud")
_KEY_COUNTER = itertools.count(1)


def _log(direction: str, message: str, *args: Any) -> None:
    _LOGGER.info("%-3s " + message, direction, *args)


def _short(body: Any) -> str:
    if isinstance(body, str):
        with contextlib.suppress(ValueError):
            body = json.loads(body)
    # Someone may type real credentials into the config flow while redirected.
    if isinstance(body, dict) and "password" in body:
        body = {**body, "password": "<redacted>"}
    text = body if isinstance(body, str) else json.dumps(body, ensure_ascii=False)
    return text if len(text) <= MAX_BODY_LOG else text[:MAX_BODY_LOG] + "…"


def _redacted_headers(request: web.Request) -> dict[str, str]:
    shown: dict[str, str] = {}
    for name in ("X-APIKEY", "X-HMAC", "X-PIN-CODE", "Authorization"):
        value = request.headers.get(name)
        if value is None:
            continue
        if name == "X-APIKEY":
            shown[name] = value[:7] + "…"
        else:
            shown[name] = "<redacted>"
    return shown


def _error(status: int, detail: str) -> web.Response:
    # pydiagral splats 400/401/403/5xx bodies into a model with a single field.
    return web.json_response({"detail": detail}, status=status)


def _default_configuration(serial: str) -> dict[str, Any]:
    return {
        "alarm": {
            "name": "fake home",
            "tls": True,
            "forcePushConfig": False,
            "central": {
                "name": "CENTRAL",
                "serial": serial,
                "vendor": "DIAGRAL",
                "firmwares": {"CENTRAL": "1.0.0", "CENTRALRADIO": "2.0.0"},
            },
            "box": {
                "name": "BOX",
                "serial": "FAKEBOX01",
                "vendor": "DIAGRAL",
                "firmwares": {"BOX": "3.0.0"},
            },
        },
        "groups": [
            {"name": "Ground floor", "index": 1, "inputDelay": 30, "outputDelay": 60},
            {"name": "First floor", "index": 2, "inputDelay": 30, "outputDelay": 60},
            {"name": "Garage", "index": 3, "inputDelay": 0, "outputDelay": 0},
        ],
        "sensors": [
            {
                "uid": "S1",
                "type": 1,
                "gamme": 1,
                "group": 1,
                "index": 1,
                "label": "Front door",
                "serial": "FAKE-S1",
                "isVideo": False,
                "refCode": "R1",
                "subtype": 0,
                "inhibited": False,
                "canInhibit": True,
                "anomalies": {},
            },
            {
                "uid": "S2",
                "type": 1,
                "gamme": 1,
                "group": 3,
                "index": 2,
                "label": "Garage motion",
                "serial": "FAKE-S2",
                "isVideo": False,
                "refCode": "R2",
                "subtype": 0,
                "inhibited": False,
                "canInhibit": True,
                "anomalies": {},
            },
        ],
        "sirens": [{"index": 1, "label": "Indoor siren", "group": 1}],
        "commands": [{"index": 1, "label": "Keypad"}],
        "cameras": [],
        "transmitters": [
            {"index": 1, "label": "Transmitter", "isPlug": True, "firmwares": {}}
        ],
        "transceivers": [],
        "readingDate": "2026-01-01T00:00:00",
        "presenceGroup": [1],
        "installationState": 1,
        "centralInformation": {
            "hasPlug": True,
            "plugGSM": False,
            "plugRTC": False,
            "plugADSL": True,
            "relayCard": False,
            "canInhibit": True,
            "parameterGsmSaved": False,
        },
        "partialGroup1": [1],
        "partialGroup2": [2],
    }


class System:
    """State of one fake central, created on first use of its serial."""

    def __init__(self, serial: str) -> None:
        self.serial = serial
        self.configuration = _default_configuration(serial)
        self.status = "OFF"
        self.activated_groups: list[int] = []
        self.api_keys: dict[str, str] = {}
        self.anomalies: dict[str, Any] | None = None
        self.webhook: dict[str, Any] | None = None
        # Exit delay of a real central: arming reports TEMPO_GROUP first.
        self.exit_delay = 0.0
        self.groups_listed_during_delay = True
        self.arming: asyncio.Task | None = None

    @property
    def group_indexes(self) -> list[int]:
        return [group["index"] for group in self.configuration["groups"]]

    def status_payload(self) -> dict[str, Any]:
        return {"status": self.status, "activated_groups": self.activated_groups}

    def as_dict(self) -> dict[str, Any]:
        return {
            "serial": self.serial,
            "status": self.status_payload(),
            "api_keys": [key[:7] + "…" for key in self.api_keys],
            "anomalies": self.anomalies,
            "webhook": self.webhook,
        }


class FakeCloud:
    """In-memory Diagral cloud."""

    def __init__(self) -> None:
        self.systems: dict[str, System] = {}
        self.tokens: set[str] = set()
        self.faults: list[dict[str, Any]] = []

    def system(self, serial: str) -> System:
        if serial not in self.systems:
            self.systems[serial] = System(serial)
        return self.systems[serial]

    def only_serial(self) -> str | None:
        return next(iter(self.systems)) if len(self.systems) == 1 else None


CLOUD = web.AppKey("cloud", FakeCloud)


@web.middleware
async def log_exchanges(request: web.Request, handler) -> web.StreamResponse:
    """Log every request and response, with credentials redacted."""
    body = await request.text() if request.can_read_body else ""
    direction = "CTL" if request.path.startswith("/_control") else "IN"
    _log(
        direction,
        "%s %s headers=%s body=%s",
        request.method,
        request.path_qs,
        _redacted_headers(request),
        _short(body) or "-",
    )
    response = await handler(request)
    payload = getattr(response, "text", None) or "-"
    _log(direction, "→ %s %s", response.status, _short(payload))
    return response


@web.middleware
async def inject_faults(request: web.Request, handler) -> web.StreamResponse:
    """Delay or fail the next API requests queued by /_control/fail."""
    faults = request.app[CLOUD].faults
    if not request.path.startswith("/_control"):
        fault = next((f for f in faults if f["path"] in request.path), None)
        if fault is not None:
            faults.remove(fault)
            _log("CTL", "injecting %s", fault)
            await asyncio.sleep(fault["delay"])
            if fault["status"]:
                return _error(fault["status"], "Injected fault")
    return await handler(request)


def _require_bearer(request: web.Request) -> web.Response | None:
    token = request.headers.get("Authorization", "").removeprefix("Bearer ")
    if token not in request.app[CLOUD].tokens:
        return _error(401, "Invalid or expired token")
    return None


def _require_apikey(
    request: web.Request, system: System, *, pin: bool = False
) -> web.Response | None:
    key = request.headers.get("X-APIKEY") or ""
    if key not in system.api_keys:
        # Config entries keep their key across fake cloud restarts; its state does not
        if not key.startswith("FAKEAK"):
            return _error(401, "Invalid API key")
        system.api_keys[key] = "adopted"
        _log("CTL", "adopted API key %s… issued by a previous run", key[:7])
    if pin and request.headers.get("X-PIN-CODE") != PIN_CODE:
        return _error(403, "Invalid PIN code")
    return None


# --- Accounts and API keys -------------------------------------------------


async def login(request: web.Request) -> web.Response:
    data = await request.json()
    if data.get("username") != USERNAME or data.get("password") != PASSWORD:
        return _error(401, "Invalid credentials")
    token = "fake-token-" + secrets.token_hex(8)
    request.app[CLOUD].tokens.add(token)
    return web.json_response({"access_token": token})


async def create_api_key(request: web.Request) -> web.Response:
    if denied := _require_bearer(request):
        return denied
    data = await request.json()
    system = request.app[CLOUD].system(data["serial_id"])
    number = next(_KEY_COUNTER)
    api_key = f"FAKEAK{number:04d}"
    system.api_keys[api_key] = f"FAKESK{number:04d}"
    return web.json_response(
        {"api_key": api_key, "secret_key": system.api_keys[api_key]}
    )


async def list_api_keys(request: web.Request) -> web.Response:
    if denied := _require_bearer(request):
        return denied
    system = request.app[CLOUD].system(request.match_info["serial"])
    return web.json_response({"api_keys": [{"api_key": k} for k in system.api_keys]})


async def delete_api_key(request: web.Request) -> web.Response:
    if denied := _require_bearer(request):
        return denied
    system = request.app[CLOUD].system(request.match_info["serial"])
    system.api_keys.pop(request.match_info["apikey"], None)
    return web.json_response({})


# --- System ----------------------------------------------------------------


async def get_configuration(request: web.Request) -> web.Response:
    system = request.app[CLOUD].system(request.match_info["serial"])
    if denied := _require_apikey(request, system):
        return denied
    return web.json_response(system.configuration)


async def health(request: web.Request) -> web.Response:
    return web.json_response({"status": "we're alive"})


async def get_system_details(request: web.Request) -> web.Response:
    system = request.app[CLOUD].system(request.match_info["serial"])
    if denied := _require_apikey(request, system, pin=True):
        return denied
    # The real cloud sends the Is* flags as "True" / "False" strings
    return web.json_response(
        {
            "DeviceType": "PLUG_IP~DIAGRAL",
            "FirmwareVersion": "V1.6.0_V13_V1.1.20",
            "IpAddress": "192.0.2.10",
            "IpodaVersion": "3.0",
            "Mode": "900",
            "FirstVocalContact": "0",
            "IsAlarmFilePresent": "False",
            "IsMJPEGArchiveVideoSupported": "False",
            "IsMassStoragePresent": "False",
            "IsRemoteStartupShutdownAllowed": "False",
            "IsVideoPasswordProtected": "False",
        }
    )


async def get_status(request: web.Request) -> web.Response:
    system = request.app[CLOUD].system(request.match_info["serial"])
    if denied := _require_apikey(request, system, pin=True):
        return denied
    return web.json_response(system.status_payload())


async def system_action(request: web.Request) -> web.Response:
    system = request.app[CLOUD].system(request.match_info["serial"])
    if denied := _require_apikey(request, system, pin=True):
        return denied
    action = request.match_info["action"]
    if system.arming is not None:
        system.arming.cancel()
        system.arming = None
    if action == "start":
        _arm(system, system.group_indexes)
    elif action == "stop":
        system.status, system.activated_groups = "OFF", []
    elif action == "presence":
        system.status = "PRESENCE"
        system.activated_groups = list(system.configuration["presenceGroup"])
    else:
        groups = set((await request.json()).get("groups", []))
        if action == "activate_group":
            _arm(system, sorted(set(system.activated_groups) | groups))
        else:
            active = set(system.activated_groups) - groups
            system.activated_groups = sorted(active)
            system.status = "GROUP" if active else "OFF"
    return web.json_response(system.status_payload())


def _arm(system: System, groups: list[int]) -> None:
    """Arm the groups, through TEMPO_GROUP when an exit delay is set."""
    if not system.exit_delay:
        system.status, system.activated_groups = "GROUP", groups
        return
    system.status = "TEMPO_GROUP"
    system.activated_groups = groups if system.groups_listed_during_delay else []
    system.arming = asyncio.create_task(_finish_arming(system, groups))


async def _finish_arming(system: System, groups: list[int]) -> None:
    """End the exit delay, then tell Home Assistant as the real cloud does."""
    await asyncio.sleep(system.exit_delay)
    system.status, system.activated_groups = "GROUP", groups
    system.arming = None
    _log("CTL", "exit delay over for %s: GROUP %s", system.serial, groups)
    if system.webhook is not None:
        await _push(system, _notification(system, {"type": "STATUS"}))


async def get_anomalies(request: web.Request) -> web.Response:
    system = request.app[CLOUD].system(request.match_info["serial"])
    if denied := _require_apikey(request, system):
        return denied
    if not system.anomalies:
        # pydiagral turns exactly this 404 into "no anomalies".
        return _error(404, "No anomalies found")
    return web.json_response(system.anomalies)


# --- Webhook subscription --------------------------------------------------


async def webhook_subscription(request: web.Request) -> web.Response:
    serial = request.match_info["serial"]
    system = request.app[CLOUD].system(serial)
    if denied := _require_apikey(request, system):
        return denied

    if request.method == "GET":
        if system.webhook is None:
            # The integration looks for this literal to tell "none" from a failure.
            return _error(404, f"No subscription found for {serial}")
        return web.json_response(system.webhook)

    if request.method == "DELETE":
        system.webhook = None
        return web.json_response({})

    if request.method == "POST" and system.webhook is not None:
        return _error(409, f"Subscription already exists for {serial}")
    if request.method == "PUT" and system.webhook is None:
        return _error(409, f"There is no subscription for {serial}")

    data = await request.json()
    system.webhook = {
        "transmitter_id": serial,
        "webhook_url": data["webhook_url"],
        "subscriptions": {
            "anomaly": data.get("subscribe_to_anomaly", False),
            "alert": data.get("subscribe_to_alert", False),
            "state": data.get("subscribe_to_state", False),
        },
    }
    return web.json_response(system.webhook)


# --- Control endpoints for the tester --------------------------------------


def _target(request: web.Request, data: dict[str, Any]) -> System | web.Response:
    cloud = request.app[CLOUD]
    serial = data.get("serial") or cloud.only_serial()
    if serial is None:
        return _error(400, "Pass a serial: zero or several systems are known")
    return cloud.system(serial)


async def control_state(request: web.Request) -> web.Response:
    cloud = request.app[CLOUD]
    return web.json_response(
        {"systems": [system.as_dict() for system in cloud.systems.values()]}
    )


async def control_reset(request: web.Request) -> web.Response:
    request.app[CLOUD].systems.clear()
    request.app[CLOUD].tokens.clear()
    request.app[CLOUD].faults.clear()
    return web.json_response({"reset": True})


async def control_fail(request: web.Request) -> web.Response:
    data = await request.json()
    faults = request.app[CLOUD].faults
    if data.get("clear"):
        faults.clear()
    else:
        fault = {
            "path": data.get("path", "/v1/"),
            "status": data.get("status"),
            "delay": float(data.get("delay", 0)),
        }
        faults.extend(dict(fault) for _ in range(int(data.get("count", 1))))
    return web.json_response({"faults": faults})


async def control_status(request: web.Request) -> web.Response:
    data = await request.json()
    system = _target(request, data)
    if isinstance(system, web.Response):
        return system
    system.status = data["status"].upper()
    system.activated_groups = list(data.get("activated_groups", []))
    return web.json_response(system.status_payload())


async def control_anomalies(request: web.Request) -> web.Response:
    data = await request.json()
    system = _target(request, data)
    if isinstance(system, web.Response):
        return system
    if data.get("clear"):
        system.anomalies = None
    else:
        system.anomalies = {
            "created_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f"),
            **data.get("anomalies", {}),
        }
    return web.json_response({"anomalies": system.anomalies})


async def control_webhook(request: web.Request) -> web.Response:
    """Set the subscription to any URL, as another installation would, or clear it."""
    data = await request.json()
    system = _target(request, data)
    if isinstance(system, web.Response):
        return system
    if data.get("clear"):
        system.webhook = None
    else:
        system.webhook = {
            "transmitter_id": system.serial,
            "webhook_url": data["webhook_url"],
            "subscriptions": {"anomaly": True, "alert": True, "state": True},
        }
    return web.json_response({"webhook": system.webhook})


NOTIFICATION_DEFAULTS = {
    "STATUS": {"alarm_code": "3401", "alarm_description": "Total system arming"},
    "ALERT": {"alarm_code": "1130", "alarm_description": "Intrusion"},
    "ANOMALY": {"alarm_code": "1384", "alarm_description": "Low battery"},
}


async def control_notify(request: web.Request) -> web.Response:
    """Push a webhook notification to the URL Home Assistant registered."""
    data = await request.json()
    system = _target(request, data)
    if isinstance(system, web.Response):
        return system
    if system.webhook is None:
        return _error(409, "Home Assistant has not registered a webhook")

    payload = _notification(system, data)
    status, url = await _push(system, payload)
    return web.json_response({"sent_to": url, "payload": payload, "ha_status": status})


def _notification(system: System, data: dict[str, Any]) -> dict[str, Any]:
    """Build a webhook notification, defaults filled per type."""
    kind = data.get("type", "STATUS").upper()
    defaults = NOTIFICATION_DEFAULTS.get(kind, {})
    payload: dict[str, Any] = {
        "transmitter_id": system.serial,
        "alarm_code": str(data.get("alarm_code", defaults.get("alarm_code", "0"))),
        "alarm_description": data.get(
            "alarm_description", defaults.get("alarm_description", "")
        ),
        "group_index": data.get("group_index", "01"),
        "detail": data.get("detail", {}),
        "date_time": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    if kind == "STATUS":
        payload["user"] = data.get(
            "user", {"username": "Fake User", "user_type": "owner"}
        )
    if kind in ("ALERT", "ANOMALY") and "detail" not in data:
        payload["detail"] = {"device_type": "SENSOR", "device_index": "1"}
    # Raw override, to send malformed or unusual payloads on purpose.
    if "raw" in data:
        payload = data["raw"]
    return payload


async def _push(system: System, payload: dict[str, Any]) -> tuple[int, str]:
    """POST a notification to the webhook Home Assistant registered."""
    path = urlparse(system.webhook["webhook_url"]).path
    url = f"{HA_URL}{path}"
    _log("OUT", "POST %s body=%s", url, _short(payload))
    async with (
        ClientSession(timeout=ClientTimeout(total=10)) as session,
        session.post(url, json=payload) as response,
    ):
        text = await response.text()
    _log("OUT", "→ %s %s", response.status, _short(text) or "-")
    return response.status, url


async def control_delay(request: web.Request) -> web.Response:
    data = await request.json()
    system = _target(request, data)
    if isinstance(system, web.Response):
        return system
    system.exit_delay = float(data.get("seconds", 0))
    system.groups_listed_during_delay = bool(data.get("groups_listed", True))
    return web.json_response(
        {
            "exit_delay": system.exit_delay,
            "groups_listed": system.groups_listed_during_delay,
        }
    )


def build_app() -> web.Application:
    app = web.Application(middlewares=[log_exchanges, inject_faults])
    app[CLOUD] = FakeCloud()
    serial = r"{serial:[^/]+}"
    app.add_routes(
        [
            web.get("/", health),
            web.post("/v1/users/authenticate/login", login),
            web.post("/v1/users/api_key", create_api_key),
            web.get(f"/v1/users/systems/{serial}/api_keys", list_api_keys),
            web.delete(
                f"/v1/users/systems/{serial}/api_keys/{{apikey}}", delete_api_key
            ),
            web.get(f"/v1/systems/{serial}", get_system_details),
            web.get(f"/v1/systems/{serial}/configurations", get_configuration),
            web.get(f"/v1/systems/{serial}/status", get_status),
            web.post(
                f"/v1/systems/{serial}/{{action:start|stop|presence|activate_group|disable_group}}",
                system_action,
            ),
            web.get(f"/v1/systems/{serial}/anomalies", get_anomalies),
            web.route("*", f"/v1/webhooks/{serial}/subscription", webhook_subscription),
            web.get("/_control/state", control_state),
            web.post("/_control/reset", control_reset),
            web.post("/_control/status", control_status),
            web.post("/_control/anomalies", control_anomalies),
            web.post("/_control/notify", control_notify),
            web.post("/_control/webhook", control_webhook),
            web.post("/_control/fail", control_fail),
            web.post("/_control/delay", control_delay),
        ]
    )
    return app


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S"
    )
    _LOGGER.info(
        "Fake Diagral cloud on :%s — HA at %s — login %s / PIN %s",
        PORT,
        HA_URL,
        USERNAME,
        re.sub(r".", "*", PIN_CODE),
    )
    web.run_app(build_app(), port=PORT, print=None, access_log=None)
