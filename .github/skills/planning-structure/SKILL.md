---
name: planning-structure
description: Planning-track selection, epic/feature decomposition, readiness gates, and plan-delta rules.
user-invocable: false
---

# Planning Structure

Use this skill when producing or evaluating non-trivial implementation plans.

## 1. Track Selection

Choose the smallest track that still manages risk:

- **Quick Change**
  - one localized change
  - clear owner and file scope
  - low ambiguity
  - little or no architecture impact
- **Feature Track**
  - one feature or bug spanning a few areas
  - moderate ambiguity or dependencies
  - clear user value and verification path
- **System Track**
  - multi-surface work
  - architecture, workflow, data-model, or integration impact
  - cross-team or Multi-Hive candidate
  - requires explicit artifact planning or a readiness gate

Default upward when scope uncertainty is high.

## 2. Planning Shapes

### Quick Change

Keep the plan compact:

1. objective
2. affected files and owners
3. ordered steps
4. verification
5. scope boundaries

### Feature Track

Use a feature-oriented structure:

1. objective
2. scope
3. feature slices
4. dependencies
5. risks
6. verification
7. gaps and proposed defaults

### System Track

Use a layered structure:

1. objective
2. scope and exclusions
3. epics
4. features inside each epic
5. documentation artifacts needed
6. dependencies and sequencing
7. risks and open gaps
8. readiness gate
9. verification

## 3. Epic and Feature Rules

For larger work:

- Prefer `2-5` epics.
- Each epic should represent one coherent value stream or subsystem boundary.
- Each epic should contain a small number of implementable features or vertical slices.
- Each feature should state:
  - user or system value
  - deliverable
  - verification signal
  - main dependencies

Do not create epics for trivial work.

## 4. Deliverable and Verification Discipline

Every feature or major step should answer:

1. what will exist when this is done?
2. how will we verify it?
3. what must already exist first?

Prefer concrete verification:

- tests
- commands
- observable UI flows
- logs or metrics
- API responses

## 5. Gaps and Proposed Defaults

When a decision is unresolved but planning can continue, include:

- **Open Question**
- **Recommended Default**
- **Impact if wrong**

If the unresolved point changes architecture, security, or data correctness materially, stop and clarify instead of assuming.

## 6. Documentation Artifacts

Only plan artifacts that materially reduce execution risk.

Common candidates for `System Track`:

- `architecture.md`
- `data-model.md`
- `api-contracts.md`
- `runbook.md`
- `privacy-security-notes.md`

Do not auto-generate all of them. Name only what the work actually needs.

## 7. Readiness Gate

Execution is ready only when all are true:

1. scope is stable enough to implement
2. owners and affected areas are known
3. dependencies are identified
4. verification is concrete
5. critical gaps are resolved or intentionally defaulted

Output:

- `Implementation Readiness: PASS`
- or `Implementation Readiness: BLOCKED`

If blocked, say exactly what must be resolved first.

## 8. Plan Delta

When scope changes after a plan already exists, do not rewrite from scratch first. Produce a delta:

1. what changed
2. what stays valid
3. what steps are removed
4. what new steps are added
5. whether readiness changed
6. whether routing or Multi-Hive strategy changed

## 9. Clarification Bias

Treat planning as an interview loop, not a one-shot report.

Use clarification aggressively when the unresolved point affects:

1. user-visible behavior, UX copy, or product semantics
2. API contracts, schema, persistence, migration, or compatibility behavior
3. security, privacy, performance, or reliability expectations
4. verification, rollout, fallback, or non-goal boundaries

Default clarification behavior by track:

1. `Quick Change`: ask only when scope or acceptance criteria are not clear
2. `Feature Track`: expect at least one clarification round unless the request is already explicit
3. `System Track`: expect clarification and do not force execution-readiness until user-owned decisions are resolved

`Gaps and Proposed Defaults` is only for low-impact implementation details. If the gap changes UX, API, data correctness, security, or verification, ask via `vscode_askQuestions` (mandatory — see global rule in `copilot-instructions.md`) instead of defaulting.

## 10. Anti-Patterns

Avoid:

- giant flat task lists with no value grouping
- steps with no deliverable or no verification
- architecture artifacts for small/local changes
- hiding unresolved critical gaps inside assumptions
- re-planning from zero when a plan delta is enough
