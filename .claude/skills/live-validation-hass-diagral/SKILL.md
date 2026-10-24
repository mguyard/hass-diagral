---
name: live-validation-hass-diagral
description: Proving a hass-diagral change works on a running Home Assistant without breaking the production instance that shares the same Diagral central — the three validation levels, the shared-central constraint, driving Home Assistant over REST, and the restore procedure after a real-central session.
---

# Live Validation — hass-diagral

Unit tests prove the logic of a function. They cannot prove that the webhook round trip works, that a state survives a real poll after a webhook, or that the device registry is updated — that needs a running Home Assistant. This skill describes how to get there **without touching the production central** unless the maintainer explicitly decides to.

---

## 1. The Constraint: One Central, One Webhook

The maintainer's production Home Assistant uses the **same Diagral central** as the development instance. The central holds a **single** webhook subscription:

- Setting up the integration on another instance calls `register_webhook`, which finds the existing subscription and **re-points it** to the new instance (log: `A Webhook subscription already exists for another URL … Integration will force update`).
- Unloading the entry there — disabling it, removing it, or the `unregister_webhook` action — **deletes** the subscription outright.

Either way, production stops receiving events, silently. Restarting Home Assistant does not unload entries, so a dev instance left enabled keeps the subscription until it is unloaded.

The development config entry backed by the real credentials therefore stays **disabled**. Enabling it is a decision the maintainer takes for a specific session — never on your own.

---

## 2. Choosing a Level

| Level | What it proves | Touches the real central | When |
|---|---|---|---|
| 1 — pytest with mocks | Logic of each function | No | Always (`testing-hass-diagral`) |
| 2 — Fake Diagral cloud | Full runtime: setup, polling, webhook register / receive / unregister, events, entity states | No | Any change to runtime behaviour — **not available yet**, see §4 |
| 3 — Real central | Behaviour of the real Diagral API and real hardware | **Yes** | Rarely, with explicit consent: before a significant release, a `pydiagral` bump, or when the real API's behaviour is in question |

Until level 2 exists, a runtime change is validated by level 1 plus, if the maintainer agrees, level 3. State in the pull request which level was used.

---

## 3. Driving Home Assistant

### 3.1 Environment

Any real Home Assistant works. The maintainer uses a Home Assistant core devcontainer whose `config/custom_components/diagral` is bind-mounted from this repository — a local checkout changes what Home Assistant loads on its next restart. Resolve the container by image:

```bash
C=$(docker ps --format '{{.ID}} {{.Image}}' | awk '/vsc-home-assistant-dev/ {print $1}')
```

Logging needed in `configuration.yaml`:

```yaml
logger:
  default: info
  logs:
    custom_components.diagral: debug
    pydiagral.api: debug
```

> **Ask the human to restart Home Assistant. Do not restart it yourself** — they follow the logs live. A code change requires a restart; reloading the entry does not re-import Python modules.

A browser session on the Home Assistant UI (Claude in Chrome) can be used for what the REST API does not cover, such as enabling or disabling an entry. Ask before doing either — see §1.

### 3.2 REST API

A long-lived access token is needed, created by the human from their Home Assistant profile and stored in a file. Never read or print it; reference it as `$(cat <token-file>)`.

```bash
H="Authorization: Bearer $(cat <token-file>)"
curl -s -H "$H" http://localhost:8123/api/states/alarm_control_panel.<alarm>_central
curl -s -H "$H" -X POST http://localhost:8123/api/services/homeassistant/update_entity \
  -d '{"entity_id": "alarm_control_panel.<alarm>_central"}'
```

Listening for `DIAGRAL_EVENT` is done over the websocket API (`subscribe_events` with `event_type: DIAGRAL_EVENT`), or in the UI under Developer tools → Events.

### 3.3 Logs

Read `home-assistant.log` and filter on `custom_components.diagral` and `pydiagral.api`. These lines contain the serial, the alarm name, user names and webhook URLs: never paste them unredacted into an issue, a PR or a commit.

---

## 4. Level 2 — Fake Diagral Cloud (planned)

Not built yet. The design, so it is not rediscovered:

- `pydiagral` builds each request URL from the module global `BASE_URL` at call time (`f"{BASE_URL}/{API_VERSION}/{endpoint}"` in `pydiagral/api.py`). Reassigning `pydiagral.api.BASE_URL` before setup redirects every call — no change to the integration code.
- The redirect is injected from the Home Assistant venv (a `sitecustomize` gated by an environment variable), never from `custom_components/diagral/`.
- A small `aiohttp` server implements the endpoints the integration uses — configuration, system details, status, anomalies, start/stop/presence, group activation, webhook get/register/update/delete, API key creation and deletion — ignores the HMAC headers, keeps state in memory, and stores the registered webhook URL.
- A replay command makes the fake cloud POST a `STATUS`, `ALERT` or `ANOMALY` notification to that URL, with the host rewritten to `localhost:8123`.
- It runs against a **dedicated config entry with a fake serial and fake credentials**, beside the real entry, which stays disabled. If the redirect ever failed, the real API would reject those credentials: the production central cannot be reached by construction.
- The Nabu Casa cloudhook branch cannot be exercised this way; it stays covered by level 1.
- The server and the replay script belong in this skill's directory, not in `custom_components/` — HACS ships that folder to users.

---

## 5. Level 3 — Real Central

### 5.1 Before

1. Get the maintainer's explicit consent **for this session**, naming what will be done: enabling the entry, any arming or disarming, any webhook action. Arming or disarming acts on the real alarm.
2. Agree on the end of the session: who disables the entry, and when.

### 5.2 During

- The maintainer enables the entry (or approves you doing it in the UI).
- Confirm in the log that setup completed and which webhook branch ran.
- Exercise only what was agreed. Prefer observing a real event (the maintainer arms from the Diagral app) to triggering one.

### 5.3 Restore production (mandatory)

1. Disable the development entry. This **deletes** the central's subscription.
2. On the **production** Home Assistant, call the `diagral.register_webhook` action targeting its alarm panel entity. Its log should show `Webhook successfully created for …` and `Webhook successfully registered for …`.
3. Check that production receives an event again — a `STATUS` from an arm/disarm in the Diagral app produces a `DIAGRAL_EVENT` there.
4. Tell the maintainer the restore is done, and what was observed.

Do not consider the session closed until step 3 is confirmed.

---

## 6. Scenarios Worth Replaying

Whichever level runs them:

| # | Scenario | Expected |
|---|---|---|
| 1 | Setup with an external HTTPS URL, no existing subscription | Subscription registered; webhook registered locally |
| 2 | Setup with an existing subscription to another host | Warning logged; subscription updated to this instance |
| 3 | `STATUS` webhook with a user | Coordinator refresh; `changed_by` set to the user name; `DIAGRAL_EVENT` fired |
| 4 | `ALERT` with code 1130, 1139 or 1141 and a group index | Panel `triggered` with a `trigger` attribute; stays triggered through polls until `disarmed` |
| 5 | `ALERT` with another code | `DIAGRAL_EVENT` fired; panel state unchanged |
| 6 | `ANOMALY` webhook | Refresh; `detail.device_label` filled; anomalies sensor updated |
| 7 | Malformed JSON | `Received invalid JSON data from webhook` logged; nothing else |
| 8 | `unregister_webhook` action | Subscription deleted; local webhook unregistered; `webhook_id` cleared |
| 9 | Firmware string changes between polls | Device registry `sw_version` updated |
| 10 | No external URL available | Error logged; setup still completes without a webhook |

Report, in the pull request, the level, the Home Assistant version, the scenarios run and the log lines observed — redacted.
