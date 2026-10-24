# Agent Instructions — hass-diagral

Repository rules for AI coding agents. This file is the source of truth; `CLAUDE.md` imports it and adds only what is specific to Claude Code.

## Precedence

`.claude/rules/` is vendored from the ECC plugin (2.2.3) and kept byte-identical to upstream, so it can be refreshed without merge work.
It is generic advice, written for no repository in particular.
**Where it disagrees with this file, this file wins.**

The known divergences, so they do not have to be rediscovered:

| An ECC rule says | This repository does |
|---|---|
| Format with `black`, sort imports with `isort` | `ruff format` only — `lint.yaml` runs `ruff format --check`. Imports are sorted by ruff's isort with `force-sort-within-sections` and `known-first-party = ["homeassistant"]`, the Home Assistant core layout, which isort does not reproduce by default. |
| Prefer `@dataclass(frozen=True)`, never mutate | `DiagralData` is mutable by design: it is Home Assistant's `runtime_data`, and `webhook_id` is reassigned when the webhook is registered or unregistered. Entity descriptions, on the other hand, are frozen. |
| `pytest --cov=src`, `@pytest.mark.unit` / `.integration` | There is no `src/` — see Commands below. No marker is registered in `pyproject.toml`, so those two raise `PytestUnknownMarkWarning`. Tests are grouped in `Test*` classes. |
| Load secrets from `.env` with `python-dotenv`, scan with `bandit` | Credentials are entered in the config flow and stored in the config entry; there is no `.env`. Security scanning is CodeQL, weekly. |
| Anything about FastAPI | `rules/ecc/python/fastapi.md` matches no file here — its globs resolve to nothing. |

## Project

