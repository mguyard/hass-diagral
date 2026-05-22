---
last_updated: 2026-03-10
purpose: "Durable project decisions and invariants. Template file for downstream projects."
---

# Project Decisions

## How to Use

- Add entries only when a decision is durable and likely to matter in future sessions.
- Prefer linking to code/paths and stating invariants/constraints over narrative.
- If a decision is superseded, append an "Update" note to the original entry.
- Keep runtime scratch notes out of this file.
- Separate verified repo facts from assumptions or interpretations.

## Entry Template

```md
## <Decision Title> — YYYY-MM-DD

### Facts
- Verified repo facts with file/path references.

### Inferences
- Assumptions or interpretations that still need validation.

### Decision
- The durable rule, invariant, or operating choice.

### Consequences
- What this changes, constrains, or requires going forward.
```

## Onboarding Snapshot Template

Use this after project familiarization / onboarding runs:

```md
## Onboarding Snapshot — YYYY-MM-DD

### Facts
- Major modules / packages
- Run / build / test commands
- Key conventions and invariants
- Top risks or TODOs worth remembering

### Inferences
- Only if necessary, clearly marked
```

## Entries

## Onboarding Snapshot — 2026-04-04

### Facts

**Project identity**
- Custom Home Assistant integration for Diagral alarm system
- HACS-compatible, quality_scale: bronze, version: 1.3.0
- Repo: `mguyard/hass-diagral`, default branch: `main`, dev branch: `dev`
- All PRs target `dev`

**Module map**
- `__init__.py` — entry setup/teardown, webhook registration, `DiagralConfigEntry` alias
- `coordinator.py` — `DiagralDataUpdateCoordinator`, polled every 300 s
- `models.py` — `DiagralData`, `DiagralConfigData`, `DiagralOptionsData`
- `const.py` — `DOMAIN`, service names, config keys, `HA_CLOUD_DOMAIN`
- `config_flow.py` — UI config flow + options flow (CONFIG_VERSION=2)
- `entity.py` — `DiagralEntity(CoordinatorEntity)`, `_attr_has_entity_name = True`
- `alarm_control_panel.py` — AlarmControlPanel platform with group arming services
- `sensor.py` — Sensor platform (anomalies, active_groups entities)
- `webhook.py` — Webhook handler supporting Nabu Casa and direct HA endpoints
- `diagnostics.py` — HA diagnostics endpoint
- `translations/en.json`, `translations/fr.json` — all entity human names

**External dependency**
- `pydiagral` (pinned in `manifest.json`) — all Diagral API calls go through this library exclusively
- Direct Diagral API calls are FORBIDDEN

**Coordinator data keys**
- `alarm_config` (AlarmConfiguration), `devices_infos` (DeviceInfos), `groups` (list[Group])
- `system_status` (SystemStatus), `anomalies` (Anomalies)

**Key invariants**
- Always use `DiagralConfigEntry` (not raw `ConfigEntry`)
- `unique_id` pattern: `{entry_id}_{DOMAIN}_{alarm_config.alarm.central.serial}_{description.key}`
- Translation keys must be added to both `en.json` AND `fr.json`
- Every new entity needs a row in `docs/integration/entities.mdx`

**Run/build/test commands**
- Lint: `flake8 --max-line-length=150 custom_components/diagral/`
- Tests inside devcontainer: `cd /workspaces/home-assistant-dev/config/custom_components/diagral && pytest tests/ -v`
- Tests outside devcontainer: `docker ps` → `docker exec -w /workspaces/home-assistant-dev/config/custom_components/diagral <ID> pytest tests/ -v`
- Detect environment: `test -d /workspaces && echo inside || echo outside`
- Tests live at `custom_components/diagral/tests/` (devcontainer-mounted path)

**CI/CD**
- `home-assistant.yaml`: hassfest + HACS validation (push/PR)
- `release.yaml`: semantic-release on tag push
- `codeql.yaml`: weekly CodeQL Python security scan
- `devsec.yaml`: FortiDevSec SAST on `dev` branch

**Commit convention**
- Format: `<type>[scope]: <gitmoji> <description>` — see `python-homeassistant/SKILL.md` §7
- Types: feat ✨, fix 🐛, docs 📝, refactor ♻️, test ✅, chore 🔧

**Agent/skills structure**
- Skills in `.github/skills/` — only Python/HA-relevant skills kept
- Domain skill: `python-homeassistant/SKILL.md`
- Universal skills: code-quality, testing-qa, security-best-practices, review-core, review-orchestration, multi-model-review, planning-structure, research-discovery, memory-management, git-worktree, api-design

### Inferences
- None at this time

### memory_meta
- timestamp: 2026-04-04
- author: GitHub Copilot (onboarding scan)
