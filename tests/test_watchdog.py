"""Tests for the core watchdog logic."""

import time
from unittest.mock import patch, MagicMock
import pytest

from core.watchdog import WatchdogThread


DEFAULTS = {
    "QB_URL": "http://localhost:8080/",
    "QB_USERNAME": "admin",
    "QB_PASSWORD": "pass",
    "QB_CONTAINER": "qbittorrent",
    "CHECK_INTERVAL": "60",
    "STALL_TIMEOUT_MIN": "5",
    "STALL_REMOVAL_ENABLED": "false",
}


def make_watchdog(**overrides):
    settings = {**DEFAULTS, **overrides}
    return WatchdogThread(get_setting_fn=lambda key, default=None: settings.get(key, default or ""))


# ---- Status & Events ----

class TestStatusAndEvents:
    def test_initial_status(self):
        wd = make_watchdog()
        s = wd.status()
        assert s["running"] is False
        assert s["dht_nodes"] == 0
        assert s["stalled_count"] == 0
        assert s["restarts"] == 0
        assert s["checks"] == 0
        assert s["uptime"] == 0

    def test_events_empty(self):
        wd = make_watchdog()
        assert wd.events() == []

    def test_add_event_appears(self):
        wd = make_watchdog()
        wd._add_event("test_type", "test message", "test_torrent")
        events = wd.events()
        assert len(events) == 1
        assert events[0]["type"] == "test_type"
        assert events[0]["message"] == "test message"
        assert events[0]["torrent"] == "test_torrent"
        assert "ts" in events[0]

    def test_events_max_200(self):
        wd = make_watchdog()
        for i in range(250):
            wd._add_event("test", f"event {i}")
        assert len(wd.events()) == 200

    def test_events_newest_first(self):
        wd = make_watchdog()
        wd._add_event("first", "first")
        wd._add_event("second", "second")
        events = wd.events()
        assert events[0]["type"] == "second"
        assert events[1]["type"] == "first"


# ---- Stall Detection ----

class TestStallDetection:
    def test_detect_stalled_dl(self):
        wd = make_watchdog()
        torrents = [
            {"name": "file1", "hash": "abc123", "state": "stalledDL"},
            {"name": "file2", "hash": "def456", "state": "downloading"},
        ]
        stalled = wd._handle_stalled(torrents)
        assert len(stalled) == 1
        assert stalled[0]["name"] == "file1"

    def test_detect_stalled_up(self):
        wd = make_watchdog()
        torrents = [{"name": "file1", "hash": "abc123", "state": "stalledUP"}]
        stalled = wd._handle_stalled(torrents)
        assert len(stalled) == 1

    def test_no_stalled(self):
        wd = make_watchdog()
        torrents = [
            {"name": "file1", "hash": "abc123", "state": "downloading"},
            {"name": "file2", "hash": "def456", "state": "uploading"},
        ]
        stalled = wd._handle_stalled(torrents)
        assert len(stalled) == 0

    def test_stalled_sends_reannounce(self):
        wd = make_watchdog()
        wd._session = MagicMock()
        torrents = [{"name": "file1", "hash": "abc123", "state": "stalledDL"}]
        wd._handle_stalled(torrents)
        # Should have called reannounce, pause, resume
        assert wd._session.post.call_count == 3
        calls = [c[0][0] for c in wd._session.post.call_args_list]
        assert any("reannounce" in c for c in calls)
        assert any("pause" in c for c in calls)
        assert any("resume" in c for c in calls)


# ---- Metadata Stuck Detection ----

class TestMetadataStuck:
    def test_metadl_with_zero_dht(self):
        wd = make_watchdog()
        wd._session = MagicMock()
        torrents = [{"name": "file1", "hash": "abc123", "state": "metaDL"}]
        stuck = wd._handle_metadata_stuck(torrents, dht_nodes=0)
        assert len(stuck) == 1

    def test_metadl_with_healthy_dht(self):
        wd = make_watchdog()
        torrents = [{"name": "file1", "hash": "abc123", "state": "metaDL"}]
        stuck = wd._handle_metadata_stuck(torrents, dht_nodes=150)
        assert len(stuck) == 0

    def test_non_metadl_with_zero_dht(self):
        wd = make_watchdog()
        torrents = [{"name": "file1", "hash": "abc123", "state": "downloading"}]
        stuck = wd._handle_metadata_stuck(torrents, dht_nodes=0)
        assert len(stuck) == 0


# ---- Stall Removal Tracking ----