Custom [Home Assistant](https://www.home-assistant.io/) integration for Diagral alarm systems: alarm control panel, sensors, webhook push updates, config flow, diagnostics. HACS-compatible, `iot_class: cloud_polling`, `quality_scale: bronze`.

- All code, comments, docstrings and commit messages in **English**.
- Every call to the Diagral cloud goes through [`pydiagral`](https://github.com/mguyard/pydiagral), pinned in `manifest.json`. **Never call the Diagral API directly.** `pydiagral` is maintained by the same author: when it is wrong or missing something, fix it there rather than working around it here.
- Check the [pydiagral documentation](https://mguyard.github.io/pydiagral/) or Context7 before using any `pydiagral` class, method or model. Do not assume its API from memory.
- Use [developers.home-assistant.io](https://developers.home-assistant.io) and Context7 for Home Assistant API guidance.

## Module map

```
custom_components/diagral/
├── __init__.py             # Entry setup/teardown, migration, webhook register/unregister, DiagralConfigEntry
├── alarm_control_panel.py  # Alarm panel entity + entity services (arm/disarm groups, (un)register webhook)
├── config_flow.py          # 3-step config flow, reconfigure flow, options flow (CONFIG_VERSION=2.1)
├── const.py                # DOMAIN, config keys, service names, DEFAULT_SCAN_INTERVAL
├── coordinator.py          # DiagralDataUpdateCoordinator — polls every 300 s, keeps sw_version in sync
├── diagnostics.py          # Diagnostics endpoint, TO_REDACT
├── entity.py               # DiagralEntity(CoordinatorEntity)
├── icons.json              # Service icons
├── manifest.json           # pydiagral pin, version (managed by semantic-release)
├── models.py               # DiagralData, DiagralConfigData, DiagralOptionsData, AccountInfoData…
├── pyproject.toml          # pytest configuration
├── quality_scale.yaml      # Declared rule statuses — see the ha-quality-scale-verify skill
├── sensor.py               # anomalies and active_groups sensors
├── services.yaml           # Service definitions
├── tests/                  # pytest suite (see below)
├── translations/           # en.json, fr.json
└── webhook.py              # Incoming webhook: refresh, enrich, dispatcher signal, DIAGRAL_EVENT
```

## Invariants

- Use `DiagralConfigEntry` from `__init__.py`, never a raw `ConfigEntry`. It is `ConfigEntry[DiagralData]`.
- Reach runtime state through `entry.runtime_data.coordinator`, `.api`, `.config`, `.webhook_id`.
- `coordinator.data` is a **dict** with five keys: `alarm_config` (`AlarmConfiguration`), `devices_infos` (`DeviceList`), `groups` (`list[Group]`), `system_status` (`SystemStatus`), `anomalies` (`Anomalies`).
- Entities extend `DiagralEntity`, which sets `_attr_has_entity_name = True` and provides `device_info`.
- `unique_id` is `f"{entry_id}_{DOMAIN}_{central_serial}_{description.key}"`; the alarm panel uses the suffix `alarm_control_panel`. **Never rename an existing `key`** — it is part of the unique id, and renaming it orphans the user's entity. `translation_key` may differ from `key` (the `anomalies` sensor uses `alarm_anomalies`).
- Every entity needs a `translation_key`, present in **both** `translations/en.json` and `translations/fr.json`. The same holds for services, config and options strings.
- Every new entity needs a row in `docs/integration/entities.mdx`.
- Constants live in `const.py`. No magic strings or numbers inline.
- `homeassistant.components.cloud` is imported **inside** `register_webhook` / `unregister_webhook`, deliberately: importing it at module level pulls in dependencies the test environment does not have. Keep the `# noqa: PLC0415`.
- Webhook signals are `signal-diagral-webhook-<TYPE>` (dispatcher) and `DIAGRAL_EVENT` (bus). Both are public contracts used in user automations — see `docs/integration/events.mdx`.
- `_LOGGER = logging.getLogger(__name__)`. Never `print()`.
- All I/O is `async`/`await`. No blocking calls in async context.
- Never log, publish or expose a secret: username, password, PIN code, API key, secret key, webhook id or webhook URL. `diagnostics.py` redacts them through `TO_REDACT`; extend it whenever a new secret enters the payload.

## Commands

```bash
# Lint and format — ruff, configured in custom_components/diagral/pyproject.toml
ruff check custom_components/diagral
ruff format --check custom_components/diagral

# Tests — anywhere homeassistant and the pinned pydiagral are importable.
# pyproject.toml sets pythonpath = ["../.."], so no PYTHONPATH is needed.
python -m pytest custom_components/diagral/tests/ -v
```

CI pins `ruff==0.16.1`; a newer release must not be able to turn a green PR red on its own. Line length is 88, and `E501` is deliberately ignored — formatting is the formatter's job, not the linter's. The two deferred `homeassistant.components.cloud` imports keep a targeted `# noqa: PLC0415` rather than a project-wide ignore.

Every test needs Home Assistant **and** `pydiagral`, including `test_const.py`: pytest imports the package `__init__.py` before `conftest.py`. See the `testing-hass-diagral` skill for the environments.

There is no Makefile and no `requirements_test.txt`.

## Python 3.14

Home Assistant requires Python 3.14 since 2026.3, and CI tests on 3.14 only. Do not suggest workarounds for older versions, and do not flag 3.14-only syntax.

- `except ValueError, TypeError:` without parentheses is valid (PEP 758) and is what `ruff format` produces here.
- Annotations are evaluated lazily (PEP 649). Forward references need no quotes.

## CI

| Workflow | Trigger | Purpose |
|---|---|---|
| `tests.yaml` | push / PR on `dev`, paths `custom_components/diagral/**`; weekly; manual | pytest on HA stable + beta (when newer), Python 3.14, coverage to Codecov |
| `lint.yaml` | push / PR on `dev`, same paths; manual | `ruff check` + `ruff format --check` |
| `home-assistant.yaml` | push / PR on `main`, `beta`; daily; manual | hassfest + HACS validation |
| `semantic-prs.yml` | PR opened / edited / synchronized | validates the PR title against Conventional Commits |
| `release.yaml` | push on `main`, `beta` | semantic-release |
| `codeql.yaml` | weekly (Saturday), manual | CodeQL Python security scan |
| `labelers.yml` | push on `main`, manual | issue and PR labels |
| `lock-stale.yml` | daily | locks and marks stale issues |

`tests.yaml` and `lint.yaml` are path-filtered: a change outside `custom_components/diagral/**` does not run them. hassfest does not run on `dev` — a broken `manifest.json` or translation file is only caught when it reaches `beta`.

## Branches

| Branch | Role |
|---|---|
| `dev` | Development. **All PRs target this branch.** |
| `beta` | Prereleases, published by semantic-release |
| `main` | Stable releases, published by semantic-release. Repository default. |

Never commit or push directly to `beta` or `main` — semantic-release owns them. Always confirm the current branch with `git branch --show-current` before committing.

Dependabot **security** PRs always target `main`, the default branch: `target-branch: dev` in `dependabot.yml` only applies to version updates. Never merge one into `main`. Carry its change to a branch cut from `dev`, open the PR there, and close the Dependabot PR with a link — see the `git-conventions` skill.

Because `main` is the default branch, a `Closes #N` keyword only fires when the change reaches `main`, not when a PR merges into `dev`. Issues therefore stay open through the beta cycle by design.

## Commits

```
<type>[optional scope]: <gitmoji> <description>

[optional body — bullet points]

Tests: ✅ N passed, ❌ 0 failed, ⚠️ 0 errors
```

- First line in English, 72 characters maximum. Use backticks for code references.
- Types and gitmoji: `feat` ✨, `fix` 🐛, `docs` 📝, `refactor` ♻️, `test` ✅, `chore` 🔧, `perf` ⚡, `ci` 🔧. `semantic-prs.yml` accepts `feat|fix|docs|test|ci|refactor|perf|chore`.
- Scope is the module filename without extension: `sensor`, `coordinator`, `alarm_control_panel`, `config_flow`, `webhook`, `translations`, `deps`, `tests`…
- The `Tests:` line is required whenever `custom_components/` changed. Use `Tests: N/A (no custom_components change)` otherwise.
- The body explains **why**. Never restate what the diff already shows.

The pre-commit test gate, the pull request description template and the prepare-PR workflow live in the `git-conventions` skill.

`release.config.cjs` uses semantic-release's default (Angular) presets: only `feat`, `fix` and `perf` — plus reverts and breaking changes — appear in the changelog and trigger a release. A `docs`, `refactor` or `chore` commit is invisible to users — a change they must know about needs a rendered type.

The changelog credits contributors: an author other than the maintainer appears as `(by …)`, and each `Co-authored-by:` trailer as `(co-authored by …)` — a GitHub login when the address is a noreply one, the name otherwise, never an e-mail address, and never an assistant or a bot. When carrying over someone else's work, add `Co-authored-by: Name <id+login@users.noreply.github.com>` so they are credited. The toolchain is pinned in `.github/release/` and updated by Dependabot; dry-run an upgrade before merging it, since a release only runs on `beta` and `main`.

## Pull requests

- Title follows the commit format; `semantic-prs.yml` enforces it.
- Target `dev`, always.
- Run the full suite and `ruff` before opening. Fix everything first.
- Describe what changed and why, and how it was verified.

## Testing

- Tests live in `custom_components/diagral/tests/`, inside the integration folder so that a Home Assistant instance which mounts only that folder still sees them.
- `asyncio_mode = "auto"`: async tests need no `@pytest.mark.asyncio`.
- Never make a real call to the Diagral cloud. Mock at the `pydiagral` boundary.
- **After every change to `custom_components/diagral/*.py`**, review `tests/test_<module>.py` and create, update or delete tests accordingly. Never skip this.
- Write the failing test first, confirm it fails for the right reason, then fix. A test that passes against unfixed code proves nothing — check it is load-bearing.
- Prefer `pytest.mark.parametrize` with named `ids` over duplicated bodies. Avoid branching inside tests.

## Validation against a running Home Assistant

**The maintainer's production Home Assistant uses the same Diagral central.** The central holds a single webhook subscription. An entry no longer overwrites or deletes a subscription it does not own — it raises a repair issue instead — but the take-over repair, the `register_webhook` action and older versions of the integration still re-point it, and production then silently stops receiving events.

Never enable a config entry backed by real Diagral credentials, never call an arming action, and never register or unregister a webhook against the real central without the maintainer's explicit consent for that specific run. The `live-validation-hass-diagral` skill describes the safe levels, and the restore procedure when the real central is used.

## Documentation

Whenever a feature, entity, service, event or behaviour is added or changed, check `docs/integration/` for pages that cover it and update them in the same change. Match the existing tone, structure and MDX components — do not introduce new formatting patterns. When unsure whether a change warrants a docs update, ask.

## Comments

Explain why, never what. One short line stating a non-obvious constraint, or no comment at all. Do not restate the following line, do not justify a change by describing what the code looked like before, and do not add section dividers — they go stale and mislead.
