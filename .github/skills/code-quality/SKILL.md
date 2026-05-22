---
name: code-quality
description: Concise code-quality rules for implementation and review across the stack.
license: "See repository LICENSE"
user-invocable: false
---

# Code Quality & Clean Code

Use this skill for implementation, refactoring, and review when you need practical guidance rather than a textbook.

## Priorities

Apply these in order:

1. **Correctness**
2. **Simplicity**
3. **Consistency with the repo**
4. **Operability** (errors, logs, debuggability)
5. **Performance where it matters**

Do not trade correctness for cleverness.

## Core Rules

### 1. Prefer the smallest safe change

- Fix the root cause, not just the symptom.
- Change only the files and behaviors needed for the task.
- Avoid opportunistic refactors unless they directly reduce risk for the task at hand.

### 2. Reuse existing patterns

- Match the repository's naming, file layout, error-handling style, and testing approach.
- Prefer extending an existing abstraction over inventing a new one.
- If the repo already has two patterns for the same concern, follow the more local one unless there is a strong reason not to.

### 3. Keep control flow obvious

- Prefer flat, readable code over indirection.
- Avoid deep nesting when early returns or small helpers make the path clearer.
- Make state transitions explicit.
- Do not hide business-critical work inside callbacks, decorators, magic hooks, or convenience wrappers unless the repo already standardizes on them.

### 4. One unit, one reason to change

- Functions should do one coherent job.
- Modules should have clear ownership boundaries.
- If one function validates input, writes data, sends notifications, and updates analytics, split the responsibilities unless the repo strongly prefers orchestration in one place.

### 5. Make invalid states hard to represent

- Encode invariants in types, schemas, guards, or data structures when practical.
- Prefer explicit state models over loosely coupled booleans or nullable piles.
- Validate external input at boundaries.

### 6. Be explicit about failures

- Never silently swallow errors.
- Add context when rethrowing or converting errors.
- Use structured logs at meaningful boundaries.
- Return or throw domain-appropriate errors; avoid generic `"something went wrong"` style messages inside the code path.

### 7. Keep comments rare and valuable

- Prefer self-explanatory code first.
- Comment only for invariants, non-obvious tradeoffs, protocol details, or external constraints.
- Remove stale TODO-style comments instead of adding new vague ones.

### 8. Keep configuration boring

- Prefer explicit config over hidden defaults.
- Centralize cross-cutting configuration when the repo already has a convention for it.
- Name feature flags, environment variables, and constants clearly.

## Refactoring Rules

Refactor only when at least one is true:

1. it removes duplication that would otherwise make the current task risky
2. it clarifies ownership or control flow required for the current task
3. it reduces the chance of regression in a touched code path

Do not refactor just because the code can be made "cleaner."

## Review Heuristics

When reviewing or self-checking code, look for:

### Correctness

- missing edge-case handling
- partial success / partial failure paths
- race conditions or ordering assumptions
- broken invariants after updates
- unsafe defaults or silent fallbacks

### Maintainability

- duplicated logic in nearby files
- helpers that hide too much
- misleading names
- functions that mix domain logic and transport/UI concerns
- abstractions that save little but cost a lot

### Safety

- unvalidated external input
- privilege or authorization gaps
- unsafe retries / repeated side effects
- logging of secrets or sensitive data
- lack of timeout / cancellation / cleanup at important boundaries

### Testing

- missing tests for changed behavior
- tests coupled to implementation details instead of behavior
- missing regression coverage for the exact bug or risk being addressed

## Good Defaults by Task Type

### New feature

- add the smallest extension point that fits the existing architecture
- keep the happy path clear
- add validation and test coverage around new behavior

### Bug fix

- reproduce first when possible
- patch the narrowest root cause
- add or update a regression test if the repo has tests

### Refactor

- preserve behavior
- keep changes reviewable
- validate key paths after each structural step

### Review

- prioritize correctness, regressions, and security over style
- do not request abstraction for abstraction's sake

## Anti-Patterns

Avoid these unless the repo explicitly depends on them:

- speculative abstractions
- giant utility modules
- boolean flag state machines with unclear ownership
- catching broad errors and returning defaults silently
- "smart" helper layers that obscure I/O or state changes
- comments that restate the code
- large rewrites when a surgical fix is enough

## Quick Checklist

- [ ] The change follows local repo patterns
- [ ] Ownership and control flow are easy to follow
- [ ] External input is validated at the boundary
- [ ] Errors are explicit and contextual
- [ ] The change is no larger than necessary
- [ ] Tests or verification steps match the real risk
- [ ] No unnecessary abstraction was introduced
