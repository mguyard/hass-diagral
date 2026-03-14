---
description: "Use when writing commit messages, PR titles, or PR descriptions for hass-diagral. Enforces Conventional Commits + gitmoji format, scope conventions, branch rules, and PR description structure."
---

# Commit & PR Guidelines — hass-diagral

## Commit Message Format

```
<type>[optional scope]: <gitmoji> <description>

[optional body — bullet points]
```

- First line: **max 72 characters**
- Language: **English**
- Body: bullet points only when needed for clarity

## Types → Gitmoji

| Type | Gitmoji | Use When |
|------|---------|---------|
| `feat` | ✨ | New feature or entity |
| `fix` | 🐛 | Bug fix |
| `docs` | 📝 | Anything in `docs/` or `docs.json` |
| `refactor` | ♻️ | Code restructure, no feature/fix |
| `test` | ✅ | Adding or updating tests |
| `chore` | 🔧 | Deps, CI, build, maintenance |

## Scope (optional)

Use the module filename without extension:

- `sensor`, `coordinator`, `alarm_control_panel`, `config_flow`
- `webhook`, `diagnostics`, `entity`, `models`, `const`
- `deps` (for dependency bumps), `readme`, `entities` (for doc pages)

## Examples

```
feat(sensor): ✨ Add battery level sensor entity

fix(coordinator): 🐛 Retain stale data when API returns empty response

docs(entities): 📝 Document new battery sensor entity

refactor(webhook): ♻️ Simplify Nabu Casa URL detection logic

test(sensor): ✅ Add test for anomaly count sensor

chore(deps): 🔧 Bump pydiagral to 1.7.0
```

## PR Title

Same format as a commit message:

```
<type>[optional scope]: <gitmoji> <description>
```

## PR Description Template

```markdown
## Summary

<One paragraph explaining the purpose and impact of the change.>

## Commits

- [`abc1234`](https://github.com/mguyard/hass-diagral/commit/abc1234) feat(sensor): ✨ Add battery level sensor — short explanation
- [`def5678`](https://github.com/mguyard/hass-diagral/commit/def5678) docs(entities): 📝 Document battery sensor

## Related Issues

Closes #<issue_number>
```

## Branch Rules

| Branch | Role |
|--------|------|
| `dev` | Development — **all PRs must target this branch** |
| `main` | Stable releases — merged only by `semantic-release` CI |

Never open a PR directly against `main`.
