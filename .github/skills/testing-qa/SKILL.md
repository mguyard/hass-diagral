---
name: testing-qa
description: Practical testing rules for unit, integration, and end-to-end verification.
license: "See repository LICENSE"
user-invocable: false
---

# Testing & QA Practices

Use this skill when adding tests, fixing failing tests, or deciding how to verify a change safely.

## Priorities

1. **Test real behavior**
2. **Keep tests deterministic**
3. **Match test scope to risk**
4. **Prefer fast feedback**
5. **Keep tests maintainable**

## Core Rules

### 1. Start with the smallest useful test

- Unit tests for isolated logic
- Integration tests for contracts between components
- E2E only for critical user journeys and system-level confidence

Do not jump to the heaviest test layer first unless the bug or requirement is only visible there.

### 2. Test behavior, not implementation trivia

- Assert observable outcomes.
- Avoid coupling tests to internal helper structure unless that structure is the contract.
- Refactors should not break good tests when behavior is unchanged.

### 3. Keep tests deterministic

- Control time, randomness, network, and external services.
- Use fixtures/factories intentionally.
- Avoid sleeps and timing races when a proper wait/trigger exists.

### 4. Cover the exact risk you introduced

For every meaningful change, ask:

- what can regress?
- what edge case is easiest to miss?
- what user-visible behavior proves the fix or feature works?

### 5. Keep verification layered

- narrow automated checks first
- broader integration next when needed
- manual verification for UX, environment-specific flows, or things automation cannot cheaply prove

## By Test Type

### Unit

- ideal for pure logic, mapping, formatting, validators, reducers, helpers
- should be fast and isolated

### Integration

- use for DB interactions, API contracts, module boundaries, queue/worker behavior, or framework integration
- prefer realistic wiring with limited mocking

### End-to-End

- reserve for high-value journeys
- keep scenarios independent
- avoid bloated end-to-end suites that duplicate lower-level coverage

## Good Testing Defaults

- add a regression test for bug fixes when the repo has tests
- prefer factories over giant inline fixtures
- keep one test focused on one behavior
- name tests so failure explains the broken expectation

## Review Heuristics

Look for:

- tests that assert implementation details instead of behavior
- missing regression coverage for the changed risk
- non-deterministic waits and sleeps
- over-mocking that hides real integration bugs
- giant fixtures that make failures hard to reason about
- E2E coverage used where a smaller test would be clearer

## Anti-Patterns

Avoid:

- asserting every internal call in routine code
- snapshot-heavy testing without meaningful review discipline
- tests that only prove mocks were configured
- one huge test covering many unrelated behaviors
- fragile selectors in UI tests when stable hooks exist

## Quick Checklist

- [ ] Test scope matches the risk
- [ ] Behavior under test is explicit
- [ ] Test is deterministic
- [ ] Regression path is covered when relevant
- [ ] Mocks are limited to true external boundaries
- [ ] Manual verification steps are noted when automation is insufficient
