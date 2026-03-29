"""Watchdog thread: monitors qBittorrent for stalled/stuck torrents."""

import threading
import time
import logging
import collections
import traceback

import requests

_docker_available = False
try:
    import docker
    _docker_available = True
except ImportError:
    pass


class WatchdogThread:
    def __init__(self, get_setting_fn):
        self._get = get_setting_fn
        self._thread = None
        self._stop_event = threading.Event()
        self._events = collections.deque(maxlen=200)
        self._status = {
            "running": False,
            "dht_nodes": 0,
            "stalled_count": 0,
            "metadata_stuck": 0,
            "restarts": 0,
            "checks": 0,
            "started_at": None,
        }
        self._session = requests.Session()
        self._logged_in = False
        self._stalled_tracker = {}

    # ---- public API ----

    def start(self):
        if self._thread and self._thread.is_alive():
            return False
        self._stop_event.clear()
        self._status["running"] = True
        self._status["started_at"] = time.time()
        self._status["restarts"] = 0
        self._status["checks"] = 0
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        logging.info("[WATCHDOG] Started")
        self._add_event("started", "Watchdog started")
        return True

    def stop(self):
        if not self._status["running"]:
            return False
        self._stop_event.set()
        self._status["running"] = False
        logging.info("[WATCHDOG] Stop requested")
        self._add_event("stopped", "Watchdog stopped")
        return True

    def status(self) -> dict:
        s = dict(self._status)
        if s["started_at"] and s["running"]:
            s["uptime"] = int(time.time() - s["started_at"])
        else:
            s["uptime"] = 0
        return s

    def events(self) -> list:
        return list(self._events)

    def get_torrents(self) -> list:
        """Proxy: return current torrent list from qBit."""
        try:
            r = self._api_get("/api/v2/torrents/info")
            return r.json() if r and r.ok else []
        except Exception:
            return []

    def restart_qbit(self) -> dict:
        """Manual restart from UI."""
        return self._restart_container()

    def reannounce_torrent(self, torrent_hash: str) -> bool:
        try:
            url = self._get("QB_URL").rstrip("/")
            self._session.post(f"{url}/api/v2/torrents/reannounce", data={"hashes": torrent_hash})
            self._add_event("reannounce", f"Manual reannounce: {torrent_hash[:12]}...")
            return True
        except Exception:
            return False

    # ---- internal ----

    def _add_event(self, event_type: str, message: str, torrent_name: str = ""):
        self._events.appendleft({
            "ts": time.time(),
            "type": event_type,
            "message": message,
            "torrent": torrent_name,
        })

    def _login(self) -> bool:
        url = self._get("QB_URL").rstrip("/")
        user = self._get("QB_USERNAME")
        pw = self._get("QB_PASSWORD")
        try:
            r = self._session.post(f"{url}/api/v2/auth/login", data={"username": user, "password": pw}, timeout=10)
            if r.ok:
                self._logged_in = True
                logging.info("[WATCHDOG] qBit login OK")
                return True
            else:
                logging.warning("[WATCHDOG] qBit login failed: %s", r.status_code)
                return False
        except Exception as e:
            logging.error("[WATCHDOG] qBit login error: %s", e)
            return False

    def _api_get(self, path: str):
        url = self._get("QB_URL").rstrip("/") + path
        try:
            r = self._session.get(url, timeout=10)
            if r.status_code == 403:
                if self._login():
                    r = self._session.get(url, timeout=10)
            return r
        except Exception as e:
            logging.error("[WATCHDOG] API GET %s failed: %s", path, e)
            return None

    def _get_dht_nodes(self) -> int:
        r = self._api_get("/api/v2/transfer/info")
        if r and r.ok:
            return r.json().get("dht_nodes", 0)
        return 0

    def _restart_container(self) -> dict:
        container_name = self._get("QB_CONTAINER")
        if not _docker_available:
            msg = "Docker SDK not available"
            logging.error("[WATCHDOG] %s", msg)
            return {"ok": False, "error": msg}
        try:
            client = docker.DockerClient(base_url="unix://var/run/docker.sock")
            container = client.containers.get(container_name)
            container.restart()
            self._status["restarts"] += 1
            msg = f"Restarted container: {container_name}"
            logging.info("[WATCHDOG] %s", msg)
            self._add_event("restart", msg)
            return {"ok": True, "message": msg}
        except docker.errors.NotFound:
            msg = f"Container '{container_name}' not found"
            logging.error("[WATCHDOG] %s", msg)
            self._add_event("error", msg)
            return {"ok": False, "error": msg}
        except Exception as e:
            msg = f"Docker restart failed: {e}"
            logging.error("[WATCHDOG] %s", msg)
            self._add_event("error", msg)
            return {"ok": False, "error": str(e)}

    def _handle_stalled(self, torrents) -> list:
        stalled = [t for t in torrents
                   if t.get("state", "").lower().startswith("stalled")
                   or t.get("state", "").lower().endswith("stalled")]
        for t in stalled:
            name = t.get("name", "UNKNOWN")
            h = t.get("hash", "")
            logging.info("[WATCHDOG] Stalled: %s", name)
            url = self._get("QB_URL").rstrip("/")
            try:
                self._session.post(f"{url}/api/v2/torrents/reannounce", data={"hashes": h})
                self._session.post(f"{url}/api/v2/torrents/pause", data={"hashes": h})
                self._session.post(f"{url}/api/v2/torrents/resume", data={"hashes": h})
            except Exception:
                pass
        return stalled

    def _handle_metadata_stuck(self, torrents, dht_nodes) -> list:
        stuck = [t for t in torrents
                 if t.get("state", "").lower() == "metadl" and dht_nodes == 0]
        for t in stuck:
            name = t.get("name", "UNKNOWN")
            h = t.get("hash", "")
            logging.info("[WATCHDOG] Metadata stuck: %s", name)
            url = self._get("QB_URL").rstrip("/")
            try:
                self._session.post(f"{url}/api/v2/torrents/reannounce", data={"hashes": h})
                self._session.post(f"{url}/api/v2/torrents/pause", data={"hashes": h})
                self._session.post(f"{url}/api/v2/torrents/resume", data={"hashes": h})
            except Exception:
                pass
        return stuck

    def _process_stalled_for_removal(self, stalled_torrents):
        """Track stalled torrents and remove after timeout (when enabled)."""
        enabled = self._get("STALL_REMOVAL_ENABLED") == "true"
        if not enabled:
            return

        timeout_min = int(self._get("STALL_TIMEOUT_MIN") or 5)
        timeout_sec = timeout_min * 60
        now = time.time()
        updated = {}

        for t in stalled_torrents:
            h = t["hash"]
            name = t.get("name", "UNKNOWN")
            if h not in self._stalled_tracker:
                self._stalled_tracker[h] = {"first_seen": now, "name": name}
                logging.info("[WATCHDOG] Tracking stalled: %s", name)
                self._add_event("tracking", f"Tracking stalled torrent", name)
            else:
                first_seen = self._stalled_tracker[h]["first_seen"]
                elapsed = now - first_seen
                if elapsed >= timeout_sec:
                    logging.info("[WATCHDOG] Removing stalled torrent after %dm: %s", int(elapsed / 60), name)
                    self._add_event("removed", f"Removed after {int(elapsed/60)}m stall", name)
                    self._remove_torrent(h)
                    continue
            updated[h] = self._stalled_tracker[h]

        # Clean up recovered
        for h in list(self._stalled_tracker):
            if h not in updated:
                name = self._stalled_tracker[h]["name"]
                logging.info("[WATCHDOG] Recovered: %s", name)
                self._add_event("recovered", "Torrent recovered", name)

        self._stalled_tracker.clear()
        self._stalled_tracker.update(updated)

    def _remove_torrent(self, torrent_hash: str):
        url = self._get("QB_URL").rstrip("/")
        try:
            self._session.post(f"{url}/api/v2/torrents/delete",
                               data={"hashes": torrent_hash, "deleteFiles": "true"})
        except Exception as e:
            logging.error("[WATCHDOG] Remove torrent failed: %s", e)

    def _run(self):
        logging.info("[WATCHDOG] Thread running, attempting login...")
        if not self._login():
            logging.error("[WATCHDOG] Initial login failed, will retry in loop")

        interval = int(self._get("CHECK_INTERVAL") or 60)

        while not self._stop_event.is_set():
            try:
                torrents = self.get_torrents()
                dht_nodes = self._get_dht_nodes()

                stalled = self._handle_stalled(torrents)
                metadata_stuck = self._handle_metadata_stuck(torrents, dht_nodes)

                self._status["dht_nodes"] = dht_nodes
                self._status["stalled_count"] = len(stalled)
                self._status["metadata_stuck"] = len(metadata_stuck)
                self._status["checks"] += 1

                logging.info("[WATCHDOG] Check #%d — DHT: %d, Stalled: %d, MetaStuck: %d",
                             self._status["checks"], dht_nodes, len(stalled), len(metadata_stuck))

                if (stalled or metadata_stuck) and dht_nodes == 0:
                    logging.warning("[WATCHDOG] Stalled + 0 DHT → restarting qBittorrent")
                    self._add_event("restart_trigger", f"Stalled + 0 DHT, restarting container")
                    self._restart_container()
                    self._stop_event.wait(30)
                    continue

                if stalled:
                    for t in stalled:
                        self._add_event("stall_detected", "Torrent stalled", t.get("name", ""))

                # Process stall removal (if enabled)
                self._process_stalled_for_removal(stalled + metadata_stuck)

            except Exception as e:
                logging.error("[WATCHDOG] Loop error: %s\n%s", e, traceback.format_exc())
                self._add_event("error", str(e))

            # Re-read interval in case it changed
            try:
                interval = int(self._get("CHECK_INTERVAL") or 60)
            except (ValueError, TypeError):
                interval = 60

            self._stop_event.wait(interval)

        self._status["running"] = False
        logging.info("[WATCHDOG] Thread stopped")
