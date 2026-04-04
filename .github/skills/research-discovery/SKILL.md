---
name: research-discovery
description: Fast broad-to-narrow read-only discovery for planning, routing, and review preparation.
user-invocable: false
---

# Research Discovery

Use this skill when an agent needs to understand an unfamiliar request, map the codebase quickly, or gather just enough context for planning, routing, or review.

## Search Strategy

Go **broad to narrow**:

1. Start with broad discovery:
   - file patterns
   - directory ownership
   - obvious entry points
2. Narrow with targeted text or symbol search:
   - specific identifiers
   - error strings
   - integration points
3. Read files only when the path is known or full context is needed.

## Parallel Discovery

Parallelize only when the task has multiple mostly independent tracks.

- `x1`: one primary area
- `x2`: two clear research tracks (for example frontend + backend)
- `x3`: architecture/onboarding/multi-surface work where three tracks materially improve decomposition

Do not exceed `x3`.

## Speed Principles

- Bias for speed over exhaustiveness.
- Stop once you have enough context to answer the delegated question.
- Prefer a few targeted searches over large indiscriminate sweeps.
- Reuse existing patterns and analogous implementations whenever possible.

## Memory Use

- Read session memory only when it helps align with recent context.
- Do not treat session memory as durable project truth.
- If a discovery result becomes durable knowledge, it must be written later into `.agent-memory/` by the appropriate writing agent.

## Output

Return concise findings that are immediately useful to the parent agent:

1. clickable absolute file paths
2. specific functions, types, patterns, or commands worth reusing
3. likely owners, subsystem boundaries, or candidate epics when the parent agent is planning larger work
4. blockers, ambiguities, and risks
5. direct answer to the delegated question

Do not drift into implementation unless the parent agent explicitly asked for implementation guidance.
