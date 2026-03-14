---
applyTo: "custom_components/diagral/*.py"
description: "Use when creating or modifying Home Assistant entities (sensor, alarm_control_panel) in the diagral integration. Covers EntityDescription pattern, unique_id, translation keys, conditional exists_fn, and documentation checklist."
---

# Entity Guidelines — hass-diagral

## Checklist for Every New Entity

1. **`EntityDescription` subclass** — `@dataclass(frozen=True)`, extends the HA description class
2. **`unique_id`** — Follow the established pattern (see below)
3. **`translation_key`** — Set on the description; add to both `en.json` **and** `fr.json`
4. **`exists_fn`** — Add if the entity is conditional; defaults to `lambda _: True`
5. **Documentation** — Add a row to `docs/integration/entities.mdx`
6. **Tests** — Add or update tests in `tests/test_<platform>.py`

## EntityDescription Pattern (Sensor example)

```python
@dataclass(frozen=True)
class DiagralSensorEntityDescription(SensorEntityDescription):
    """Sensor entity description for Diagral."""

    exists_fn: Callable[..., bool] = lambda _: True


SENSORS: tuple[DiagralSensorEntityDescription, ...] = (
    DiagralSensorEntityDescription(
        key="my_sensor",            # snake_case, unique within the platform
        translation_key="my_sensor",  # must match the key in en.json / fr.json
        icon="mdi:...",
        native_unit_of_measurement="unit",
        # exists_fn=lambda coordinator: coordinator.some_condition,
    ),
)
```

## unique_id Pattern

All entity unique IDs must follow:

```python
self._attr_unique_id = (
    f"{config_entry.entry_id}_{DOMAIN}"
    f"_{coordinator.data['alarm_config'].alarm.central.serial}"
    f"_{description.key}"
)
```

## Base Class

All entities extend `DiagralEntity`:

```python
from .entity import DiagralEntity

class DiagralMySensor(DiagralEntity, SensorEntity):
    def __init__(
        self,
        coordinator: DiagralDataUpdateCoordinator,
        description: DiagralSensorEntityDescription,
        config_entry: DiagralConfigEntry,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._entry_id = config_entry.entry_id
        self._alarm_config = coordinator.data.get("alarm_config", {})
        self._attr_unique_id = (
            f"{self._entry_id}_{DOMAIN}"
            f"_{self._alarm_config.alarm.central.serial}"
            f"_{description.key}"
        )
```

## Coordinator Data Keys

Available from `coordinator.data`:

| Key | Type | Description |
|-----|------|-------------|
| `alarm_config` | `AlarmConfiguration` | Full alarm configuration |
| `system_status` | `SystemStatus` | Current system status |
| `anomalies` | `Anomalies` | Current anomalies list |
| `groups` | `list[Group]` | Active arming groups |
| `devices_infos` | `DeviceInfos` | All registered devices |

## Translation — en.json and fr.json

Add under `entity.<platform>.<translation_key>`:

```json
"entity": {
    "sensor": {
        "my_sensor": {
            "name": "Human Readable Name"
        }
    }
}
```

Both `translations/en.json` **and** `translations/fr.json` must be updated.

## async_setup_entry

Register new entities from the SENSORS/PANELS tuple in `async_setup_entry`:

```python
async def async_setup_entry(
    hass: HomeAssistant,
    entry: DiagralConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data.coordinator
    async_add_entities(
        DiagralMySensor(coordinator, description, entry)
        for description in SENSORS
        if description.exists_fn(coordinator)
    )
```

## Documentation

Add a row in `docs/integration/entities.mdx`:

```mdx
| My Sensor | Description of what this entity exposes |
```
