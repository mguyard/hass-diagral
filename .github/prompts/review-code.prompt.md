---
description: "Review a Python file in hass-diagral for code quality: flake8 compliance (max 150 chars), Home Assistant async patterns, security, entity conventions, and test coverage gaps."
agent: "agent"
argument-hint: "File path to review, e.g. custom_components/diagral/sensor.py"
---

Perform a code review of the following file in the `hass-diagral` integration:

**File:** $input

Read the file fully, then evaluate it against the criteria below.

---

## 1. Flake8 — Line Length & Style

- Max line length: **150 characters**
- Flag any line that exceeds 150 characters
- Flag unused imports, undefined names, and bare `except:` clauses

## 2. Home Assistant Patterns

Check for correct usage of:
- `async`/`await` for all I/O-bound operations (no blocking calls in async context)
- `_LOGGER = logging.getLogger(__name__)` — no `print()` statements
- `CoordinatorEntity` / `DiagralEntity` as base class for entities
- `DiagralConfigEntry` used instead of raw `ConfigEntry`
- `entry.runtime_data.coordinator` to access the coordinator
- `@callback` decorator on `_handle_coordinator_update`
- Constants from `const.py` — no magic strings or numbers inline

## 3. Entity Conventions (if applicable)

- `_attr_unique_id` follows the pattern `{entry_id}_{DOMAIN}_{serial}_{key}`
- `_attr_has_entity_name = True` is set on the base class (already in `DiagralEntity`)
- `translation_key` is set on the `EntityDescription`
- `exists_fn` is defined if the entity is conditional

## 4. Security

Check for:
- No secrets or credentials logged
- No direct Diagral API calls (must go through `pydiagral`)
- No hardcoded URLs or tokens
- Input from webhooks / external sources is not trusted without validation

## 5. Error Handling

- Exceptions are caught at the appropriate level and logged with `_LOGGER.error` or `_LOGGER.warning`
- Coordinator data access uses `.get()` with safe fallbacks where the key may be absent
- No silent `except: pass` blocks

## 6. Test Coverage Gaps

List what is **not yet tested** in `tests/test_<module>.py` (or note if no test file exists):
- Untested public methods or properties
- Untested error paths
- Missing edge-case coverage

---

## Output Format

Present findings as:

### Issues (must fix)
- `<file>:<line>` — description

### Suggestions (nice to have)
- description

### Test gaps
- description

If the file passes all checks, say so clearly. Keep the review concise and actionable.
