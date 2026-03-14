---
description: "Prepare a pull request for hass-diagral: analyze staged/current branch changes, then generate a properly formatted PR title, description, and commit list following project conventions."
agent: "agent"
tools: [run_in_terminal, read_file]
argument-hint: "Optional: issue number to close (e.g. 42) or a summary of the change"
---

Prepare a pull request for the `hass-diagral` project. Follow all rules in [commits.instructions.md](../instructions/commits.instructions.md).

## Step 1 — Gather context

Run the following to understand what changed:

```bash
# All commits on this branch not yet in dev (or main)
git log origin/dev..HEAD --oneline --no-decorate

# Full diff summary
git diff origin/dev --stat
```

Read the output carefully to understand:
- Which files changed and why
- The nature of each commit (feat / fix / docs / refactor / test / chore)
- Whether any commit closes a GitHub issue

## Step 2 — Generate PR title

Format: `<type>[optional scope]: <gitmoji> <description>` — max 72 characters.

Choose the type that best represents the **dominant** change. If the branch mixes a feat and docs update, use `feat`.

## Step 3 — Generate PR description

Use this exact structure:

```markdown
## Summary

<One paragraph explaining the purpose and impact of the change.>

## Commits

- [`<short-sha>`](https://github.com/mguyard/hass-diagral/commit/<full-sha>) <type>(<scope>): <gitmoji> <description> — <one-line explanation>

## Related Issues

Closes #<issue_number>
```

Omit "Related Issues" if no issue is referenced.

## Step 4 — Pre-flight checklist

Before presenting the result, verify:
- [ ] Target branch is `dev` (never `main`)
- [ ] PR title follows Conventional Commits + gitmoji format
- [ ] Each commit SHA links to `github.com/mguyard/hass-diagral/commit/<sha>`
- [ ] New entities are documented in `docs/integration/entities.mdx`
- [ ] Tests exist or are proposed for new features / bug fixes

Present the final PR title and description in a ready-to-copy code block.
