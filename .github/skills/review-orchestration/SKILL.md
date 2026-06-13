---
name: review-orchestration
description: Review routing, independent post-implementation review gates, multi-model escalation, and targeted optimization follow-up.
user-invocable: false
---

# Review Orchestration

Use this skill when the Orchestrator is deciding how to run review after implementation or debugging work.

## 1. Purpose

This skill governs:

1. when review is required
2. when review may be skipped
3. single-model vs multi-model review selection
4. how to route findings back into execution
5. when a targeted optimization pass is justified

It does NOT replace:

- `review-core` for independent reviewer output format
- `multi-model-review` for consensus consolidation

## 2. Independent Review Gate

Default rule:

1. any non-trivial implementation or verified bug fix must be reviewed by a model that did not author the change
2. the reviewer must be independent from the coding/debugging agent that produced the patch
3. do not close the task before the independent review is complete, unless a valid skip rule applies

Review is usually required when any are true:

1. behavior changed
2. `>= 2` files changed
3. tests were added or updated
4. shared utilities, public APIs, persistence, config, auth, or security-sensitive code changed
5. the change came from `Debugger`, `CoderSr`, or a worktree-based flow

## 3. Review Skip Rules

Review may be skipped only when all are true:

1. the change is trivial and mechanical
2. scope is localized to one file or one clearly isolated config surface
3. no behavior, API, persistence, security, or performance expectation changed
4. there is no meaningful regression risk

If review is skipped, say why explicitly in the final report.

## 4. Mode Selection

Use single-model review by default.

Use multi-model review when any are true:

1. authentication, authorization, payments, secrets, or PII handling changed
2. data persistence, migrations, or compatibility behavior changed
3. shared infrastructure or core cross-cutting utilities changed
4. change volume is large (`>5` files or roughly `>200` changed lines)
5. the user explicitly asked for a deep audit

## 5. Delegation Contract

For every review run, inject these baseline skills:

1. `@skills/security-best-practices/SKILL.md`
2. `@skills/code-quality/SKILL.md`
3. `@skills/testing-qa/SKILL.md`
4. `@skills/review-core/SKILL.md`

Single-model path:

1. default reviewer: `Reviewer`
2. reviewer returns findings using `review-core`

Multi-model path:

1. run `ReviewerGPT`, `ReviewerGemini`, and `Reviewer` in parallel
2. use the same review skills and priority order for all 3
3. pass raw outputs to `MultiReviewer`
4. label them exactly:
   - `=== ReviewerGPT ===`
   - `=== ReviewerGemini ===`
   - `=== Reviewer ===`
5. use `@skills/multi-model-review/SKILL.md` for consolidation policy

## 6. Fix Loop After Review

If review returns concrete issues:

1. route correctness, safety, or regression issues back to the appropriate executor
2. keep the fix scope narrow; do not restart implementation from scratch
3. re-run independent review when the fix is non-trivial or touches the original risky area

If review returns no significant issues:

1. proceed to independent verification
2. close the task only after verification passes or a justified skip/override exists

## 7. Optimization Follow-Up

Optimization is not a mandatory polishing pass.

Use a targeted optimization follow-up only when at least one is true:

1. the review flags maintainability debt that meaningfully affects future changes
2. the review flags measurable performance concerns
3. the review flags obvious complexity, duplication, or test fragility introduced by the change
4. the user explicitly asks for cleanup or optimization

Rules:

1. optimization must be grounded in review findings or explicit user intent
2. do not run speculative cleanup loops after every feature
3. after optimization, run a short independent re-review unless the changes are trivially local
4. after review and any justified optimization follow-up, hand off to `Verifier` for objective acceptance checks

## 8. Output Expectations for Orchestrator

The Orchestrator should keep only these decisions locally:

1. review required or justified skip
2. single-model or multi-model
3. executor chosen for follow-up fixes
4. whether targeted optimization is warranted
5. whether the task is ready for `Verifier`

Detailed review workflow policy belongs in this skill, not in the Orchestrator prompt.
