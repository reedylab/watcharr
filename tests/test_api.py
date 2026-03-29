"""Tests for the Flask API endpoints and auth."""

import os
import sys
import base64
import tempfile
from unittest.mock import patch, MagicMock
import pytest


@pytest.fixture(autouse=True)
def clean_env(tmp_path):
    """Ensure auth env vars are clean and paths are writable between tests."""
    for key in ("AUTH_USERNAME", "AUTH_PASSWORD"):
        os.environ.pop(key, None)
    os.environ["LOG_FILE"] = str(tmp_path / "watcharr.log")
    os.environ["SETTINGS_FILE"] = str(tmp_path / "settings.json")
    # Force reimport of web modules to pick up new env (auth is set in create_app)
    # Keep core.* modules intact so other test files can patch them reliably
    for mod in list(sys.modules):
        if mod.startswith("web"):
            del sys.modules[mod]
    yield
    for key in ("AUTH_USERNAME", "AUTH_PASSWORD", "LOG_FILE", "SETTINGS_FILE"):
        os.environ.pop(key, None)
    for mod in list(sys.modules):
        if mod.startswith("web"):
            del sys.modules[mod]


@pytest.fixture
def app():
    """Create app without auth."""
    from web import create_app
    app = create_app()
    app.config["TESTING"] = True
    return app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def auth_app():
    """Create app with auth enabled."""
    os.environ["AUTH_USERNAME"] = "testuser"
    os.environ["AUTH_PASSWORD"] = "testpass"
    from web import create_app
    app = create_app()
    app.config["TESTING"] = True
    return app


@pytest.fixture
def auth_client(auth_app):
    return auth_app.test_client()


def _basic_auth_header(user, password):
    creds = base64.b64encode(f"{user}:{password}".encode()).decode()
    return {"Authorization": f"Basic {creds}"}


# ---- Health ----

class TestHealth:
    def test_health_ok(self, client):
        r = client.get("/api/health")
        assert r.status_code == 200
        assert r.get_json()["status"] == "ok"

    def test_health_bypasses_auth(self, auth_client):
        r = auth_client.get("/api/health")
        assert r.status_code == 200


# ---- Auth ----

class TestAuth:
    def test_no_auth_by_default(self, client):
        r = client.get("/api/status")
        assert r.status_code == 200

    def test_auth_required_when_configured(self, auth_client):
        r = auth_client.get("/api/status")
        assert r.status_code == 401

    def test_auth_valid_credentials(self, auth_client):
        r = auth_client.get("/api/status", headers=_basic_auth_header("testuser", "testpass"))
        assert r.status_code == 200

    def test_auth_wrong_password(self, auth_client):
        r = auth_client.get("/api/status", headers=_basic_auth_header("testuser", "wrong"))
        assert r.status_code == 401

    def test_auth_wrong_username(self, auth_client):
        r = auth_client.get("/api/status", headers=_basic_auth_header("wrong", "testpass"))
        assert r.status_code == 401


# ---- Status ----

class TestStatusEndpoint:
    def test_status_returns_fields(self, client):
        r = client.get("/api/status")
        data = r.get_json()
        assert "running" in data
        assert "dht_nodes" in data
        assert "stalled_count" in data

    def test_start_stop(self, client):
        r = client.post("/api/start")
        assert r.status_code == 200
        # Verify running
        r = client.get("/api/status")
        assert r.get_json()["running"] is True
        # Stop
        r = client.post("/api/stop")
        assert r.status_code == 200


# ---- Events ----

class TestEventsEndpoint:
    def test_events_returns_list(self, client):
        r = client.get("/api/events")
        assert r.status_code == 200
        assert isinstance(r.get_json(), list)


# ---- Settings ----

class TestSettingsEndpoint:
    def test_get_settings(self, client):
        r = client.get("/api/settings")
        assert r.status_code == 200
        data = r.get_json()
        assert "schema" in data
        assert "values" in data

    def test_post_invalid_key(self, client):
        r = client.post("/api/settings", json={"NONEXISTENT_KEY": "value"})
        assert r.status_code == 200
        assert r.get_json()["message"] == "No changes."
