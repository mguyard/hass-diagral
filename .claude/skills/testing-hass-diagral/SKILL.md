---
name: testing-hass-diagral
description: Project-specific test setup for hass-diagral — directory structure, running pytest in the Home Assistant devcontainer or a plain virtualenv, the pydiagral prerequisite, shared fixtures, mocking strategy, and the mandatory test impact analysis.
---

# Testing — hass-diagral Project Setup

Use this skill for any task that requires running, writing, or understanding tests in the `custom_components/diagral/` codebase.

---

## 1. Directory Structure

Tests live **inside** the integration folder, so that a Home Assistant instance mounting only `custom_components/diagral/` still sees them:

```
custom_components/diagral/
├── pyproject.toml                    # pytest config (asyncio_mode=auto, pythonpath=["../.."])
└── tests/
    ├── __init__.py
    ├── conftest.py                   # Shared fixtures
    ├── test_alarm_control_panel.py   # state mapping, code requirement, code validation
    ├── test_config_flow_validation.py# e-mail / PIN / panel code validators
    ├── test_const.py                 # constant values
    ├── test_sensor.py                # anomalies and active_groups computation
    └── test_webhook.py               # enrich_data_alert_anomaly
```

Not covered yet: `__init__.py` (setup, migration, webhook register/unregister, entry removal), `coordinator.py`, `diagnostics.py`, the config flow steps themselves, and `webhook.handle_webhook` / `publish_event`.

---

## 2. Every Test Needs Home Assistant and pydiagral

Because `tests/` sits inside the package, pytest imports `custom_components/diagral/__init__.py` — which imports `homeassistant` and `pydiagral` — before it can load `conftest.py`. This applies to `test_const.py` too: the `importlib` loading it uses does not avoid the package import. There is no test that runs without both installed.

`pydiagral` must be the version pinned in `manifest.json`:

```bash
python -c "import json; print(*json.load(open('custom_components/diagral/manifest.json'))['requirements'])"
```

---

## 3. Running Tests

`pyproject.toml` sets `pythonpath = ["../.."]`, and pytest picks it up as the rootdir config, so no `PYTHONPATH` is needed from either location below.

### Inside the maintainer's Home Assistant devcontainer

The devcontainer bind-mounts this repository's `custom_components/diagral` into its `config/`. Resolve the container by image, never by a hard-coded id:

```bash
C=$(docker ps --format '{{.ID}} {{.Image}}' | awk '/vsc-home-assistant-dev/ {print $1}')
docker exec -w /workspaces/home-assistant-dev/config $C \
  /home/vscode/.local/ha-venv/bin/python -m pytest custom_components/diagral/tests/ -v
```

**`pydiagral` is missing in a devcontainer where the diagral integration has never been started** — Home Assistant installs requirements only when it loads the integration, and the maintainer keeps that entry disabled (see `live-validation-hass-diagral`). The symptom is `ModuleNotFoundError: No module named 'pydiagral'` while loading `conftest.py`. Install the pinned version into the HA venv:

```bash
docker exec $C /home/vscode/.local/ha-venv/bin/uv pip install --python /home/vscode/.local/ha-venv/bin/python pydiagral==<pin>
```

This tests against the Home Assistant **dev** branch checked out in the devcontainer.

### Standalone virtualenv — what CI does

```bash
python3.14 -m venv .venv && . .venv/bin/activate
pip install homeassistant pydiagral==<pin> pytest pytest-asyncio pytest-timeout pytest-mock

# from the repository root
python -m pytest custom_components/diagral/tests/ -v
```

`tests.yaml` does the equivalent against the latest Home Assistant stable, and against the beta when one is newer. A fix can pass on one and fail on the other: the devcontainer (dev branch) plus a virtualenv (stable) covers both ends.

> **This section is the canonical source for running tests.** `git-conventions` §2 refers to it — do not duplicate the commands elsewhere.

---

## 4. Dependencies and pytest Configuration

`homeassistant` is an ordinary pip package. **`pytest-homeassistant-custom-component` is not used.** There is no `requirements_test.txt`; CI installs `pytest pytest-asyncio pytest-cov pytest-timeout pytest-mock pytest-html aiohttp aiofiles` inline, then the requirements from `manifest.json`.

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
pythonpath = ["../.."]
testpaths = ["tests"]
filterwarnings = [...]
```

`asyncio_mode = "auto"`: no `@pytest.mark.asyncio` on async tests.

---

## 5. Shared Fixtures (`conftest.py`)

| Fixture | Provides |
|---|---|
| `mock_hass` | `MagicMock(spec=HomeAssistant)` |
| `alarm_config_mock` | `AlarmConfiguration` mock with `alarm.central.serial = "SERIAL123"` |
| `system_status_mock` | `SystemStatus` mock with `status = "off"` |
| `coordinator_mock` | Coordinator mock whose `data` dict holds the five keys |
| `diagral_config` | `DiagralConfigData` mock with `alarmpanel_options` set to `never` / no code |

Entity logic is tested by building the entity with `object.__new__(...)` and setting only the attributes the method under test reads — see `make_sensor_mock` and `make_panel_mock`.

---

## 6. Mocking Strategy

- **Never make a real call to the Diagral cloud.** Mock at the `pydiagral` boundary: `AsyncMock` for `DiagralAPI` methods, real `pydiagral.models` instances for data.
- Prefer real `pydiagral.models` objects (`Anomalies`, `AnomalyDetail`, `DeviceList`, `WebHookNotification`…) over `MagicMock` when the code iterates them. `vars(MagicMock())` yields non-iterable sentinels and raises `TypeError` — use `DeviceList(cameras=[], commands=[], sensors=[], sirens=[], transmitters=[])`.
- Patch module-level utilities where they are used: `patch("custom_components.diagral.sensor.dt_util")`.
- `homeassistant.components.cloud` is imported lazily inside `register_webhook` / `unregister_webhook`; patch it at `homeassistant.components.cloud.<name>` when testing those functions.
- Webhook payloads in tests are synthetic. Never paste a captured real payload without replacing the serial, user names and URLs.

---

## 7. Test Impact Analysis (Mandatory)

Every time a file in `custom_components/diagral/*.py` is created or modified, before finishing the task:

1. **Identify** the matching `tests/test_<module>.py`
2. **Read** its existing tests
3. **For each function or class added, changed, or removed**, decide:
   - `CREATE` — new behaviour needs a test
   - `UPDATE` — an existing test no longer reflects the logic
   - `DELETE` — the code is gone and the test is dead
4. **Apply** the changes — never skip silently
5. **Run** the suite (§3)

If the module has no test file yet, create it.

---

## 8. Ruff Gate

`lint.yaml` runs both commands on every push and PR touching `custom_components/diagral/**`. Run them before committing, with the version CI pins:

```bash
pip install ruff==0.16.1
ruff check custom_components/diagral
ruff format --check custom_components/diagral
```

`ruff format` may rewrite `except (A, B):` into `except A, B:` — that is PEP 758, valid on Python 3.14. Accept it.

---

## 9. Test Rules and Naming

- Per entity: `unique_id` format, state value, `exists_fn` if defined, the missing-data path
- Happy path and error path (`DiagralAPIError`, missing coordinator keys, malformed webhook payload)
- Group related cases in a `Test<Subject>` class; name methods `test_<condition>_<expected>` — e.g. `test_status_presence_returns_armed_home`
- Prefer `pytest.mark.parametrize` with `ids` over near-identical methods
