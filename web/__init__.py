import atexit
import logging
import os
from flask import Flask, request, Response
from core.config import get_setting
from core.logging_setup import setup_logging
from core.watchdog import WatchdogThread
from .blueprints.api import api_bp
from .blueprints.ui import ui_bp


_watchdog = None


def get_watchdog() -> WatchdogThread:
    return _watchdog


def create_app():
    log_file = get_setting("LOG_FILE", "/app/logs/watcharr.log")
    setup_logging(log_file)

    app = Flask(__name__)
    app.config["LOG_PATH"] = log_file

    global _watchdog
    _watchdog = WatchdogThread(get_setting_fn=get_setting)
    app.config["WATCHDOG"] = _watchdog

    @atexit.register
    def shutdown():
        if _watchdog and _watchdog.status()["running"]:
            _watchdog.stop()

    # Optional basic auth
    auth_user = os.environ.get("AUTH_USERNAME", "").strip()
    auth_pass = os.environ.get("AUTH_PASSWORD", "").strip()

    if auth_user and auth_pass:
        @app.before_request
        def check_auth():
            # Health check is always open for Docker HEALTHCHECK
            if request.path == "/api/health":
                return None
            auth = request.authorization
            if not auth or auth.username != auth_user or auth.password != auth_pass:
                return Response(
                    "Authentication required.\n",
                    401,
                    {"WWW-Authenticate": 'Basic realm="Watcharr"'},
                )
        logging.info("[APP] Basic auth enabled (user: %s)", auth_user)

    app.register_blueprint(ui_bp)
    app.register_blueprint(api_bp, url_prefix="/api")

    logging.info("[APP] Watcharr ready")
    return app
