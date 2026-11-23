from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException

from database import (
    format_recurrence_label,
    get_pending_notification_by_id,
    get_pending_notifications,
    get_reminder_any_by_id,
    remove_pending_notification,
    snooze_or_clone_reminder,
)
from .auth import WebAppUser, get_current_user
from .html_sanitizer import sanitize_telegram_html, strip_html_for_ui
from .schemas import SnoozeRequest
from .tg_sync import cleanup_chat_message

router = APIRouter(prefix="/api/notifications", tags=["notifications"])

SNOOZE_DELTAS: dict[str, tuple[timedelta, str]] = {
    "5m": (timedelta(minutes=5), "5 минут"),
    "30m": (timedelta(minutes=30), "30 минут"),
    "1h": (timedelta(hours=1), "1 час"),
    "1d": (timedelta(days=1), "1 день"),
}


@router.get("")
async def list_notifications(user: WebAppUser = Depends(get_current_user)) -> dict:
    pending = await get_pending_notifications(user.user_id)
    items = [
        {
            "id": n.id,
            "reminder_id": n.reminder_id,
            "text": strip_html_for_ui(n.text),
            "text_html": sanitize_telegram_html(n.text),
            "recurrence": n.recurrence,
            "recurrence_label": (
                format_recurrence_label(n.recurrence)
                if n.recurrence and n.recurrence != "once"
                else ""
            ),
        }
        for n in pending
    ]
    return {"total": len(items), "items": items}


@router.post("/{notif_id}/ack")
async def ack_notification(
    notif_id: int,
    user: WebAppUser = Depends(get_current_user),
) -> dict:
    notif = await get_pending_notification_by_id(user.user_id, notif_id)
    if not notif:
        raise HTTPException(status_code=404, detail="Уведомление уже обработано")
    msg_id = notif.message_id
    await remove_pending_notification(notif.id)
    await cleanup_chat_message(user.user_id, msg_id)
    return {"ok": True}


@router.post("/{notif_id}/snooze")
async def snooze_notification(
    notif_id: int,
    payload: SnoozeRequest,
    user: WebAppUser = Depends(get_current_user),
) -> dict:
    notif = await get_pending_notification_by_id(user.user_id, notif_id)
    if not notif:
        raise HTTPException(status_code=404, detail="Уведомление уже обработано")

    delta, label = SNOOZE_DELTAS[payload.interval]
    new_utc = datetime.now(timezone.utc).replace(tzinfo=None) + delta
    msg_id = notif.message_id

    await remove_pending_notification(notif.id)
    snoozed = await snooze_or_clone_reminder(user.user_id, notif.reminder_id, new_utc)
    await cleanup_chat_message(user.user_id, msg_id)
    if not snoozed:
        raise HTTPException(status_code=404, detail="Исходное напоминание не найдено")

    return {"ok": True, "label": label}


@router.post("/{notif_id}/repeat")
async def repeat_notification(
    notif_id: int,
    user: WebAppUser = Depends(get_current_user),
) -> dict:
    notif = await get_pending_notification_by_id(user.user_id, notif_id)
    if not notif:
        raise HTTPException(status_code=404, detail="Уведомление уже обработано")

    msg_id = notif.message_id
    reminder_text = notif.text
    if not reminder_text:
        rem = await get_reminder_any_by_id(user.user_id, notif.reminder_id)
        if rem:
            reminder_text = rem.text

    await remove_pending_notification(notif.id)
    await cleanup_chat_message(user.user_id, msg_id)
    if not reminder_text:
        raise HTTPException(status_code=404, detail="Текст напоминания не найден")

    return {
        "ok": True,
        "text": strip_html_for_ui(reminder_text),
        "text_html": sanitize_telegram_html(reminder_text),
    }
