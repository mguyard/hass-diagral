---
last_updated: 2026-03-10
purpose: "Recurring bug patterns and fixes. Template file for downstream projects."
---

# Error Patterns

## How to Use

- Record only repeatable patterns (root cause + fix + prevention).
- Include reproduction signal when available (test name, stack trace snippet, command).
- Prefer actionable prevention guardrails (lint rule, test, invariant, CI gate).
- Keep entries short and reusable; do not dump incident timelines.

## Entry Template

```md
## <Pattern Title> — YYYY-MM-DD

### Reproduction Signal
- Test name, stack trace, failing command, or clear repro steps.

### Root Cause
- The repeated failure mode.

### Fix
- What resolved it.

### Prevention
- Guardrail: test, lint, invariant, review rule, or coding constraint.
```

## Patterns

<!-- Add project-specific recurring patterns below. Keep this file empty in reusable template repositories. -->

_No patterns recorded yet._
