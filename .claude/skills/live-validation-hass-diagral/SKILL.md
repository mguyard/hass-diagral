---
name: live-validation-hass-diagral
description: Proving a hass-diagral change works on a running Home Assistant without breaking the production instance that shares the same Diagral central — the three validation levels, the shared-central constraint, driving Home Assistant over REST, and the restore procedure after a real-central session.
---

# Live Validation — hass-diagral

Unit tests prove the logic of a function. They cannot prove that the webhook round trip works, that a state survives a real poll after a webhook, or that the device registry is updated — that needs a running Home Assistant. This skill describes how to get there **without touching the production central** unless the maintainer explicitly decides to.

---

## 1. The Constraint: One Central, One Webhook

The maintainer's production Home Assistant uses the **same Diagral central** as the development instance. The central holds a **single** webhook subscription:

- Since webhook ownership is tracked, setting up the integration on another instance leaves a subscription it does not own untouched and raises a repair issue instead; unloading only deletes a subscription the entry owns.
- The **take-over** repair, the `register_webhook` action, and any version of the integration older than ownership tracking still **re-point** the subscription. Production then stops receiving events, silently, until it takes it back.

Restarting Home Assistant does not unload entries, so a dev instance that took the subscription over keeps it until production takes it back.

The development config entry backed by the real credentials therefore stays **disabled**. Enabling it is a decision the maintainer takes for a specific session — never on your own.

---

## 2. Choosing a Level

| Level | What it proves | Touches the real central | When |
|---|---|---|---|
| 1 — pytest with mocks | Logic of each function | No | Always (`testing-hass-diagral`) |
| 2 — Fake Diagral cloud | Full runtime: config flow, setup, polling, webhook register / receive / unregister, events, entity states | No | Any change to runtime behaviour — see §4 |
| 3 — Real central | Behaviour of the real Diagral API and real hardware | **Yes** | Rarely, with explicit consent: before a significant release, a `pydiagral` bump, or when the real API's behaviour is in question |

A runtime change is validated by levels 1 and 2; level 3 only if the maintainer asks for it. State in the pull request which level was used.

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

## 4. Level 2 — Fake Diagral Cloud

Everything lives in `fake_cloud/` next to this file — never in `custom_components/`, which HACS ships to users.

| File | Role |
|---|---|
| `server.py` | `aiohttp` fake of the Diagral API that pydiagral calls, in-memory state, `/_control` endpoints, every exchange logged |
| `Dockerfile` | Image `diagral-fake-cloud` running `server.py` on port 8099 |
| `diagral_fake_cloud_redirect.py` | Imported at Python startup through a one-line `.pth`; while the marker file exists it reassigns `pydiagral.api.BASE_URL` and logs `DIAGRAL FAKE CLOUD ACTIVE` each time a `DiagralAPI` is created |
| `fake_cloud.sh` | `up`, `down`, `status`, `logs` |
| `smoke.py` | Runs the real pydiagral against the fake, method by method |

### 4.1 How the redirect works

pydiagral builds each URL from the module global `BASE_URL` at call time (`f"{BASE_URL}/{API_VERSION}/{endpoint}"`). Reassigning `pydiagral.api.BASE_URL` redirects every call; patching `pydiagral.constants.BASE_URL` does not. No file of pydiagral or of the integration is modified.

The redirect only acts while `config/.diagral_fake_cloud` exists; the file holds the fake cloud's URL as seen from the Home Assistant container (`http://host.docker.internal:8099`). The `.pth` and the module live in the Home Assistant venv of the container, so a container rebuild removes them.

### 4.2 Session

1. `fake_cloud.sh up` — builds and starts the container, installs the redirect, writes the marker, then prints `status`. All three lines — container running, redirect installed, marker present — must show before Home Assistant is restarted. Never pipe `up` through `head` or anything that closes early: the script stops at the first broken write, and once left the redirect installed without its marker, so the fake entry called the real cloud. The fake credentials were refused, as designed, but check anyway.
2. Ask the human to restart Home Assistant. The `DIAGRAL FAKE CLOUD ACTIVE` warning only appears once a `DiagralAPI` is created, so before trusting it, check that the Home Assistant process started after the marker was written, then enable the fake entry and confirm the fake cloud receives its first requests (`GET /_control/state` lists the system) within seconds — disable the entry at once if it does not.
3. If no fake entry exists yet, create one through the config flow over REST — it exercises the whole flow:

   ```
   POST /api/config/config_entries/flow               {"handler": "diagral"}
   POST /api/config/config_entries/flow/<flow_id>     {"serial_id": "FAKECENTRAL01"}
   POST /api/config/config_entries/flow/<flow_id>     {"username": "fake@example.com", "password": "fake-password", "pin_code": "1234"}
   POST /api/config/config_entries/flow/<flow_id>     {"alarmpanel_options": {"alarmpanel_actiontype_code": "never"}}
   ```

   The fake accepts only these credentials (overridable with `FAKE_USERNAME`, `FAKE_PASSWORD`, `FAKE_PIN_CODE`), which also lets the config flow's error paths be tested. The entry is persisted, so later sessions re-enable it instead of creating another (websocket `config_entries/disable` with `"disabled_by": null`).
