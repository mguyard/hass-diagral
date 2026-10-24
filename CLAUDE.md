# CLAUDE.md

@AGENTS.md

The file above holds every repository rule and is shared with other agents. What follows applies to Claude Code only.

## Tooling

- **`gh` is installed and is the way to reach GitHub** — issues, PRs, comments, checks, API calls. There is no MCP GitHub server configured here.
- Use `AskUserQuestion` when a decision is genuinely the user's to make. Do not ask about choices that have an obvious default or facts the repository can answer.
- Context7 is available for library documentation. Prefer it over web search for Home Assistant, pydiagral, aiohttp or voluptuous APIs.

## Skills

Project skills live in `.claude/skills/` and load on demand:

| Skill | Load it for |
|---|---|
| `ha-integration-knowledge` | Any implementation in `custom_components/diagral/` — architecture, invariants, HA expectations |
| `testing-hass-diagral` | Running or writing tests, devcontainer setup |
| `live-validation-hass-diagral` | Proving a change works in a real Home Assistant, without touching the production central |
| `git-conventions` | Commits, PRs, branch rules |
| `docs-hass-diagral` | Anything under `docs/` |
| `ha-review` | Reviewing a change or a pull request |
| `ha-quality-scale-verify` | Auditing a quality-scale rule against the code |

Load `ha-integration-knowledge` first for work in the integration, and pair it with the narrower skill for the task at hand.

## Writing to GitHub

- **Never self-reference in commits.** No `Co-Authored-By: Claude`, no `Claude-Session:` trailer, no mention of the assistant or the session — in commit messages, PR bodies or issue text. Only add them if asked for a specific commit.
- **Correct a mistake in an issue or PR by editing the body**, and delete any correction comment already posted. An issue is a specification, not a conversation log. Once a discussion is under way, say in the thread that the body changed rather than editing silently.
- **Never publish personal data.** The central serial, the alarm name, the config entry id, the webhook id or URL, the account e-mail and any credential must not appear in an issue, a commit, a PR or a published page. Anonymise entity ids to `alarm_control_panel.<alarm>_central`, and never quote a webhook payload or a `pydiagral.api` debug line unredacted — they carry the serial, user names and URLs.
- Ask before any outward-facing action: opening or closing an issue or PR, posting a comment, pushing to a shared branch.

## Verifying

The user expects claims to be checked, not asserted. Read the code, run the command, observe it on a live instance. When a measurement contradicts an earlier statement, say so plainly and correct it.

## Committing

Do not commit or push unless asked. The user reviews changes first.
