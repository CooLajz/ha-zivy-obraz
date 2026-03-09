from __future__ import annotations

DOMAIN = "zivy_obraz"

CONF_URL = "url"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_TIMEOUT = "timeout"
CONF_OVERDUE_TOLERANCE = "overdue_tolerance"

DEFAULT_SCAN_INTERVAL = 300
DEFAULT_TIMEOUT = 15
DEFAULT_OVERDUE_TOLERANCE = 30

PLATFORMS = ["sensor", "binary_sensor"]