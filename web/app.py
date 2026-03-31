import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, APIRouter, Depends, Request, Body, Query
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.templating import Jinja2Templates

from core.config import get_setting, get_all_settings, save_settings
from core.logging_setup import setup_logging
from core.watchdog import WatchdogThread
from web.shared_state import get_watchdog, set_watchdog, SETTINGS_SCHEMA
from web.auth import require_auth


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    log_file = get_setting("LOG_FILE", "/app/logs/watcharr.log")
    setup_logging(log_file)
    app.state.log_path = log_file

    wd = WatchdogThread(get_setting_fn=get_setting)
    set_watchdog(wd)

    logging.info("[APP] Watcharr ready")
    yield
    # Shutdown
    if wd.status()["running"]:
        wd.stop()


app = FastAPI(lifespan=lifespan)

templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "static")), name="static")


# ----------------------- health (no auth) -----------------------

@app.get("/health")
@app.get("/api/health")
def health():
    return {"status": "ok"}


# ----------------------- API routes (auth via router) -----------------------

api_router = APIRouter(prefix="/api", dependencies=[Depends(require_auth)])


@api_router.get("/status")
def api_status():
    wd = get_watchdog()
    s = wd.status()
    s["container"] = get_setting("QB_CONTAINER")
    s["check_interval"] = get_setting("CHECK_INTERVAL")
    return s


@api_router.post("/start")
def api_start():
    wd = get_watchdog()
    if wd.start():
        return {"status": "started"}
    return JSONResponse({"status": "already running"}, status_code=400)


@api_router.post("/stop")
def api_stop():
    wd = get_watchdog()
    if wd.stop():
        return {"status": "stopping"}
    return JSONResponse({"status": "not running"}, status_code=400)


@api_router.get("/torrents")
def api_torrents():
    wd = get_watchdog()
    return wd.get_torrents()


@api_router.get("/events")
def api_events():
    wd = get_watchdog()
    return wd.events()


@api_router.post("/restart-qbit")
def api_restart_qbit():
    wd = get_watchdog()
    result = wd.restart_qbit()
    code = 200 if result.get("ok") else 500
    return JSONResponse(result, status_code=code)


@api_router.post("/reannounce")
def api_reannounce(data: dict = Body(default={})):
    h = data.get("hash", "")
    if not h:
        return JSONResponse({"error": "missing hash"}, status_code=400)
    wd = get_watchdog()
    ok = wd.reannounce_torrent(h)
    return {"ok": ok}


@api_router.get("/logs/tail")
def api_logs_tail(request: Request, pos: str = Query(default="0"), inode: str = Query(default=None)):
    log_path = request.app.state.log_path
    p = Path(log_path)

    if not p.exists():
        return {"text": "", "pos": 0, "inode": None, "reset": True}

    st = p.stat()
    inode_token = f"{st.st_dev}:{st.st_ino}"

    try:
        pos_int = int(pos)
    except Exception:
        pos_int = 0

    reset = False
    if inode and inode != inode_token:
        reset = True
        pos_int = 0
    elif pos_int > st.st_size:
        reset = True
        pos_int = 0

    with open(p, "rb") as f:
        f.seek(pos_int)
        raw = f.read()
        new_pos = pos_int + len(raw)

    text = raw.decode("utf-8", errors="replace").replace("\r\n", "\n")
    return {"text": text, "pos": new_pos, "inode": inode_token, "reset": reset}


@api_router.get("/settings")
def api_get_settings():
    try:
        values = get_all_settings()
        return {"schema": SETTINGS_SCHEMA, "values": values}
    except Exception as e:
        logging.exception("[SETTINGS] Failed to get settings")
        return JSONResponse({"error": str(e)}, status_code=500)


@api_router.post("/settings")
def api_save_settings(data: dict = Body(default={})):
    valid_keys = set()
    for section in SETTINGS_SCHEMA.values():
        valid_keys.update(section["fields"].keys())

    filtered = {k: str(v) for k, v in data.items() if k in valid_keys}

    if not filtered:
        return {"status": "ok", "message": "No changes."}

    save_settings(filtered)
    return {"status": "ok", "updated": list(filtered.keys()), "message": "Settings saved."}


app.include_router(api_router)


# ----------------------- UI (auth) -----------------------

@app.get("/", response_class=HTMLResponse, dependencies=[Depends(require_auth)])
def home(request: Request):
    return templates.TemplateResponse("ui.html", {"request": request, "api_base": "/api"})
