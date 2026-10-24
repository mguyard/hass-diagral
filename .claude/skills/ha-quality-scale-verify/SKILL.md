---
name: ha-quality-scale-verify
description: Verifies whether the hass-diagral integration follows a Home Assistant quality-scale rule, checking the code against the official rule definition. Use when asked to check a rule by name, to assess a whole tier (Bronze, Silver, Gold, Platinum), or to correct quality_scale.yaml.
---

# Verify a Quality Scale Rule — hass-diagral

Adapted from the Home Assistant core skill. Verify **one rule at a time**; to assess a whole tier, work through that tier's rules.

## Context for this repository

`manifest.json` declares `quality_scale: bronze`, and `custom_components/diagral/quality_scale.yaml` lists a status for every rule up to platinum. Those statuses were not all audited, and some contradict the code — see `ha-integration-knowledge` §11.2. hassfest does not enforce the file for custom integrations, so CI will never report a gap.

**The YAML is the claim under test, not the evidence.** Never accept a `done` because the file says so.

## 1. Fetch the rule definition

```
https://raw.githubusercontent.com/home-assistant/developers.home-assistant/refs/heads/master/docs/core/integration-quality-scale/rules/{rule}.md
```

`{rule}` is the identifier, for example `config-flow`, `entity-unique-id`, `runtime-data`. Never assess a rule from memory — the definitions change.

## 2. Understand what it requires

Extract the mandatory implementations, the exact code patterns expected, the common violations, the exemption criteria, and which tier the rule belongs to.

## 3. Read the code

The integration lives at `custom_components/diagral/` and its tests at `custom_components/diagral/tests/` — not at the core paths the upstream skill assumes.

Useful sources beyond the code:

- `manifest.json` — declared scale, dependencies, `iot_class`, `pydiagral` pin
- `hacs.json` — minimum supported Home Assistant version
- `docs/` — rules starting with `docs-` are satisfied by documentation on [docs.page](https://use.docs.page/), not by a core-style markdown page
- `https://pypi.org/pypi/pydiagral/json` — for `dependency-transparency`, `async-dependency`, `inject-websession`; the source is at [github.com/mguyard/pydiagral](https://github.com/mguyard/pydiagral)

## 4. Verify

Rules are **cumulative**: bronze applies to any integration declaring a scale, silver adds to bronze, and so on.

For each rule, decide `done`, `todo`, or `exempt`, and justify it against the code rather than against intent. An exemption needs a reason that survives scrutiny — "not applicable" is not one.

## 5. Report

Report only rules with a problem — a status in `quality_scale.yaml` that the code does not support, non-compliance, or an exemption that does not hold. For each one:

- **Rule** — identifier, declared status, actual status
- **Evidence** — file and line
- **Recommendation** — the change to the code, or to `quality_scale.yaml`

If every rule checked passes, say so in one line. If a rule definition cannot be fetched or the relevant code cannot be found, say what is missing rather than guessing.

## 6. Updating `quality_scale.yaml`

Keep the existing layout (one block per tier, comments `# Bronze`, `# Silver`…). Every `exempt` and every non-obvious `todo` carries a `comment`. `done` means verified against the code, not intended.
