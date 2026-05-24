# Watcharr

Self-hosted watchdog for qBittorrent. Detects stalled torrents (`stalledDL`/`stalledUP`/`metaDL`), monitors DHT health, and runs graduated recovery (reannounce → pause/resume → container restart). Ships with an embedded FastAPI dashboard for live monitoring so you don't need a separate Grafana panel.

## Deploy

- **Primary host:** `home-media01`
- **Compose file:** `docker-compose.yml`
- **Run:** `docker compose up -d --build`
- **Port:** see `docker-compose.yml` (dashboard exposed for LAN access)
- **Container:** `watcharr`

## Architecture

- Python 3.11 + FastAPI in `core/` and `web/`
- Talks to qBittorrent over its Web API (configured in `.env`)
- No external DB — state kept in-container/in-memory; restart-safe via re-querying qBittorrent

## Test / validation

- `pytest` from project root (suite in `tests/`, config in `pytest.ini`)
- Dashboard URL should show torrent counts, DHT health, and recent recovery actions

## Gotchas

- The qBittorrent target is `qbittorrent` (running behind `gluetun` in the host's root `docker-compose.yml`); the Watcharr container must be able to reach it via the host's bridge network.
- `entrypoint.sh` adjusts perms — if changing how the container starts, check that file first.

## Project-specific git conventions

Public mirror under `reedylab` GitHub org. See global `## Git Credentials` for auth.
