"""Constants for the Diagral integration."""

DOMAIN = "diagral"
BRAND = "Diagral"

CONFIG_VERSION = 2
CONFIG_MINOR_VERSION = 1

CONF_SERIAL_ID = "serial_id"
CONF_PIN_CODE = "pin_code"
CONF_API_KEY = "api_key"
CONF_SECRET_KEY = "secret_key"
# SHA-256 of the webhook URL this entry registered, to recognise its subscription
CONF_WEBHOOK_URL_HASH = "webhook_url_hash"
CONF_ALARMPANEL_ACTIONTYPE_CODE = "alarmpanel_actiontype_code"
CONF_ALARMPANEL_ACTIONTYPE_CODE_OPTIONS = [
    "never",
    "disarm",
    "always",
]
CONF_ALARMPANEL_CODE = "alarmpanel_code"
ALARMPANEL_CODE_MIN_LENGTH = 4

# Diagral alert codes that mean an intrusion:
# 1130 INTRUSION, 1139 INTRUSION-CONFIRMED, 1141 PREALARM-CONFIRMED
ALARM_INTRUSION_CODES = frozenset({1130, 1139, 1141})

DEFAULT_SCAN_INTERVAL = 300
# A transient read failure is retried with a longer deadline, after a longer
# pause, and the whole refresh never runs into the next poll.
READ_ATTEMPT_TIMEOUTS = (30, 45, 60)
READ_RETRY_PAUSES = (5, 10)
READ_RETRY_BUDGET = DEFAULT_SCAN_INTERVAL // 2
HTTP_SERVER_ERROR = 500
# pydiagral's per-request ceiling: a caller can shorten a deadline, never extend it.
DIAGRAL_REQUEST_TIMEOUT = max(READ_ATTEMPT_TIMEOUTS)

HA_CLOUD_DOMAIN = ".nabu.casa"

SERVICE_ARM_GROUP = "arm_groups"
SERVICE_DISARMGROUP = "disarm_groups"
SERVICE_REGISTER_WEBHOOK = "register_webhook"
SERVICE_UNREGISTER_WEBHOOK = "unregister_webhook"

INPUT_GROUPS = "group_ids"

ISSUE_WEBHOOK_OWNED_ELSEWHERE = "webhook_owned_elsewhere"
