from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from database import engine, init_db
from .routes_notifications import router as notifications_router
from .routes_reminders import router as reminders_router
from .routes_settings import router as settings_router
from .routes_users import router as users_router

STATIC_DIR = Path(__file__).resolve().parent / "static"


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

app.include_router(reminders_router)
app.include_router(notifications_router)
app.include_router(users_router)
app.include_router(settings_router)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")
