# Skills Catalog

This file is a navigation index for humans and agents.

Use it to quickly identify the narrowest relevant skill for a task before loading the full `SKILL.md`.
The source of truth remains each skill's own `SKILL.md` file and its `description` frontmatter.

## How to use this index

1. Start here when the task domain is clear but the best skill is not.
2. Prefer the narrowest matching skill over a broad fallback.
3. Combine multiple skills when the task spans domains.
4. For implementation and review, pair domain skills with baseline quality and verification skills when relevant.

## Quick routing hints

- **Home Assistant integration / Python / pydiagral / entities / coordinator / webhook** → `python-homeassistant`
- **Commit messages, PR title/description, pre-commit test gate, branch rules** → `git-conventions`
- **Running tests / devcontainer / pytest setup for this project** → `testing-hass-diagral`
- **Documentation pages in `docs/` (MDX, docs.json, components)** → `docs-hass-diagral`
- **Generic testing principles (behavior, determinism, unit vs E2E)** → `testing-qa`
- **Planning / decomposition / readiness gates** → `planning-structure`
- **Read-only discovery / routing prep** → `research-discovery`
- **General code quality** → `code-quality`
- **Testing / verification** → `testing-qa`
- **Security review baseline** → `security-best-practices`
- **Shared review contract** → `review-core`
- **Independent review routing / review gates** → `review-orchestration`
- **Multi-model review orchestration** → `multi-model-review`
- **Parallel isolated work using git worktrees** → `git-worktree`
- **Memory boundaries and durable repo memory** → `memory-management`

## Domain skill — hass-diagral

| Skill | Use for | Common triggers |
| --- | --- | --- |
| `python-homeassistant` | All implementation in `custom_components/diagral/` — entities, coordinator, config_flow, webhook, tests, translations | entity, coordinator, sensor, alarm_control_panel, config_flow, webhook, pydiagral, devcontainer, pytest |
| `git-conventions` | Commit messages, PR title/description, pre-commit test gate, branch rules | commit, PR, gitmoji, scope, test gate, branch, dev, conventional commits |
| `testing-hass-diagral` | Project-specific test setup: directory structure, tiers, devcontainer detection, pytest commands, shared fixtures | pytest, devcontainer, docker exec, conftest, fixtures, test tiers, run tests |
| `docs-hass-diagral` | Documentation pages in `docs/` — MDX format, frontmatter, components, docs.json registration, entity table | docs, MDX, frontmatter, docs.json, entities.mdx, components, Info, Warning, Card |

## Workflow and orchestration skills

| Skill | Use for | Common triggers |
| --- | --- | --- |
| `planning-structure` | Planning tracks, epics, readiness gates, plan delta handling | planning, decomposition, readiness, feature slices, epics |
| `research-discovery` | Fast broad-to-narrow read-only discovery before planning or routing | discover, scout, map codebase, entry points, reuse search |
| `memory-management` | Durable vs session memory rules and memory sync workflow | memory update, durable knowledge, `.agent-memory`, session notes |
| `git-worktree` | Isolated parallel work for risky refactors or overlapping file ownership | worktree, parallel branch, isolation, risky refactor |
| `review-orchestration` | Review routing, independent review gates, and optimization follow-up | review gate, post-implementation review, multi-review, cleanup pass |

## Review and quality skills

| Skill | Use for | Common triggers |
| --- | --- | --- |
| `code-quality` | Cross-stack implementation and review heuristics | refactor, implementation quality, maintainability |
| `testing-qa` | Unit, integration, and end-to-end verification strategy | tests, verification, QA, regressions |
| `security-best-practices` | Secure coding, auth, validation, and defense-in-depth | security, auth, input validation, secrets, hardening |
| `review-core` | Shared contract for independent reviewers and durable findings | audit, review contract, findings normalization |
| `review-orchestration` | When to review, when to skip, and how to route review follow-up | independent review, review gate, reviewer routing |
| `multi-model-review` | Consensus-based multi-review and false-positive triage | multi-review, reviewer consolidation, conflicts |

## Selection rules for agents

1. Always load `python-homeassistant` first for any task in `custom_components/diagral/`.
2. Combine domain + quality skills when reviewing or implementing non-trivial work:
   - Example: `python-homeassistant` + `testing-qa` + `code-quality`
   - Example: `python-homeassistant` + `security-best-practices` (webhook or API work)
3. Use orchestration skills to support execution, not to replace domain skills.
4. If multiple skills seem plausible, start with the narrowest one and add a broad fallback only if needed.
