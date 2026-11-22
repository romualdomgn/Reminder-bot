from datetime import date, datetime, time, timedelta
from fastapi import APIRouter, Depends, HTTPException

from config import set_last_deleted_reminder, pop_last_deleted_reminder
from database import (
    create_reminder,
    delete_reminder_by_id,
    format_tz_label,
    get_active_reminders,
    get_pending_notifications_count,
    get_reminder_by_id,
    get_user_now,
    update_reminder_datetime,
    update_reminder_recurrence,
    update_reminder_text,
)
from .auth import WebAppUser, get_current_user
from .grouping import (
    RU_MONTHS_GENITIVE,
    build_grouped_reminders,
    compute_quick_time,
    escape_for_bot_html,
)
from .schemas import ReminderCreateRequest, ReminderUpdateRequest

router = APIRouter(prefix="/api", tags=["reminders"])


@router.get("/bootstrap")
async def get_bootstrap(user: WebAppUser = Depends(get_current_user)) -> dict:
    user_now, offset_mins = await get_user_now(user.user_id)
    reminders = await get_active_reminders(user.user_id)
    pending_count = await get_pending_notifications_count(user.user_id)
    quick_date, quick_time = compute_quick_time(user_now, user_now.date())

    return {
        "user": {
            "id": user.user_id,
            "first_name": user.first_name,
            "username": user.username,
            "is_admin": user.is_admin,
        },
        "now": {
            "time": user_now.strftime("%H:%M"),
            "date_ru": f"{user_now.day} {RU_MONTHS_GENITIVE[user_now.month]} {user_now.year}",
            "iso_date": user_now.date().isoformat(),
            "tz_label": format_tz_label(offset_mins),
            "offset_minutes": offset_mins,
        },
        "quick_default": {"date": quick_date, "time": quick_time},
        "counts": {
            "reminders": len(reminders),
            "notifications": pending_count,
        },
    }


@router.get("/reminders")
async def list_reminders(user: WebAppUser = Depends(get_current_user)) -> dict:
    reminders = await get_active_reminders(user.user_id)
    user_now, offset_mins = await get_user_now(user.user_id)
    groups = build_grouped_reminders(reminders, user_now, offset_mins)
    return {"total": len(reminders), "groups": groups}


@router.post("/reminders")
async def create_new_reminder(
    payload: ReminderCreateRequest,
    user: WebAppUser = Depends(get_current_user),
) -> dict:
    user_now, offset_mins = await get_user_now(user.user_id)
    try:
        target_date = date.fromisoformat(payload.date)
        target_time = time.fromisoformat(payload.time)
    except ValueError:
        raise HTTPException(status_code=400, detail="Неверный формат даты или времени")

    local_dt = datetime.combine(target_date, target_time)
    if local_dt <= user_now.replace(tzinfo=None):
        raise HTTPException(
            status_code=400,
            detail="Выбранное время уже прошло. Укажите более позднее время",
        )

    remind_utc = local_dt - timedelta(minutes=offset_mins)
    created = await create_reminder(
        user_id=user.user_id,
        text=escape_for_bot_html(payload.text),
        remind_at_utc=remind_utc,
        recurrence=payload.recurrence,
    )
    return {"ok": True, "id": created.id}


@router.patch("/reminders/{reminder_id}")
async def edit_reminder(
    reminder_id: int,
    payload: ReminderUpdateRequest,
    user: WebAppUser = Depends(get_current_user),
) -> dict:
    reminder = await get_reminder_by_id(user.user_id, reminder_id)
    if not reminder:
        raise HTTPException(status_code=404, detail="Напоминание не найдено или уже отправлено")

    user_now, offset_mins = await get_user_now(user.user_id)
    old_local = reminder.remind_at + timedelta(minutes=offset_mins)

    if payload.date is not None or payload.time is not None:
        try:
            new_date = date.fromisoformat(payload.date) if payload.date else old_local.date()
            new_time = time.fromisoformat(payload.time) if payload.time else old_local.time()
        except ValueError:
            raise HTTPException(status_code=400, detail="Неверный формат даты или времени")

        new_local = datetime.combine(new_date, new_time)
        if new_local <= user_now.replace(tzinfo=None):
            raise HTTPException(
                status_code=400,
                detail="Выбранное время уже прошло. Укажите более позднее время",
            )
        await update_reminder_datetime(
            user.user_id, reminder_id, new_local - timedelta(minutes=offset_mins)
        )

    if payload.text is not None:
        await update_reminder_text(
            user.user_id, reminder_id, escape_for_bot_html(payload.text)
        )

    if payload.recurrence is not None:
        await update_reminder_recurrence(user.user_id, reminder_id, payload.recurrence)

    return {"ok": True}


@router.delete("/reminders/{reminder_id}")
async def remove_reminder(
    reminder_id: int,
    user: WebAppUser = Depends(get_current_user),
) -> dict:
    reminder = await get_reminder_by_id(user.user_id, reminder_id)
    if not reminder:
        raise HTTPException(status_code=404, detail="Напоминание уже не активно")

    deleted = await delete_reminder_by_id(user.user_id, reminder_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Напоминание уже удалено")

    set_last_deleted_reminder(
        user.user_id,
        {
            "text": reminder.text,
            "remind_at": reminder.remind_at,
            "recurrence": reminder.recurrence,
        },
    )
    return {"ok": True, "can_undo": True}


@router.post("/reminders/undo")
async def undo_delete_reminder(user: WebAppUser = Depends(get_current_user)) -> dict:
    saved = pop_last_deleted_reminder(user.user_id)
    if not saved:
        raise HTTPException(status_code=404, detail="Отмена удаления больше недоступна")

    restored = await create_reminder(
        user_id=user.user_id,
        text=saved["text"],
        remind_at_utc=saved["remind_at"],
        recurrence=saved["recurrence"],
    )
    return {"ok": True, "id": restored.id}
