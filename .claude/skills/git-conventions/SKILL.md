---
name: git-conventions
description: Commit and PR procedure for hass-diagral — branch check, pre-commit test gate, Tests line, PR description template, and GitHub CLI usage.
---

# Git Conventions — hass-diagral

Use this skill for any commit, PR creation, or pre-commit verification task in the hass-diagral project.

---

## 0. GitHub Tooling

`gh` is installed and is the way to reach GitHub: issues, PRs, comments, checks, raw API. There is no MCP GitHub server configured for this repository.

```bash
gh issue create --title "..." --label bug --body-file <file>
gh issue edit <n> --body-file <file>
gh pr create --base dev --title "..." --body-file <file>
gh pr checks <n>
gh api repos/mguyard/hass-diagral/issues/comments/<id> -X DELETE
```

Write issue and PR bodies from a file rather than inline: it keeps the text reviewable before it is published, and lets it be scanned for personal data first (serial, alarm name, e-mail, webhook URL — see `CLAUDE.md`).

Ask before any outward-facing action — opening or closing an issue or PR, posting a comment, pushing to a shared branch.

---

## 1. Message and Title Format

The format, the type-to-gitmoji mapping, the scope vocabulary and the `Tests:` line are defined in **`AGENTS.md` → Commits**, which every agent reads. This skill does not restate them — it covers the procedure around them.

Worked examples:

```
feat(sensor): ✨ Add battery level sensor entity

- Exposes the lowest battery level reported by the central's devices
- Translation keys added to en.json and fr.json

Tests: ✅ 92 passed, ❌ 0 failed, ⚠️ 0 errors
```

```
fix(webhook): 🐛 Keep the subscription when it belongs to another instance

Tests: ✅ 88 passed, ❌ 0 failed, ⚠️ 0 errors
```

```
chore(deps): 🔧 Bump pydiagral to 1.7.0

Tests: ✅ 86 passed, ❌ 0 failed, ⚠️ 0 errors
```

```
docs(events): 📝 Document the ANOMALY event payload

Tests: N/A (no custom_components change)
```

---

## 2. Pre-commit Gate (Mandatory)

### 2.0 Branch check (always first)

```bash
git branch --show-current
```

- `beta` or `main` → **stop**. Switch to `dev` (or a branch cut from it), then re-apply the changes.
- `dev` or a feature branch → continue.

> **Never commit or push directly to `beta` or `main`.** semantic-release owns them.

### 2.1 Is the gate required?

```bash
git diff --name-only HEAD | grep -q "^custom_components/" && echo "tests required" || echo "tests not required"
```

- No file under `custom_components/` changed → skip the gate, write `Tests: N/A (no custom_components change)`.
- Otherwise the gate is mandatory: no commit until the suite passes at 100%.

### 2.2 Run the suite

Use the canonical commands in `testing-hass-diagral` §3. Capture the pytest summary line.

### 2.3 Fix loop

1. Read the failing output and find the root cause
2. Fix the code or the test
3. Rerun
4. Repeat until green — no exceptions

### 2.4 Embed the result

Last line of the commit body:

- `Tests: ✅ N passed, ❌ M failed, ⚠️ E errors` — when the gate ran
- `Tests: N/A (no custom_components change)` — when it was skipped

---

## 3. PR Conventions

### 3.1 Title

Same format as the commit first line. `semantic-prs.yml` validates it.

### 3.2 Description template

```markdown
## Summary

<One paragraph explaining the purpose and impact of the change.>

## Commits

- [`abc1234`](https://github.com/mguyard/hass-diagral/commit/abc1234) feat(sensor): ✨ Add battery level sensor — short explanation
- [`def5678`](https://github.com/mguyard/hass-diagral/commit/def5678) docs(entities): 📝 Document battery sensor

## Tests

```
python -m pytest custom_components/diagral/tests/ -v
✅ N passed, ❌ 0 failed, ⚠️ 0 errors — HA <version>, Python 3.14
```

## Live validation

<Level used (see live-validation-hass-diagral), HA version, what was observed. "N/A" with a reason when the change has no runtime effect.>

## Related Issues

Refs #<issue_number>
```

> `## Tests` is mandatory. Use `Closes #N` only when the issue should close once the change reaches `main` — see `AGENTS.md` → Branches.

### 3.3 Prepare-PR workflow

1. Confirm the branch (§2.0)
2. Run the gate (§2)
3. `git log origin/dev..HEAD --oneline` — commits for the `## Commits` section
4. `git diff origin/dev --stat` — check the scope
5. Write the title and body from the template into a file
6. Show it to the user; open with `gh pr create --base dev` only once they agree
