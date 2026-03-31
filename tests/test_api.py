"""Tests for the FastAPI endpoints and auth."""

import os
import sys
import base64
from unittest.mock import patch, MagicMock
import pytest
from starlette.testclient import TestClient


@pytest.fixture(autouse=True)
def clean_env(tmp_path):
    """Ensure auth env vars are clean and paths are writable between tests."""
    for key in ("AUTH_USERNAME", "AUTH_PASSWORD"):
        os.environ.pop(key, None)
    os.environ["LOG_FILE"] = str(tmp_path / "watcharr.log")
    os.environ["SETTINGS_FILE"] = str(tmp_path / "settings.json")
    # Force reimport of web modules to pick up new env (auth reads at import time)
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
def client():
    """Create TestClient without auth."""
    from web.app import app
    with TestClient(app) as c:
        yield c


@pytest.fixture
def auth_client():
    """Create TestClient with auth enabled."""
    os.environ["AUTH_USERNAME"] = "testuser"
    os.environ["AUTH_PASSWORD"] = "testpass"
    for mod in list(sys.modules):
        if mod.startswith("web"):
            del sys.modules[mod]
    from web.app import app
    with TestClient(app) as c:
        yield c


def _basic_auth_header(user, password):
    creds = base64.b64encode(f"{user}:{password}".encode()).decode()
    return {"Authorization": f"Basic {creds}"}


# ---- Health ----

class TestHealth:
    def test_health_ok(self, client):
        r = client.get("/api/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"

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
        data = r.json()
        assert "running" in data
        assert "dht_nodes" in data
        assert "stalled_count" in data

    def test_start_stop(self, client):
        r = client.post("/api/start")
        assert r.status_code == 200
        # Verify running
        r = client.get("/api/status")
        assert r.json()["running"] is True
        # Stop
        r = client.post("/api/stop")
        assert r.status_code == 200


# ---- Events ----

class TestEventsEndpoint:
    def test_events_returns_list(self, client):
        r = client.get("/api/events")
        assert r.status_code == 200
        assert isinstance(r.json(), list)


# ---- Settings ----

class TestSettingsEndpoint:
    def test_get_settings(self, client):
        r = client.get("/api/settings")
        assert r.status_code == 200
        data = r.json()
        assert "schema" in data
        assert "values" in data

    def test_post_invalid_key(self, client):
        r = client.post("/api/settings", json={"NONEXISTENT_KEY": "value"})
        assert r.status_code == 200
        assert r.json()["message"] == "No changes."
