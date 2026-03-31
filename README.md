# Watcharr

[![CI](https://github.com/reedylab/watcharr/actions/workflows/ci.yml/badge.svg)](https://github.com/reedylab/watcharr/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

A self-hosted watchdog for **qBittorrent** that automatically detects stalled torrents, monitors DHT network health, and restarts your qBittorrent container when things go wrong. Comes with a built-in dark-themed web dashboard for real-time monitoring and configuration.

---

## Features

- **Stall Detection** — Continuously monitors qBittorrent for torrents stuck in `stalledDL`, `stalledUP`, or `metaDL` states
- **Automatic Recovery** — Attempts reannounce + pause/resume cycles on stalled torrents before escalating
- **DHT Health Monitoring** — Tracks DHT node count to detect network connectivity issues; zero DHT nodes + stalled torrents triggers a container restart
- **Container Restart** — Automatically restarts your qBittorrent Docker container via the Docker socket when recovery is needed
- **Stall Timeout & Removal** — Optionally removes torrents that remain stalled beyond a configurable timeout (disabled by default)
- **Web Dashboard** — Real-time dark-themed UI with status cards, event timeline, torrent table, live log viewer, and settings editor
- **Live Log Tailing** — Byte-offset log streaming in the browser with automatic scroll-pinning
- **Hot-Reloadable Settings** — Change any setting from the web UI without restarting the container; the watchdog picks up changes on the next check cycle
- **Layered Configuration** — Settings priority: Web UI (JSON file) > environment variables > built-in defaults
- **Optional Basic Auth** — Protect the dashboard with username/password when exposed beyond your local network
- **Health Check** — Built-in `/api/health` endpoint with Docker HEALTHCHECK for monitoring
- **Responsive Design** — Dashboard works on desktop and mobile

---

## Quick Start

### Prerequisites

- **Docker** and **Docker Compose**
- A running **qBittorrent** instance with the Web UI enabled

### 1. Clone the repository

```bash
git clone https://github.com/reedylab/watcharr.git
cd watcharr
```

### 2. Create your environment file

```bash
cp .env.example .env
```

Edit `.env` with your actual values:

```env
# qBittorrent connection
QB_URL=http://your-qbittorrent-ip:8080/
QB_USERNAME=admin
QB_PASSWORD=your-password
QB_CONTAINER=qbittorrent

# Watchdog settings
CHECK_INTERVAL=60

# Optional: protect the dashboard with basic auth
# AUTH_USERNAME=admin
# AUTH_PASSWORD=changeme
```

### 3. Start the container

```bash
docker compose up -d
```

### 4. Open the dashboard

Navigate to **http://your-server-ip:5035** and click **Start** to begin monitoring.

---

## Configuration

Watcharr uses a three-layer configuration system. Each layer overrides the one below it:

```
1. Web UI settings (saved to /app/data/settings.json)   ← highest priority
2. Environment variables (.env file)
3. Built-in defaults                                     ← lowest priority
```

This means you can set initial values via environment variables, then fine-tune from the web UI without restarting the container.

### Environment Variables

| Variable | Default | Description |
|---|---|---|
| `QB_URL` | `http://localhost:8080/` | qBittorrent Web UI URL |
| `QB_USERNAME` | `admin` | qBittorrent username |
| `QB_PASSWORD` | *(empty)* | qBittorrent password |
| `QB_CONTAINER` | `qbittorrent` | Docker container name to restart |
| `CHECK_INTERVAL` | `60` | Seconds between watchdog checks |
| `STALL_TIMEOUT_MIN` | `5` | Minutes before a stalled torrent is removed (when auto-removal is enabled) |
| `STALL_REMOVAL_ENABLED` | `false` | Enable automatic removal of stalled torrents after timeout |
| `AUTH_USERNAME` | *(empty)* | Dashboard username (basic auth disabled when empty) |
| `AUTH_PASSWORD` | *(empty)* | Dashboard password (basic auth disabled when empty) |
| `LOG_FILE` | `/app/logs/watcharr.log` | Path to the log file inside the container |
| `SETTINGS_FILE` | `/app/data/settings.json` | Path to the persisted settings file |

### Docker Compose

```yaml
services:
  watcharr:
    build:
      context: .
    container_name: watcharr
    restart: unless-stopped
    ports:
      - "5035:5035"
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
      - watcharr-data:/app/data
      - watcharr-logs:/app/logs
    env_file:
      - .env

volumes:
  watcharr-data:
  watcharr-logs:
```

#### Volumes

| Mount | Purpose |
|---|---|
| `/var/run/docker.sock` | Required for Watcharr to restart the qBittorrent container |
| `watcharr-data` | Persists settings across container restarts |
| `watcharr-logs` | Persists log files |

> **Note:** The Docker socket mount gives Watcharr the ability to restart containers. It only uses this to restart the container specified by `QB_CONTAINER`.

---

## Security

Watcharr's dashboard has **no authentication by default**. If your instance is only accessible on a trusted local network, this is fine. If you're exposing it beyond your LAN:

1. **Set basic auth** via `AUTH_USERNAME` and `AUTH_PASSWORD` environment variables, or
2. **Use a reverse proxy** (Nginx, Caddy, Traefik) with its own authentication layer

The `/api/health` endpoint is always accessible (bypasses auth) so Docker health checks continue to work.

---

## How It Works

Every `CHECK_INTERVAL` seconds, the watchdog runs through this decision loop:

```
1. Fetch torrent list from qBittorrent API
2. Fetch transfer info (DHT node count)
3. Identify stalled torrents (stalledDL, stalledUP states)
4. Identify metadata-stuck torrents (metaDL state + 0 DHT nodes)
5. For each stalled/stuck torrent:
   a. Send reannounce request
   b. Pause then resume the torrent
6. If (stalled OR metadata-stuck) AND DHT nodes == 0:
   → Restart qBittorrent container
   → Wait 30 seconds before next check
7. If auto-removal is enabled:
   → Track how long each torrent has been stalled
   → Remove torrents exceeding the stall timeout
```

---

## API Reference

All endpoints are under `/api`. Responses are JSON.

### Health

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/health` | Returns `{"status": "ok"}` — always accessible, bypasses auth |

### Control

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/status` | Watchdog status: running state, DHT nodes, stalled count, uptime, restart count, check count |
| `POST` | `/api/start` | Start the watchdog |
| `POST` | `/api/stop` | Stop the watchdog |

### Data

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/torrents` | Current torrent list (proxied from qBittorrent) |
| `GET` | `/api/events` | Last 200 watchdog events (stalls, restarts, removals, recoveries) |
| `GET` | `/api/logs/tail?pos=0&inode=` | Incremental log tail using byte offsets; supports log rotation detection via inode tracking |

### Actions

| Method | Endpoint | Body | Description |
|---|---|---|---|
| `POST` | `/api/restart-qbit` | — | Manually restart the qBittorrent container |
| `POST` | `/api/reannounce` | `{"hash": "..."}` | Manually reannounce a specific torrent |

### Settings

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/settings` | Returns the settings schema (field types, labels, options) and current values |
| `POST` | `/api/settings` | Save settings. Body is a JSON object of key-value pairs. Only known keys are accepted. |

---

## Project Structure

```
watcharr/
├── .github/workflows/ci.yml   # GitHub Actions CI
├── docker-compose.yml          # Container orchestration
├── Dockerfile                  # Python 3.11-slim image
├── entrypoint.sh               # Creates data/log dirs, starts uvicorn
├── requirements.txt            # Python dependencies
├── .env.example                # Environment template (safe to commit)
├── VERSION                     # Semantic version
├── LICENSE                     # MIT
│
├── core/
│   ├── config.py               # Layered settings: JSON > env > defaults
│   ├── logging_setup.py        # Dual-output logging (file + console)
│   └── watchdog.py             # WatchdogThread: monitoring loop + recovery logic
│
├── web/
│   ├── __init__.py              # Package marker
│   ├── app.py                   # FastAPI app, lifespan, all routes
│   ├── auth.py                  # Basic Auth dependency (optional)
│   ├── shared_state.py          # Watchdog global + settings schema
│   ├── templates/
│   │   └── ui.html              # Dashboard HTML shell
│   └── static/
│       ├── ui.js                # Client-side logic: polling, events, settings editor
│       └── style.css            # Dark theme, responsive layout
│
└── tests/
    ├── test_watchdog.py         # Core watchdog logic tests
    └── test_api.py              # API + auth tests
```

---

## Development

### Running locally (without Docker)

```bash
# Create a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Set required environment variables
export QB_URL="http://your-qbittorrent-ip:8080/"
export QB_USERNAME="admin"
export QB_PASSWORD="your-password"
export QB_CONTAINER="qbittorrent"

# Start the development server
uvicorn web.app:app --host 0.0.0.0 --port 5035 --workers 1
```

The dashboard will be available at `http://localhost:5035`.

> **Note:** Container restart functionality requires access to the Docker socket. When running outside Docker, make sure the Docker socket is accessible or expect restart operations to fail gracefully.

### Running tests

```bash
pip install pytest
python -m pytest tests/ -v
```

### Rebuilding the Docker image

```bash
docker compose build --no-cache
docker compose up -d
```

---

## Contributing

Contributions are welcome. To get started:

1. Fork the repository
2. Create a feature branch: `git checkout -b my-feature`
3. Make your changes
4. Run tests: `python -m pytest tests/ -v`
5. Test locally with Docker: `docker compose up --build`
6. Open a pull request

Please keep changes focused and include a clear description of what changed and why.

---

## License

[MIT](LICENSE)
