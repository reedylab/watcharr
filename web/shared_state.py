from core.watchdog import WatchdogThread

_watchdog: WatchdogThread | None = None


def get_watchdog() -> WatchdogThread:
    return _watchdog


def set_watchdog(wd: WatchdogThread):
    global _watchdog
    _watchdog = wd


SETTINGS_SCHEMA = {
    "qbittorrent": {
        "label": "qBittorrent",
        "fields": {
            "QB_URL": {"label": "qBittorrent URL", "type": "text", "placeholder": "http://localhost:8080/"},
            "QB_USERNAME": {"label": "Username", "type": "text", "placeholder": "admin"},
            "QB_PASSWORD": {"label": "Password", "type": "password", "placeholder": ""},
            "QB_CONTAINER": {"label": "Docker Container Name", "type": "text", "placeholder": "qbittorrent"},
        }
    },
    "watchdog": {
        "label": "Watchdog",
        "fields": {
            "CHECK_INTERVAL": {"label": "Check Interval (seconds)", "type": "text", "placeholder": "60"},
            "STALL_TIMEOUT_MIN": {"label": "Stall Timeout (minutes)", "type": "text", "placeholder": "5"},
            "STALL_REMOVAL_ENABLED": {"label": "Auto-Remove Stalled", "type": "select", "options": [
                {"value": "false", "label": "Disabled"},
                {"value": "true", "label": "Enabled"},
            ]},
        }
    },
}
