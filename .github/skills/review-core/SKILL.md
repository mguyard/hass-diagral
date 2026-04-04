---
name: review-core
description: Shared contract for independent review agents and durable review findings.
user-invocable: false
---

# Skill: Review Core Contract

This skill is the single source of truth for independent code-review agents that feed either:

- direct single-model review (`Reviewer`)
- multi-model consolidation (`ReviewerGPT`, `ReviewerGemini` -> `MultiReviewer`)

## Scope

- Analyze code only; do not implement fixes.
- Focus on bugs, security, regressions, performance, and critical quality issues.
- Reference exact file paths and line numbers whenever possible.

## Severity Model

- `BLOCKER`: Must fix before shipping (security, data loss, critical bugs, breaking changes)
- `WARNING`: Should fix soon (error handling gaps, likely regressions, notable performance issues)
- `SUGGESTION`: Optional improvements (maintainability and design quality)
- `POSITIVE`: Good patterns worth preserving

## Minimum Review Process

1. Read changed files fully.
2. Inspect related callers/tests/types where relevant.
3. Validate edge cases and failure modes.
4. Check framework/library best practices with available docs tools.

## Mandatory Output Format

All independent reviewers must return findings in this exact structure:

```markdown
## Findings

### 🔴 BLOCKER: [File:Line] — [Title]
- Problem: [What's wrong]
- Impact: [Why it matters]
- Fix: [How to resolve]

### 🟡 WARNING: [File:Line] — [Title]
- Problem: [What's wrong]
- Suggestion: [How to improve]

### 🔵 SUGGESTION: [File:Line] — [Title]
- Observation: [What could be better]
- Benefit: [Why consider this]

### ✅ POSITIVE: [Description]
- [Good pattern/implementation found]
```

## Optional: Durable Notes for `.agent-memory/`

When the Orchestrator requests it (or when the review discovers durable repo-wide rules), append this section **after** `## Findings`:

```markdown
## Memory Candidate

- [Durable invariant/decision/rule-of-thumb worth remembering]
- [Repeatable error pattern + prevention guardrail]
- [How to run/build/test in this repo (only if stable)]
```

Keep it short (2–8 bullets). No long narrative.

## Rules

1. No code writing.
2. No vague statements; each finding must be actionable.
3. Prioritize correctness and risk over style preferences.
4. Avoid documentation-only nitpicks unless they hide a functional risk.
