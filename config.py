import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
if not BOT_TOKEN:
    raise ValueError("Не задан TELEGRAM_BOT_TOKEN в файле .env")


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

# Переменные для раздела /info
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
