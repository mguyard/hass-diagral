# Contributing to hass-diagral

Thanks for your interest in the Diagral integration! 💙 Bug reports, feature requests and pull requests are all welcome.

- 🐛 **Report a bug or request a feature** through the [issue templates](https://github.com/mguyard/hass-diagral/issues/new/choose). For a bug, attach the diagnostics file: the [diagnostics guide](https://docs.page/mguyard/hass-diagral/issues/diagnostics) explains how to get it.
- 🔀 **Submit a pull request**: review open PRs, or submit your own following the steps below.

The full repository rules live in [`AGENTS.md`](AGENTS.md). This page is the short version for contributors.

## 🛠️ Set up

Home Assistant requires Python 3.14. Install the `pydiagral` version pinned in [`manifest.json`](custom_components/diagral/manifest.json):

```bash
git clone https://github.com/<your-account>/hass-diagral
cd hass-diagral
python3.14 -m venv .venv && . .venv/bin/activate

pip install homeassistant pydiagral==<pinned version> pytest pytest-asyncio pytest-timeout pytest-mock ruff==0.17.1
```

`ruff` is pinned to the version CI uses.

## 🔀 Workflow

1. **Fork** the repository and clone your fork.
2. **Create a branch** from `dev`, with a descriptive name:
   ```sh
   git checkout -b new-feature-x origin/dev
   ```
3. **Make your changes**, with tests for every change under `custom_components/diagral/`, and update the [documentation](docs/integration/) of what you changed.
4. **Check them locally** — CI runs the same commands, and all of them are required to merge:
   ```sh
   python -m pytest custom_components/diagral/tests/
   ruff check custom_components/diagral
   ruff format --check custom_components/diagral
   ```
5. **Commit** with a signed commit (see below), and push to your fork.
6. **Open a pull request against `dev`**, and fill in the template.

Once reviewed and approved, the PR is merged into `dev`, then promoted to `beta` for a prerelease and to `main` for a stable release.

## 📝 Commits

Commits follow [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/), with a gitmoji after the type, and end with a `Tests:` line:

```
fix(sensor): 🐛 Name an anomaly after a device of its own type

Tests: ✅ 351 passed, ❌ 0 failed, ⚠️ 0 errors
```

| Type | Gitmoji | Released? |
|---|---|---|
| `feat` | ✨ | ✅ minor |
| `fix` | 🐛 | ✅ patch |
| `perf` | ⚡ | ✅ patch |
| `docs` | 📝 | — |
| `refactor` | ♻️ | — |
| `test` | ✅ | — |
| `chore`, `ci` | 🔧 | — |

The scope is the module name without its extension: `sensor`, `webhook`, `config_flow`… Use `Tests: N/A (no custom_components change)` when nothing under `custom_components/` changed. The PR title follows the same format, and a check validates it. The details, including breaking changes, are in `AGENTS.md` → *Commits*.

> [!IMPORTANT]
>
> **Every commit must be signed**: the branches only accept signed commits. See GitHub's guide to [signing commits](https://docs.github.com/en/authentication/managing-commit-signature-verification/signing-commits).

## 🔒 Ground rules

- **Through pydiagral only.** Every call to the Diagral cloud goes through [pydiagral](https://github.com/mguyard/pydiagral). When it is wrong or missing something, fix it there rather than working around it here.
- **No real Diagral call in tests.** Tests mock pydiagral and never touch the Diagral cloud.
- **No personal data.** No credential, serial number, alarm name, e-mail address or webhook URL in code, fixtures, logs, commits, issues or PRs. Fixtures are synthetic, and a diagnostics file or a log pasted in an issue must be redacted.
- **Never rename an entity `key`.** It is part of the entity's unique id: renaming it orphans the users' entities.
- **Translate everything.** Every new string goes into both `translations/en.json` and `translations/fr.json`.

## 🤖 Contributing with an AI assistant

AI coding assistants are welcome, under the same rules as everyone else. Point yours at [`AGENTS.md`](AGENTS.md): it holds the repository rules, in the `AGENTS.md` format that many agents read automatically. Claude Code reads it through [`CLAUDE.md`](CLAUDE.md).

You stay the author of what you submit: read and understand every line before opening the PR, and say in its description when an assistant helped.

## 📄 License

By contributing, you agree that your contributions are distributed under the [GPL-v3 License](LICENSE) of the project.
