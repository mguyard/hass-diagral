---
name: ha-review
description: Reviews code changes and pull requests for hass-diagral with a consistent contract and output format. Covers reviewing a working tree, a branch, or a GitHub PR, and auditing whether existing review comments have been addressed.
---

# Review Code Changes — hass-diagral

Adapted from the Home Assistant core review skill. Use it whenever a review is requested, on a branch, on uncommitted work, or on a pull request.

## Scope

Unless told otherwise, review the full change — the branch plus anything uncommitted — against the target branch. `dev` is the default base here; a PR's base comes from `gh pr view`. This repository has a single remote, so resolve the base as `origin/<base>` and fall back to the local branch:

```bash
BASE=origin/dev
git diff "$(git merge-base "$BASE" HEAD)"
```

## Reviewing a pull request

```bash
gh pr view <n>          # title, description, base branch
gh pr diff <n>          # the change itself
gh pr checks <n>        # whether CI already caught something
```

Pass the PR's actual base to the diff step rather than assuming `dev`.

Read the description critically. A claim in a PR body is not evidence: check what it asserts against what the repository actually does.

Dependabot PRs bump GitHub Actions only; check the action's changelog for breaking inputs rather than reviewing code.

## Auditing existing review comments

```bash
gh api repos/mguyard/hass-diagral/pulls/<n>/comments --paginate
```

Flag a comment when it has not been addressed, and when the author replied without implementing the suggestion — summarise the reply in that case. Flag comments where the author asked for clarification. Do not list comments that were addressed. Include a link for each one flagged.

## What to look for

- Correctness and edge cases, especially error paths and missing coordinator data
- Consistency with the invariants in `AGENTS.md` and `ha-integration-knowledge`
- Blocking calls in async context
- Security: never a credential, key, PIN, webhook id or URL in a log line, an event payload or a diagnostics dump
- Webhook changes: what happens to another Home Assistant sharing the central (`ha-integration-knowledge` §2.3)
- Public contracts: `DIAGRAL_EVENT` payload, dispatcher signal names, entity `key`s, service schemas — a change here breaks user automations
- A `pydiagral` workaround that belongs in `pydiagral` itself
- Test coverage of what changed, and whether the new tests are load-bearing
- Documentation under `docs/` when behaviour or a contract changed
- `manifest.json`, `services.yaml`, translations: hassfest does not run on `dev`, so a structural mistake is only caught on `beta`

If the change touches `quality_scale.yaml`, verify each added or modified rule with the `ha-quality-scale-verify` skill and fold the result into the review.

## Verification

After drafting the findings, re-check each one before reporting it. Prefer disproving your own finding to reporting it optimistically: a plausible-but-wrong finding costs the reader more than a missed nitpick. State a finding as confirmed only when you can name the input that triggers it and the resulting behaviour.

## Rules

- **Review only. Make no changes.**
- Report in the console. Do not post to GitHub unless explicitly asked.
- Be specific and constructive. Suggest an improvement rather than only naming a problem.
- Do not highlight what is already fine.
- No need to run tests — CI does that. Read the code.

## Output format

List findings per file and line, then close with an overall assessment.

```
Overall assessment: request changes.
- [CRITICAL] __init__.py:212 - unload deletes a subscription that points to another instance
- [PROBLEM] config_flow.py:198 - password logged at debug level
- [SUGGESTION] test_sensor.py:45 - parametrise instead of duplicating the body
```

Use `approve`, `request changes`, or `comment` as the assessment. Always include file and line where possible.
