import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from urllib.parse import parse_qsl
from fastapi import Header, HTTPException

from config import BOT_TOKEN
from database import is_admin_id, is_user_allowed

INIT_DATA_MAX_AGE_SECONDS = 86400  # 24 часа


@dataclass(frozen=True)
class WebAppUser:
    user_id: int
    first_name: str
    username: str
    is_admin: bool


def _parse_and_verify_init_data(init_data: str) -> tuple[int, str, str]:
    if not init_data:
        raise HTTPException(status_code=401, detail="Отсутствует подпись Telegram initData")

    pairs = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = pairs.pop("hash", None)
    if not received_hash:
        raise HTTPException(status_code=401, detail="Некорректная подпись initData")

    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
    secret_key = hmac.new(b"WebAppData", BOT_TOKEN.encode("utf-8"), hashlib.sha256).digest()
    expected_hash = hmac.new(
        secret_key, data_check_string.encode("utf-8"), hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(expected_hash, received_hash):
        raise HTTPException(status_code=401, detail="Подпись Telegram initData не прошла проверку")

    try:
        auth_date = int(pairs.get("auth_date", "0"))
    except ValueError:
        raise HTTPException(status_code=401, detail="Некорректная дата авторизации")

    if auth_date <= 0 or (time.time() - auth_date) > INIT_DATA_MAX_AGE_SECONDS:
        raise HTTPException(status_code=401, detail="Сессия Mini App устарела, откройте заново")

    raw_user = pairs.get("user")
    if not raw_user:
        raise HTTPException(status_code=401, detail="В initData отсутствуют данные пользователя")

    try:
        user_obj = json.loads(raw_user)
        uid = int(user_obj["id"])
    except Exception:
        raise HTTPException(status_code=401, detail="Некорректные данные пользователя")

    return uid, str(user_obj.get("first_name", "")), str(user_obj.get("username", ""))


async def get_current_user(
    x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
) -> WebAppUser:
    uid, first_name, username = _parse_and_verify_init_data(x_telegram_init_data or "")

    if not await is_user_allowed(uid):
        raise HTTPException(status_code=403, detail="У Вас нет доступа к боту")

    return WebAppUser(
        user_id=uid,
        first_name=first_name,
        username=username,
        is_admin=is_admin_id(uid),
    )
