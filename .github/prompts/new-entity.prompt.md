---
description: "Create a complete new entity for the hass-diagral integration: EntityDescription, class, unique_id, translations (en + fr), docs entry, and test stub."
agent: "agent"
argument-hint: "e.g. sensor named 'battery_level' measuring battery percentage"
---

Create a complete new entity for the hass-diagral integration based on the following request:

**Request:** $input

Follow all rules in [entity.instructions.md](../.github/instructions/entity.instructions.md) and produce ALL of the following in one pass:

## 1. EntityDescription entry — `custom_components/diagral/sensor.py` or `alarm_control_panel.py`

Add a new `DiagralSensorEntityDescription` (or appropriate description type) to the `SENSORS` / `PANELS` tuple:
- `key`: snake_case identifier, unique within the platform
- `translation_key`: same as `key` unless a different human label is needed
- `icon`: appropriate `mdi:` icon
- `native_unit_of_measurement` if applicable
- `exists_fn` if the entity is conditional on coordinator data

## 2. Entity class update

If the entity requires custom `_handle_coordinator_update` logic or extra attributes, add or update the class accordingly.
Use the established `unique_id` pattern:
```python
f"{entry_id}_{DOMAIN}_{alarm_config.alarm.central.serial}_{description.key}"
```

## 3. Translations — both files

Update **`custom_components/diagral/translations/en.json`** and **`custom_components/diagral/translations/fr.json`**:

```json
"entity": {
    "<platform>": {
        "<translation_key>": {
            "name": "Human Readable Name"
        }
    }
}
```

## 4. Documentation — `docs/integration/entities.mdx`

Add a row to the entity table:

```mdx
| Entity Name | Description of what this entity exposes and its unit/format |
```

## 5. Test stub — `tests/test_<platform>.py`

Create or update the test file with at least:
- A test for the `unique_id` format
- A test for the entity state with mocked coordinator data
- A test for the `exists_fn` if one was defined

If `tests/` does not exist yet, also create `tests/__init__.py` and `tests/conftest.py` following [tests.instructions.md](../.github/instructions/tests.instructions.md).

## 6. Commit message

Provide a ready-to-use commit message following [commits.instructions.md](../.github/instructions/commits.instructions.md):

```
feat(<platform>): ✨ Add <entity_name> entity
```
