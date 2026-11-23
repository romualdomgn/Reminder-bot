from contextlib import asynccontextmanager
import hashlib
from pathlib import Path
import re
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from database import engine, init_db
from .routes_notifications import router as notifications_router
from .routes_reminders import router as reminders_router
from .routes_settings import router as settings_router
from .routes_users import router as users_router

STATIC_DIR = Path(__file__).resolve().parent / "static"
_ASSET_VER_RE = re.compile(r"\?v=[^\"'\s>]+")
_ASSET_CACHE: dict[str, object] = {"mtime": -1.0, "version": "1"}

CSP_POLICY = (
    "default-src 'self'; "
    "script-src 'self' https://telegram.org; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; "
    "connect-src 'self'"
)


def _get_static_asset_version() -> str:
    files = sorted(p for p in STATIC_DIR.glob("*") if p.is_file())
    latest_mtime = max((p.stat().st_mtime for p in files), default=0.0)
    if latest_mtime == _ASSET_CACHE["mtime"]:
        return str(_ASSET_CACHE["version"])
    hasher = hashlib.sha256()
    for p in files:
        hasher.update(p.name.encode("utf-8"))
        hasher.update(p.read_bytes())
    ver = hasher.hexdigest()[:10]
    _ASSET_CACHE["mtime"] = latest_mtime
    _ASSET_CACHE["version"] = ver
    return ver


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await init_db()
    yield
    await engine.dispose()


app = FastAPI(
    title="Reminder Bot Mini App",
    docs_url=None,
    redoc_url=None,
    lifespan=lifespan,
)


@app.middleware("http")
async def security_and_cache_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["Content-Security-Policy"] = CSP_POLICY
    if request.url.path in ("/", "/index.html") or request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


app.include_router(reminders_router)
app.include_router(notifications_router)
app.include_router(users_router)
app.include_router(settings_router)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.get("/")
async def index() -> HTMLResponse:
    raw_html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    ver = _get_static_asset_version()
    rendered = _ASSET_VER_RE.sub(f"?v={ver}", raw_html)
    return HTMLResponse(content=rendered)