class TestStallRemoval:
    def test_disabled_by_default(self):
        wd = make_watchdog()
        wd._session = MagicMock()
        torrents = [{"name": "file1", "hash": "abc123", "state": "stalledDL"}]
        wd._process_stalled_for_removal(torrents)
        # Should not track when disabled
        assert len(wd._stalled_tracker) == 0

    def test_tracks_when_enabled(self):
        wd = make_watchdog(STALL_REMOVAL_ENABLED="true")
        torrents = [{"name": "file1", "hash": "abc123", "state": "stalledDL"}]
        wd._process_stalled_for_removal(torrents)
        assert "abc123" in wd._stalled_tracker

    def test_removes_after_timeout(self):
        wd = make_watchdog(STALL_REMOVAL_ENABLED="true", STALL_TIMEOUT_MIN="0")
        wd._session = MagicMock()
        # First pass: start tracking
        torrents = [{"name": "file1", "hash": "abc123", "state": "stalledDL"}]
        wd._process_stalled_for_removal(torrents)
        # Backdate the first_seen so it exceeds timeout
        wd._stalled_tracker["abc123"]["first_seen"] = time.time() - 120
        # Second pass: should remove
        wd._process_stalled_for_removal(torrents)
        # Should have called delete endpoint
        wd._session.post.assert_called()
        delete_calls = [c for c in wd._session.post.call_args_list
                        if "delete" in c[0][0]]
        assert len(delete_calls) == 1

    def test_recovery_clears_tracker(self):
        wd = make_watchdog(STALL_REMOVAL_ENABLED="true")
        torrents = [{"name": "file1", "hash": "abc123", "state": "stalledDL"}]
        wd._process_stalled_for_removal(torrents)
        assert "abc123" in wd._stalled_tracker
        # Torrent recovers (not in stalled list anymore)
        wd._process_stalled_for_removal([])
        assert "abc123" not in wd._stalled_tracker


# ---- Container Restart ----

class TestContainerRestart:
    def _get_module(self):
        """Get the actual module that WatchdogThread's code references."""
        import sys
        return sys.modules["core.watchdog"]

    def test_restart_without_docker(self):
        wd_mod = self._get_module()
        original = wd_mod._docker_available
        wd_mod._docker_available = False
        try:
            wd = make_watchdog()
            result = wd._restart_container()
            assert result["ok"] is False
            assert "not available" in result["error"]
        finally:
            wd_mod._docker_available = original

    def test_restart_success(self):
        wd_mod = self._get_module()
        original_avail = wd_mod._docker_available
        original_docker = getattr(wd_mod, "docker", None)
        wd_mod._docker_available = True

        mock_docker = MagicMock()
        mock_container = MagicMock()
        mock_docker.DockerClient.return_value.containers.get.return_value = mock_container
        wd_mod.docker = mock_docker

        try:
            wd = make_watchdog()
            result = wd._restart_container()
            assert result["ok"] is True
            mock_container.restart.assert_called_once()
            assert wd._status["restarts"] == 1
        finally:
            wd_mod._docker_available = original_avail
            if original_docker is not None:
                wd_mod.docker = original_docker

    def test_restart_container_not_found(self):
        wd_mod = self._get_module()
        original_avail = wd_mod._docker_available
        original_docker = getattr(wd_mod, "docker", None)
        wd_mod._docker_available = True

        mock_docker = MagicMock()
        not_found = type("NotFound", (Exception,), {})
        mock_docker.errors.NotFound = not_found
        mock_docker.DockerClient.return_value.containers.get.side_effect = not_found("not found")
        wd_mod.docker = mock_docker

        try:
            wd = make_watchdog()
            result = wd._restart_container()
            assert result["ok"] is False
        finally:
            wd_mod._docker_available = original_avail
            if original_docker is not None:
                wd_mod.docker = original_docker


# ---- Start / Stop ----

class TestStartStop:
    def test_start_sets_running(self):
        wd = make_watchdog()
        with patch.object(wd, "_run"):
            result = wd.start()
        assert result is True
        assert wd._status["running"] is True
        assert wd._status["started_at"] is not None

    def test_stop_when_not_running(self):
        wd = make_watchdog()
        result = wd.stop()
        assert result is False

    def test_stop_when_running(self):
        wd = make_watchdog()
        wd._status["running"] = True
        result = wd.stop()
        assert result is True
        assert wd._stop_event.is_set()

    def test_uptime_when_running(self):
        wd = make_watchdog()
        wd._status["running"] = True
        wd._status["started_at"] = time.time() - 120
        s = wd.status()
        assert s["uptime"] >= 119  # allow small timing variance

    def test_uptime_zero_when_stopped(self):
        wd = make_watchdog()
        s = wd.status()
        assert s["uptime"] == 0


# ---- Reannounce ----

class TestReannounce:
    def test_reannounce_torrent(self):
        wd = make_watchdog()
        wd._session = MagicMock()
        result = wd.reannounce_torrent("abc123def456")
        assert result is True
        wd._session.post.assert_called_once()
        events = wd.events()
        assert len(events) == 1
        assert events[0]["type"] == "reannounce"
