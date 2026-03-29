# web/blueprints/api.py
from flask import Blueprint, current_app, jsonify, request
from pathlib import Path
import logging

from core.config import get_setting, get_all_settings, save_settings, DEFAULTS

api_bp = Blueprint("api", __name__)


# ----------------------- health check -----------------------
@api_bp.get("/health")
def api_health():
    return jsonify({"status": "ok"})


# ----------------------- settings schema -----------------------
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


# ----------------------- control routes -----------------------
@api_bp.get("/status")
def api_status():
    wd = current_app.config["WATCHDOG"]
    s = wd.status()
    s["container"] = get_setting("QB_CONTAINER")
    s["check_interval"] = get_setting("CHECK_INTERVAL")
    return jsonify(s)


@api_bp.post("/start")
def api_start():
    wd = current_app.config["WATCHDOG"]
    if wd.start():
        return jsonify({"status": "started"})
    return jsonify({"status": "already running"}), 400


@api_bp.post("/stop")
def api_stop():
    wd = current_app.config["WATCHDOG"]
    if wd.stop():
        return jsonify({"status": "stopping"})
    return jsonify({"status": "not running"}), 400


# ----------------------- data routes -----------------------
@api_bp.get("/torrents")
def api_torrents():
    wd = current_app.config["WATCHDOG"]
    return jsonify(wd.get_torrents())


@api_bp.get("/events")
def api_events():
    wd = current_app.config["WATCHDOG"]
    return jsonify(wd.events())


@api_bp.post("/restart-qbit")
def api_restart_qbit():
    wd = current_app.config["WATCHDOG"]
    result = wd.restart_qbit()
    code = 200 if result.get("ok") else 500
    return jsonify(result), code


@api_bp.post("/reannounce")
def api_reannounce():
    data = request.get_json() or {}
    h = data.get("hash", "")
    if not h:
        return jsonify({"error": "missing hash"}), 400
    wd = current_app.config["WATCHDOG"]
    ok = wd.reannounce_torrent(h)
    return jsonify({"ok": ok})


# ----------------------- logs tail -----------------------
@api_bp.get("/logs/tail")
def api_logs_tail():
    log_path = current_app.config.get("LOG_PATH", "/app/logs/watcharr.log")
    p = Path(log_path)

    if not p.exists():
        return jsonify({"text": "", "pos": 0, "inode": None, "reset": True})

    st = p.stat()
    inode_token = f"{st.st_dev}:{st.st_ino}"

    try:
        pos = int(request.args.get("pos", "0"))
    except Exception:
        pos = 0
    client_inode = request.args.get("inode")

    reset = False
    if client_inode and client_inode != inode_token:
        reset = True
        pos = 0
    elif pos > st.st_size:
        reset = True
        pos = 0

    with open(p, "rb") as f:
        f.seek(pos)
        data = f.read()
        new_pos = pos + len(data)

    text = data.decode("utf-8", errors="replace").replace("\r\n", "\n")
    return jsonify({"text": text, "pos": new_pos, "inode": inode_token, "reset": reset})


# ----------------------- settings -----------------------
@api_bp.get("/settings")
def api_get_settings():
    try:
        values = get_all_settings()
        return jsonify({"schema": SETTINGS_SCHEMA, "values": values})
    except Exception as e:
        logging.exception("[SETTINGS] Failed to get settings")
        return jsonify({"error": str(e)}), 500


@api_bp.post("/settings")
def api_save_settings():
    data = request.get_json() or {}

    # Filter to only known keys
    valid_keys = set()
    for section in SETTINGS_SCHEMA.values():
        valid_keys.update(section["fields"].keys())

    filtered = {k: str(v) for k, v in data.items() if k in valid_keys}

    if not filtered:
        return jsonify({"status": "ok", "message": "No changes."})

    save_settings(filtered)
    return jsonify({"status": "ok", "updated": list(filtered.keys()), "message": "Settings saved."})
