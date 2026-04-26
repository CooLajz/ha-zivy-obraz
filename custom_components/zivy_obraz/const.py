from __future__ import annotations

DOMAIN = "zivy_obraz"

CONF_EXPORT_KEY = "export_key"
CONF_NAME = "name"
CONF_USE_GROUP_FILTER = "use_group_filter"
CONF_GROUP_ID = "group_id"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_TIMEOUT = "timeout"
CONF_OVERDUE_TOLERANCE = "overdue_tolerance"
CONF_OVERDUE_NOTIFICATION = "overdue_notification"

CONF_PUSH_ENABLED = "push_enabled"
CONF_IMPORT_KEY = "import_key"
CONF_LABEL = "label"
CONF_PREFIX = "prefix"
CONF_PREFIX_OVERRIDE = "prefix_override"
CONF_PUSH_INTERVAL = "push_interval"

DEFAULT_SCAN_INTERVAL = 300
DEFAULT_NAME = "Živý Obraz"
DEFAULT_TIMEOUT = 15
DEFAULT_OVERDUE_TOLERANCE = 30
DEFAULT_OVERDUE_NOTIFICATION = True

DEFAULT_PUSH_ENABLED = False
DEFAULT_IMPORT_KEY = ""
DEFAULT_LABEL = "ZivyObraz"
DEFAULT_PREFIX = ""
DEFAULT_PUSH_INTERVAL = 300
DEFAULT_USE_GROUP_FILTER = False

ZIVY_OBRAZ_EXPORT_URL = "https://out.zivyobraz.eu/"
ZIVY_OBRAZ_PUSH_URL = "https://in.zivyobraz.eu/"

MAX_PUSH_URL_LENGTH = 1800

PLATFORMS = ["sensor", "binary_sensor"]

SERVICE_PUSH = "push"

ATTR_ENTRY_ID = "entry_id"
ATTR_NAME = "name"
