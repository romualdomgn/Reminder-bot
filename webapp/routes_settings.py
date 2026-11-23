import re
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException

from config import ADMIN_TG_USERNAME, REPOSITORY_URL, get_app_version_info
from database import (
    TZ_ABBR_MAP,
    format_tz_label,
    get_user_now,
    set_user_offset_minutes,
)
from .auth import WebAppUser, get_current_user
from .schemas import TzUpdateRequest

router = APIRouter(prefix="/api", tags=["settings"])

_TIME_RE = re.compile(r"^\s*(\d{1,2})\D+(\d{1,2})\s*$")


@router.get("/settings")
async def get_settings(user: WebAppUser = Depends(get_current_user)) -> dict:
    user_now, offset_mins = await get_user_now(user.user_id)
    presets = [
        {"offset_minutes": mins, "label": label}
        for mins, label in sorted(TZ_ABBR_MAP.items())
    ]
    return {
        "current_dt": user_now.strftime("%d.%m.%Y %H:%M"),
        "offset_minutes": offset_mins,
        "tz_label": format_tz_label(offset_mins),
        "presets": presets,
    }


@router.post("/settings/tz")
async def update_timezone(
    payload: TzUpdateRequest,
    user: WebAppUser = Depends(get_current_user),
) -> dict:
    if payload.offset_minutes is not None:
        offset_minutes = int(round(payload.offset_minutes / 15.0) * 15)
    elif payload.device_time is not None:
        match = _TIME_RE.match(payload.device_time)
        if not match:
            raise HTTPException(status_code=400, detail="Введите время в формате ЧЧ:ММ")
        hour, minute = int(match.group(1)), int(match.group(2))
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise HTTPException(status_code=400, detail="Некорректное время (00:00–23:59)")

        utc_now = datetime.now(timezone.utc)
        diff = (hour * 60 + minute) - (utc_now.hour * 60 + utc_now.minute)
        if diff > 840:
            diff -= 1440
        elif diff < -720:
            diff += 1440
        offset_minutes = int(round(diff / 15.0) * 15)
    else:
        raise HTTPException(status_code=400, detail="Укажите offset_minutes или device_time")

    await set_user_offset_minutes(user.user_id, offset_minutes)
    user_now, _ = await get_user_now(user.user_id)
    return {
        "ok": True,
        "offset_minutes": offset_minutes,
        "tz_label": format_tz_label(offset_minutes),
        "current_dt": user_now.strftime("%d.%m.%Y %H:%M"),
    }


@router.get("/info")
async def get_info(_user: WebAppUser = Depends(get_current_user)) -> dict:
    version_str, last_update = get_app_version_info()
    cards = [
        {
            "title": "📋 Как создать напоминание",
            "body": (
                "Нажмите «Создать напоминание», укажите текст, выберите быструю дату или любую дату "
                "в календаре, точное время и периодичность (разовое, ежедневно, раз в неделю, "
                "раз в две недели, ежемесячно или ежегодно). Активные напоминания можно редактировать "
                "и удалять с возможностью мгновенной отмены."
            ),
        },
        {
            "title": "🔔 Работа с уведомлениями",
            "body": (
                "Все сработавшие напоминания без реакции попадают в раздел «Уведомления». "
                "Каждое уведомление можно отметить прочитанным, отложить (5 мин, 30 мин, 1 час, 1 день) "
                "или перезапустить кнопкой «Повторить»."
            ),
        },
        {
            "title": "🕒 Выбор часового пояса",
            "body": (
                "Сервер хранит напоминания в UTC. Настройте свой часовой пояс в «Настройках» "
                "кнопкой автосинхронизации с устройством, выбором города или вводом времени ЧЧ:ММ, "
                "чтобы уведомления приходили строго по местному времени."
            ),
        },
        {
            "title": "👤 Как добавить нового пользователя",
            "body": (
                "Узнайте числовой Telegram ID участника через @userinfobot, откройте раздел "
                "«Пользователи» → «Добавить пользователя», введите ID и имя. После этого участник "
                "сразу получит доступ к боту."
            ),
        },
        {
            "title": "📱 Вид приложения",
            "body": "Приложение можно использовать в двух вариантах - как чат в Телеграм или как мини-приложение.",
        },
        {
            "title": "🌐 О приложении",
            "body": (
                f"Open-source приложение «Напоминалкин».\n"
                f"Репозиторий: {REPOSITORY_URL}\n"
                f"Разработчик: {ADMIN_TG_USERNAME}\n"
                f"ver. {version_str} Last update - {last_update}"
            ),
        },
    ]
    return {"cards": cards}
