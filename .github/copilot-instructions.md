# GitHub Copilot Custom Instructions for `hass-diagral`

## Project Context

- **Project Type:** Custom integration for [Home Assistant](https://www.home-assistant.io/), written in Python.
- **Purpose:** Connects Home Assistant to the Diagral alarm system — alarm states, sensors, diagnostics, config flow.
- **Language:** All code, comments, and docstrings must be in **English**.
- **External dependency:** `pydiagral` (pinned in `manifest.json`) — all Diagral API calls go through this library exclusively.

## Architecture

```
custom_components/diagral/
├── __init__.py          # Integration setup/teardown, webhook registration, DiagralConfigEntry alias
├── coordinator.py       # DiagralDataUpdateCoordinator (polls every 300 s)
├── models.py            # DiagralData, DiagralConfigData, DiagralOptionsData
├── const.py             # All constants (DOMAIN, services, default values)
├── config_flow.py       # UI config flow + options flow
├── entity.py            # Base entity class (DiagralEntity)
├── alarm_control_panel.py  # AlarmControlPanel platform
├── sensor.py            # Sensor platform
├── webhook.py           # Webhook handler (Nabu Casa + direct HA webhook)
├── diagnostics.py       # HA diagnostics endpoint
├── services.yaml        # Custom service definitions
├── manifest.json        # Integration metadata (pydiagral pinned)
└── translations/        # en.json, fr.json
```

**Key patterns:**
- `DiagralConfigEntry = ConfigEntry[DiagralData]` — always use this alias instead of raw `ConfigEntry`.
- Coordinator data keys: `alarm_config`, `devices_infos`, `groups`, `system_status`, `anomalies`.
- Webhook supports **Nabu Casa cloud** (`.nabu.casa`) and direct HA webhook.

## Quick Start — Key Commands

```bash
# Lint
flake8 --max-line-length=150 custom_components/diagral/

# Tests — see .github/skills/testing-hass-diagral/SKILL.md for full environment detection
test -d /workspaces && echo "inside devcontainer" || echo "outside"
# Inside:  cd /workspaces/home-assistant-dev/config/custom_components/diagral && pytest tests/ -v
# Outside: docker ps  →  docker exec -w /workspaces/home-assistant-dev/config/custom_components/diagral <ID> pytest tests/ -v
```

> No Makefile. `pyproject.toml` at `custom_components/diagral/pyproject.toml` configures pytest.

## CI/CD

| Workflow | Trigger | Purpose |
|----------|---------|---------|
| `home-assistant.yaml` | push / PR | `hassfest` + HACS validation |
| `release.yaml` | tag push | `semantic-release` |
| `codeql.yaml` | weekly + push | CodeQL Python security scan |
| `devsec.yaml` | `dev` branch / PR to `dev` | FortiDevSec SAST scan |

**Branch strategy:** `dev` → integration/development. `main` → stable releases. All PRs target `dev`.

## Mandatory Rules for Copilot Coding Agent

- All code, comments, and docstrings in **English**.
- **After every `custom_components/diagral/*.py` change**, analyse `tests/test_<module>.py` and CREATE, UPDATE, or DELETE tests as needed. Never skip this step.
- **Flake8 max line length: 150 characters.**
- New entities: follow `python-homeassistant/SKILL.md §5`. Add row to `docs/integration/entities.mdx`.
- Commit/PR: follow `python-homeassistant/SKILL.md` §7. PR target branch is always `dev`.
- Use `async`/`await` for all I/O. Use `_LOGGER = logging.getLogger(__name__)`, never `print()`.
- Use `context7` and [developers.home-assistant.io](https://developers.home-assistant.io) for HA API guidance.
- Use `context7` or [mguyard.github.io/pydiagral](https://mguyard.github.io/pydiagral/) for pydiagral API guidance — always check before using any pydiagral class or model.
- **Every question asked to the user MUST use `vscode_askQuestions`.** Never ask questions inline as plain text only. Always set `allowFreeformInput: true` (or leave it at its default) so the user can provide a custom answer alongside the proposed options.
