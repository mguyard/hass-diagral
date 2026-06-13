---
name: git-conventions
description: Commit message format, PR conventions, branch rules, and pre-commit test gate for hass-diagral.
user-invocable: false
---

# Git Conventions — hass-diagral

Use this skill for any commit, PR creation, or pre-commit verification task in the hass-diagral project.

---

## 1. Commit Message Format

```
<type>[optional scope]: <gitmoji> <description>

[optional body — bullet points]

Tests: N passed, 0 failed, 0 errors
```

- First line: **max 72 characters**, in **English**
- Body: bullet points only when needed for clarity
- `Tests:` line: **always required** — run the test gate (§3) before committing

---

## 2. Types, Gitmoji, and Scopes

### 2.1 Types → Gitmoji

| Type | Gitmoji | Use When |
|------|---------|----------|
| `feat` | ✨ | New feature or entity |
| `fix` | 🐛 | Bug fix |
| `docs` | 📝 | Anything in `docs/` or `docs.json` |
| `refactor` | ♻️ | Code restructure, no feature/fix |
| `test` | ✅ | Adding or updating tests |
| `chore` | 🔧 | Deps, CI, build, maintenance |

### 2.2 Scope (optional)

Use the module filename without extension:
- `sensor`, `coordinator`, `alarm_control_panel`, `config_flow`
- `webhook`, `diagnostics`, `entity`, `models`, `const`
- `deps` (dependency bumps), `readme`, `entities` (doc pages)

### 2.3 Examples

```
feat(sensor): ✨ Add battery level sensor entity

- Added DiagralBatteryLevelSensor to sensor.py
- Added translation keys to en.json and fr.json

Tests: ✅ 42 passed, ❌ 0 failed, ⚠️ 0 errors

fix(coordinator): 🐛 Retain stale data when API returns empty response

Tests: ✅ 42 passed, ❌ 0 failed, ⚠️ 0 errors

test(sensor): ✅ Add test for anomaly count sensor

Tests: ✅ 43 passed, ❌ 0 failed, ⚠️ 0 errors

chore(deps): 🔧 Bump pydiagral to 1.7.0

Tests: ✅ 42 passed, ❌ 0 failed, ⚠️ 0 errors
```

---

## 3. Pre-commit Gate (Mandatory)

The pre-commit gate applies **only when `custom_components/` has changed** in the current commit.

Before running, check whether the staged or changed files include `custom_components/`:
```bash
git diff --name-only HEAD | grep -q "^custom_components/" && echo "tests required" || echo "tests not required"
```

If no file under `custom_components/` is modified → skip the gate, use `Tests: N/A (no custom_components change)` in the commit body.

If any file under `custom_components/` is modified → the gate is mandatory. No commit may be created until all tests pass at 100%.

### 3.1 Run Tests

Follow `@skills/testing-hass-diagral/SKILL.md §3` for the canonical run commands (environment detection, devcontainer vs `docker exec`).

Quick summary:
```bash
# Detect environment
test -d /workspaces && echo "inside devcontainer" || echo "outside"
# Then run pytest tests/ -v (see testing-hass-diagral §3 for full commands)
```

Capture the output to extract the summary line.

### 3.2 Pass Gate

Parse the last summary line from pytest output:
```
N passed, 0 failed, 0 errors
```

- If **0 failures and 0 errors** → gate passes, proceed to commit
- If **any failure or error** → go to §3.3

### 3.3 Fix Loop (when gate fails)

1. Read the failing test output and identify the root cause
2. Fix the code or test causing the failure
3. Rerun tests (§3.1)
4. Repeat until gate passes
5. Do NOT commit until 100% pass — this rule has no exceptions

### 3.4 Embed Results in Commit Body

After gate passes (or is skipped), embed the test summary as the final line of the commit body:

```
feat(sensor): ✨ Add battery level sensor entity

- Added DiagralBatteryLevelSensor to sensor.py
- Added translation keys to en.json and fr.json

Tests: ✅ 42 passed, ❌ 0 failed, ⚠️ 0 errors
```

Format:
- `Tests: ✅ N passed, ❌ M failed, ⚠️ E errors` — when gate ran
- `Tests: N/A (no custom_components change)` — when gate was skipped

---

## 4. PR Conventions

### 4.1 PR Title

Same format as the commit first line:
```
<type>[optional scope]: <gitmoji> <description>
```

### 4.2 PR Description Template

```markdown
## Summary

<One paragraph explaining the purpose and impact of the change.>

## Commits

- [`abc1234`](https://github.com/mguyard/hass-diagral/commit/abc1234) feat(sensor): ✨ Add battery level sensor — short explanation
- [`def5678`](https://github.com/mguyard/hass-diagral/commit/def5678) docs(entities): 📝 Document battery sensor

## Tests

```
pytest tests/ -v
✅ N passed, ❌ 0 failed, ⚠️ 0 errors
```

## Related Issues

Closes #<issue_number>
```

> `## Tests` is **mandatory**. Run the pre-commit gate (§3) on the source branch before opening the PR. Fix all failures before opening.

### 4.3 Branch Rules

| Branch | Role |
|--------|------|
| `dev` | Development — **all PRs must target this branch** |
| `main` | Stable releases — merged only by `semantic-release` CI |

Never open a PR directly against `main`.

### 4.4 Prepare PR Workflow

1. Ensure you are on the feature branch
2. Run pre-commit gate (§3) on the source branch
3. Run `git log origin/dev..HEAD --oneline` — list commits for the `## Commits` section
4. Run `git diff origin/dev --stat` — verify scope of changes
5. Produce PR title + description using the template (§4.2)
6. Target branch: **always `dev`**
