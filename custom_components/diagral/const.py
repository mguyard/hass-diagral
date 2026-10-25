"""Constants for the Diagral integration."""

DOMAIN = "diagral"
BRAND = "Diagral"
# Bus event fired for every webhook; a public contract used in automations
DIAGRAL_EVENT = "DIAGRAL_EVENT"
# Dispatcher signals of a webhook: the global one is kept for existing listeners,
# the entities of an entry only listen to their own central.
WEBHOOK_SIGNAL = "signal-" + DOMAIN + "-webhook-{alarm_type}"
ENTRY_WEBHOOK_SIGNAL = "signal-" + DOMAIN + "-{entry_id}-webhook-{alarm_type}"

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
# Stated rather than left to pydiagral's default: only DIAGRAL is supported.
DIAGRAL_VENDOR = "DIAGRAL"
# A hung cloud must not hold the diagnostics download for a full request timeout.
DIAGNOSTICS_CLOUD_TIMEOUT = 10

HA_CLOUD_DOMAIN = ".nabu.casa"

# Diagral system statuses, as `SystemStatus.status` reports them in lower case
STATUS_OFF = "off"
STATUS_GROUP = "group"
STATUS_TEMPO_GROUP = "tempo_group"
STATUS_PRESENCE = "presence"
# A command is never resent: past this deadline, one status read decides.
COMMAND_TIMEOUT = 30

SERVICE_ARM_GROUP = "arm_groups"
SERVICE_DISARMGROUP = "disarm_groups"
SERVICE_REGISTER_WEBHOOK = "register_webhook"
SERVICE_UNREGISTER_WEBHOOK = "unregister_webhook"

INPUT_GROUPS = "group_ids"

ISSUE_WEBHOOK_OWNED_ELSEWHERE = "webhook_owned_elsewhere"
ISSUE_WEBHOOK_REGISTRATION_FAILED = "webhook_registration_failed"
ISSUE_WEBHOOK_NO_URL = "webhook_no_url"

# State of an entry's webhook, reported by its diagnostic entities
WEBHOOK_CONNECTED = "connected"
WEBHOOK_OWNED_ELSEWHERE = "owned_elsewhere"
WEBHOOK_REGISTRATION_FAILED = "registration_failed"
WEBHOOK_NO_URL = "no_url"
WEBHOOK_UNREGISTERED = "unregistered"
WEBHOOK_STATUSES = (
    WEBHOOK_CONNECTED,
    WEBHOOK_OWNED_ELSEWHERE,
    WEBHOOK_REGISTRATION_FAILED,
    WEBHOOK_NO_URL,
    WEBHOOK_UNREGISTERED,
)
WEBHOOK_STATUS_OF_ISSUE = {
    ISSUE_WEBHOOK_REGISTRATION_FAILED: WEBHOOK_REGISTRATION_FAILED,
    ISSUE_WEBHOOK_NO_URL: WEBHOOK_NO_URL,
}
# A subscription can be taken over or deleted between restarts: check it hourly
WEBHOOK_CHECK_INTERVAL = 3600
