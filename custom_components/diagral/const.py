"""Constants for the Diagral integration."""

DOMAIN = "diagral"
BRAND = "Diagral"

CONFIG_VERSION = 2
CONFIG_MINOR_VERSION = 1

CONF_SERIAL_ID = "serial_id"
CONF_PIN_CODE = "pin_code"
CONF_API_KEY = "api_key"
CONF_SECRET_KEY = "secret_key"
CONF_ALARMPANEL_ACTIONTYPE_CODE = "alarmpanel_actiontype_code"
CONF_ALARMPANEL_ACTIONTYPE_CODE_OPTIONS = [
    "never",
    "disarm",
    "always",
]
CONF_ALARMPANEL_CODE = "alarmpanel_code"

DEFAULT_SCAN_INTERVAL = 300

HA_CLOUD_DOMAIN = ".nabu.casa"

SERVICE_ARM_GROUP = "arm_groups"
SERVICE_DISARMGROUP = "disarm_groups"
SERVICE_REGISTER_WEBHOOK = "register_webhook"
SERVICE_UNREGISTER_WEBHOOK = "unregister_webhook"

INPUT_GROUPS = "group_ids"
