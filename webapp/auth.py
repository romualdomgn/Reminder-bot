import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from urllib.parse import parse_qsl
from fastapi import Header, HTTPException

from config import BOT_TOKEN
from database import ensure_user_language, is_admin_id, is_user_allowed
from i18n import DEFAULT_LANG, detect_language_from_code, t

INIT_DATA_MAX_AGE_SECONDS = 86400


@dataclass(frozen=True)
class WebAppUser:
    user_id: int
    first_name: str
    username: str
    is_admin: bool
    lang: str = DEFAULT_LANG
    language_code: str = ""


def _parse_and_verify_init_data(init_data: str) -> tuple[int, str, str, str]:
    if not init_data:
        raise HTTPException(status_code=401, detail=t(DEFAULT_LANG, "api_missing_init_data"))

    pairs = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = pairs.pop("hash", None)
    if not received_hash:
        raise HTTPException(status_code=401, detail=t(DEFAULT_LANG, "api_bad_init_data"))

    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
    secret_key = hmac.new(b"WebAppData", BOT_TOKEN.encode("utf-8"), hashlib.sha256).digest()
    expected_hash = hmac.new(secret_key, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(expected_hash, received_hash):
        raise HTTPException(status_code=401, detail=t(DEFAULT_LANG, "api_invalid_sig"))

    raw_user = pairs.get("user")
    detected_lang = DEFAULT_LANG
    user_obj = None
    if raw_user:
        try:
            user_obj = json.loads(raw_user)
            detected_lang = detect_language_from_code(str(user_obj.get("language_code", "")))
        except Exception:
            user_obj = None

    try:
        auth_date = int(pairs.get("auth_date", "0"))
    except ValueError:
        raise HTTPException(status_code=401, detail=t(detected_lang, "api_bad_auth_date"))

    if auth_date <= 0 or (time.time() - auth_date) > INIT_DATA_MAX_AGE_SECONDS:
        raise HTTPException(status_code=401, detail=t(detected_lang, "api_session_expired"))

    if not raw_user:
        raise HTTPException(status_code=401, detail=t(detected_lang, "api_missing_user"))

    try:
        if user_obj is None:
            user_obj = json.loads(raw_user)
        uid = int(user_obj["id"])
    except Exception:
        raise HTTPException(status_code=401, detail=t(detected_lang, "api_bad_user"))

    return uid, str(user_obj.get("first_name", "")), str(user_obj.get("username", "")), str(user_obj.get("language_code", ""))


async def get_current_user(
    x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
) -> WebAppUser:
    uid, first_name, username, language_code = _parse_and_verify_init_data(x_telegram_init_data or "")
    if not await is_user_allowed(uid):
        raise HTTPException(status_code=403, detail=t(detect_language_from_code(language_code), "access_denied"))
    lang = await ensure_user_language(uid, language_code)
    return WebAppUser(user_id=uid, first_name=first_name, username=username, is_admin=is_admin_id(uid), lang=lang, language_code=language_code)
