import ctypes
import gc
import hashlib
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

VERSION_PREFIX = os.getenv("APP_VERSION_PREFIX", "1.4").strip()
VERSION_STATE_FILE = BASE_DIR / ".version_state.json"

_libc = None
_LAST_DELETED_REMINDERS: dict[int, dict[str, Any]] = {}


def set_last_deleted_reminder(user_id: int, data: dict[str, Any]) -> None:
    _LAST_DELETED_REMINDERS[user_id] = data


def pop_last_deleted_reminder(user_id: int) -> dict[str, Any] | None:
    return _LAST_DELETED_REMINDERS.pop(user_id, None)


def clear_last_deleted_reminder(user_id: int) -> None:
    _LAST_DELETED_REMINDERS.pop(user_id, None)


def trim_memory() -> None:
    global _libc
    gc.collect()
    try:
        if _libc is None:
            _libc = ctypes.CDLL("libc.so.6")
        _libc.malloc_trim(0)
    except Exception:
        pass


def get_app_version_info() -> tuple[str, str]:
    py_files = sorted(
        list(BASE_DIR.glob("*.py")) + list((BASE_DIR / "handlers").glob("*.py"))
    )
    hasher = hashlib.sha256()
    latest_mtime = 0.0

    for file_path in py_files:
        try:
            stat = file_path.stat()
            if stat.st_mtime > latest_mtime:
                latest_mtime = stat.st_mtime
            hasher.update(file_path.name.encode("utf-8"))
            hasher.update(file_path.read_bytes())
        except Exception:
            pass

    code_hash = hasher.hexdigest()
    release_date = (
        datetime.fromtimestamp(latest_mtime).strftime("%d.%m.%Y")
        if latest_mtime > 0
        else datetime.now().strftime("%d.%m.%Y")
    )

    build_num = 1
    saved_date = release_date

    if VERSION_STATE_FILE.exists():
        try:
            state = json.loads(VERSION_STATE_FILE.read_text(encoding="utf-8"))
            prev_hash = state.get("hash", "")
            prev_build = int(state.get("build", 1))
            if prev_hash == code_hash:
                build_num = prev_build
                saved_date = state.get("date", release_date)
            else:
                build_num = prev_build + 1
                saved_date = release_date
                VERSION_STATE_FILE.write_text(
                    json.dumps(
                        {"hash": code_hash, "build": build_num, "date": saved_date},
                        ensure_ascii=False,
                    ),
                    encoding="utf-8",
                )
        except Exception:
            pass
    else:
        try:
            VERSION_STATE_FILE.write_text(
                json.dumps(
                    {"hash": code_hash, "build": build_num, "date": saved_date},
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
        except Exception:
            pass

    return f"{VERSION_PREFIX}.{build_num}", saved_date


BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
if not BOT_TOKEN:
    raise ValueError("Не задан TELEGRAM_BOT_TOKEN в файле .env")

TELEGRAM_PROXY = os.getenv("TELEGRAM_PROXY", "").strip()


def _parse_ids(raw_value: str) -> set[int]:
    ids = set()
    for part in raw_value.split(","):
        part = part.strip()
        if part.isdigit():
            ids.add(int(part))
    return ids


ADMIN_IDS: set[int] = _parse_ids(os.getenv("ADMIN_TELEGRAM_ID", ""))
USER_IDS: set[int] = _parse_ids(os.getenv("USER_TELEGRAM_ID", ""))
ALLOWED_IDS: set[int] = ADMIN_IDS | USER_IDS

DEFAULT_TZ_OFFSET_HOURS = int(os.getenv("TZ_OFFSET_HOURS", "5"))

REPOSITORY_URL = (
    os.getenv("repository")
    or os.getenv("REPOSITORY")
    or "https://github.com/"
).strip()

_raw_tg_username = (
    os.getenv("TgUserName")
    or os.getenv("TGUSERNAME")
    or ""
).strip().lstrip("@")
ADMIN_TG_USERNAME = f"@{_raw_tg_username}" if _raw_tg_username else "@admin"

DB_PATH = BASE_DIR / "reminders.db"
DATABASE_URL = f"sqlite+aiosqlite:///{DB_PATH}"
