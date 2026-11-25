import re
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException

from config import ADMIN_TG_USERNAME, REPOSITORY_URL, get_app_version_info
from database import format_tz_label, get_user_now, set_user_language, set_user_offset_minutes
from i18n import get_tz_presets, get_webapp_info_cards, t
from .auth import WebAppUser, get_current_user
from .schemas import LangUpdateRequest, TzUpdateRequest
from .tg_sync import sync_chat_commands_from_webapp

router = APIRouter(prefix="/api", tags=["settings"])
_TIME_RE = re.compile(r"^\s*(\d{1,2})\D+(\d{1,2})\s*$")


@router.get("/settings")
async def get_settings(user: WebAppUser = Depends(get_current_user)) -> dict:
    user_now, offset_mins = await get_user_now(user.user_id)
    return {
        "lang": user.lang,
        "current_dt": user_now.strftime("%d.%m.%Y %H:%M"),
        "offset_minutes": offset_mins,
        "tz_label": format_tz_label(offset_mins, lang=user.lang),
        "presets": get_tz_presets(user.lang),
    }


@router.post("/settings/lang")
async def update_language(payload: LangUpdateRequest, user: WebAppUser = Depends(get_current_user)) -> dict:
    saved = await set_user_language(user.user_id, payload.lang)
    await sync_chat_commands_from_webapp(user.user_id, saved)
    return {"ok": True, "lang": saved}


@router.post("/settings/tz")
async def update_timezone(payload: TzUpdateRequest, user: WebAppUser = Depends(get_current_user)) -> dict:
    if payload.offset_minutes is not None:
        offset_minutes = int(round(payload.offset_minutes / 15.0) * 15)
    elif payload.device_time is not None:
        match = _TIME_RE.match(payload.device_time)
        if not match:
            raise HTTPException(status_code=400, detail=t(user.lang, "api_bad_time_hhmm"))
        hour, minute = int(match.group(1)), int(match.group(2))
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise HTTPException(status_code=400, detail=t(user.lang, "api_bad_time_range"))
        utc_now = datetime.now(timezone.utc)
        diff = (hour * 60 + minute) - (utc_now.hour * 60 + utc_now.minute)
        if diff > 840:
            diff -= 1440
        elif diff < -720:
            diff += 1440
        offset_minutes = int(round(diff / 15.0) * 15)
    else:
        raise HTTPException(status_code=400, detail=t(user.lang, "api_tz_payload_missing"))

    await set_user_offset_minutes(user.user_id, offset_minutes)
    user_now, _ = await get_user_now(user.user_id)
    return {
        "ok": True,
        "offset_minutes": offset_minutes,
        "tz_label": format_tz_label(offset_minutes, lang=user.lang),
        "current_dt": user_now.strftime("%d.%m.%Y %H:%M"),
    }


@router.get("/info")
async def get_info(user: WebAppUser = Depends(get_current_user)) -> dict:
    version_str, last_update = get_app_version_info()
    return {
        "cards": get_webapp_info_cards(
            lang=user.lang, repo_url=REPOSITORY_URL, admin_username=ADMIN_TG_USERNAME,
            version_str=version_str, last_update=last_update,
        )
    }