4. Drive scenarios through the control endpoints (§4.3) and read the result on Home Assistant (§3).
5. Disable the fake entry while the fake cloud is still up — websocket `config_entries/disable` with `"disabled_by": "user"`. It unloads cleanly and deletes its subscription. Left enabled, it would send its fake credentials to the real Diagral cloud at the next start and retry forever.
6. `fake_cloud.sh down`, then ask the human to restart Home Assistant. Do not leave the redirect in place at the end of a session.

Identify the fake entry by `FAKECENTRAL01` in its title, and print only states: the real entry's title is the maintainer's alarm name.

`docker logs -f diagral-fake-cloud` (or `fake_cloud.sh logs`) shows every exchange: `IN` for calls from Home Assistant, `OUT` for webhooks pushed to it, `CTL` for control calls. Credentials are redacted; all data is synthetic.

### 4.3 Control endpoints

All on `http://localhost:8099`, JSON bodies. `serial` may be omitted when only one system is known.

| Endpoint | Body | Effect |
|---|---|---|
| `GET /_control/state` | — | Systems, statuses, issued keys, anomalies, registered webhook |
| `POST /_control/reset` | — | Forget every system and token |
| `POST /_control/status` | `{"status": "GROUP", "activated_groups": [1, 2]}` | What the next poll returns (`OFF`, `GROUP`, `TEMPO_GROUP`, `PRESENCE`) |
| `POST /_control/anomalies` | `{"anomalies": {"sensors": [{"serial": "…", "index": 1, "group": 1, "label": "…", "anomaly_names": [{"id": 1, "name": "Low battery"}]}]}}` or `{"clear": true}` | What `get_anomalies` returns |
| `POST /_control/webhook` | `{"webhook_url": "https://other.example.net/api/webhook/x"}` or `{"clear": true}` | Sets the subscription as another installation would — to test ownership — or removes it |
| `POST /_control/fail` | `{"path": "/status", "status": 503, "count": 2}`, `{"delay": 40}` or `{"clear": true}` | Fails (HTTP `status`) and/or delays (`delay` seconds) the next `count` API requests whose path contains `path` (default `/v1/`) — to test retries and availability |
| `POST /_control/delay` | `{"seconds": 20, "groups_listed": false}` | Exit delay, as on a real central (about 4 min in production): `start` and `activate_group` report `TEMPO_GROUP` (groups listed or not) for `seconds`, then `GROUP`, and a `STATUS` notification is pushed to Home Assistant. `0` turns it off |
| `POST /_control/notify` | `{"type": "STATUS" \| "ALERT" \| "ANOMALY", "alarm_code": "1130", "group_index": "01", "detail": {…}, "user": {…}}` | POSTs a notification to the webhook Home Assistant registered, host rewritten to `HA_URL`; `"raw": {…}` sends a payload as is |

pydiagral derives `alarm_type` from `alarm_code`, so the code decides how the notification is handled — 1130, 1139, 1141 are intrusions; 3401 an arming; 1384 a low battery.

Polling goes through the coordinator's debouncer: after `homeassistant.update_entity`, allow ten seconds before reading a state that depends on a second refresh.

### 4.4 Limits

- The Nabu Casa cloudhook branch cannot be exercised; it stays covered by level 1.
- State is in memory and lost when the container is rebuilt. A config entry keeps the API key it was given, so the fake adopts any unknown key with its own `FAKEAK` prefix, and logs it; any other key is refused.
- `server.py` implements what pydiagral 1.6.0 calls. After a pydiagral bump, run `smoke.py` with the new version before trusting the fake.
- An existing **disabled** diagral entry is a realistic condition, not noise: keep the real entry disabled beside the fake one.

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
