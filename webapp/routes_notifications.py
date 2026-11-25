from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException

from database import (
    claim_and_ack_notification,
    claim_and_repeat_notification,
    claim_and_snooze_notification,
    format_recurrence_label,
    get_pending_notifications,
)
from i18n import get_snooze_label, t
from .auth import WebAppUser, get_current_user
from .html_sanitizer import sanitize_telegram_html, strip_html_for_ui
from .schemas import SnoozeRequest
from .tg_sync import cleanup_chat_message

router = APIRouter(prefix="/api/notifications", tags=["notifications"])

SNOOZE_DELTAS: dict[str, timedelta] = {
    "5m": timedelta(minutes=5), "30m": timedelta(minutes=30), "1h": timedelta(hours=1), "1d": timedelta(days=1),
}


@router.get("")
async def list_notifications(user: WebAppUser = Depends(get_current_user)) -> dict:
    pending = await get_pending_notifications(user.user_id)
    items = [
        {
            "id": n.id, "reminder_id": n.reminder_id, "text": strip_html_for_ui(n.text),
            "text_html": sanitize_telegram_html(n.text), "recurrence": n.recurrence,
            "recurrence_label": format_recurrence_label(n.recurrence, lang=user.lang) if n.recurrence and n.recurrence != "once" else "",
        }
        for n in pending
    ]
    return {"total": len(items), "items": items}


@router.post("/{notif_id}/ack")
async def ack_notification(notif_id: int, user: WebAppUser = Depends(get_current_user)) -> dict:
    msg_id = await claim_and_ack_notification(user.user_id, notif_id)
    if msg_id is None:
        raise HTTPException(status_code=404, detail=t(user.lang, "notif_already_done"))
    await cleanup_chat_message(user.user_id, msg_id)
    return {"ok": True}


@router.post("/{notif_id}/snooze")
async def snooze_notification(notif_id: int, payload: SnoozeRequest, user: WebAppUser = Depends(get_current_user)) -> dict:
    delta = SNOOZE_DELTAS[payload.interval]
    label = get_snooze_label(payload.interval, lang=user.lang)
    new_utc = datetime.now(timezone.utc).replace(tzinfo=None) + delta
    status, msg_id = await claim_and_snooze_notification(user.user_id, notif_id, new_utc)
    if status == "already_processed":
        raise HTTPException(status_code=404, detail=t(user.lang, "notif_already_done"))
    if status == "reminder_not_found":
        raise HTTPException(status_code=404, detail=t(user.lang, "api_notif_not_found"))
    await cleanup_chat_message(user.user_id, msg_id)
    return {"ok": True, "label": label}


@router.post("/{notif_id}/repeat")
async def repeat_notification(notif_id: int, user: WebAppUser = Depends(get_current_user)) -> dict:
    status, reminder_text, msg_id = await claim_and_repeat_notification(user.user_id, notif_id)
    if status == "already_processed":
        raise HTTPException(status_code=404, detail=t(user.lang, "notif_already_done"))
    await cleanup_chat_message(user.user_id, msg_id)
    if status != "ok" or not reminder_text:
        raise HTTPException(status_code=404, detail=t(user.lang, "api_notif_text_not_found"))
    return {"ok": True, "text": strip_html_for_ui(reminder_text), "text_html": sanitize_telegram_html(reminder_text)}
