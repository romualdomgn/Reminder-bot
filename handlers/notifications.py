import html
from datetime import datetime, timedelta, timezone
from aiogram import Router, Bot, F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from database import (
    get_reminder_any_by_id,
    snooze_or_clone_reminder,
    remove_tracked_message,
    get_user_now,
    format_tz_label,
)
from keyboards import (
    notification_ack_kb,
    notification_snooze_kb,
)
from .common import (
    safe_delete_message,
    render_panel,
    build_home_text,
    start_date_selection,
    get_user_main_menu_kb,
)

router = Router()


@router.callback_query(F.data == "ack_alert")
async def cb_ack_alert(callback: CallbackQuery, bot: Bot) -> None:
    if callback.message:
        await remove_tracked_message(callback.from_user.id, callback.message.message_id)
        await safe_delete_message(bot, callback.from_user.id, callback.message.message_id)
    await callback.answer("Уведомление скрыто")


@router.callback_query(F.data.startswith("notif:repeat:"))
async def cb_notif_repeat(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    reminder_id = int(callback.data.split(":")[2])
    reminder = await get_reminder_any_by_id(callback.from_user.id, reminder_id)

    if callback.message:
        await remove_tracked_message(callback.from_user.id, callback.message.message_id)
        await safe_delete_message(bot, callback.from_user.id, callback.message.message_id)

    if not reminder:
        await callback.answer("Напоминание не найдено", show_alert=True)
        return

    await state.clear()
    await start_date_selection(
        bot=bot,
        user_id=callback.from_user.id,
        state=state,
        reminder_text=reminder.text,
        header_title="🔁 <b>Повтор напоминания — Выбор даты</b>",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("notif:snooze_menu:"))
async def cb_notif_snooze_menu(callback: CallbackQuery) -> None:
    reminder_id = int(callback.data.split(":")[2])
    if callback.message:
        try:
            await callback.message.edit_reply_markup(
                reply_markup=notification_snooze_kb(reminder_id)
            )
        except Exception:
            pass
    await callback.answer("Выберите, на сколько отложить")


@router.callback_query(F.data.startswith("notif:back:"))
async def cb_notif_back(callback: CallbackQuery) -> None:
    reminder_id = int(callback.data.split(":")[2])
    if callback.message:
        try:
            await callback.message.edit_reply_markup(
                reply_markup=notification_ack_kb(reminder_id)
            )
        except Exception:
            pass
    await callback.answer()


@router.callback_query(F.data.startswith("notif:snooze:"))
async def cb_notif_snooze_apply(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    parts = callback.data.split(":")
    interval_code = parts[2]
    reminder_id = int(parts[3])

    if interval_code == "5m":
        delta = timedelta(minutes=5)
        label = "5 минут"
    elif interval_code == "1h":
        delta = timedelta(hours=1)
        label = "1 час"
    else:
        delta = timedelta(days=1)
        label = "1 день"

    now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
    new_utc_dt = now_utc + delta

    uid = callback.from_user.id
    snoozed = await snooze_or_clone_reminder(uid, reminder_id, new_utc_dt)

    if callback.message:
        await remove_tracked_message(uid, callback.message.message_id)
        await safe_delete_message(bot, uid, callback.message.message_id)

    if not snoozed:
        await callback.answer("Напоминание не найдено", show_alert=True)
        return

    _, offset_mins = await get_user_now(uid)
    local_dt = new_utc_dt + timedelta(minutes=offset_mins)
    tz_label = format_tz_label(offset_mins)

    await state.clear()
    notice = (
        f"⏳ <b>Напоминание отложено на {label}!</b>\n"
        f"📅 Дата: <code>{local_dt.strftime('%d.%m.%Y')}</code>\n"
        f"⏰ Время: <code>{local_dt.strftime('%H:%M')} ({tz_label})</code>\n"
        f"💬 Текст: <i>{html.escape(snoozed.text)}</i>"
    )
    home_text = await build_home_text(uid, notice=notice)
    kb = await get_user_main_menu_kb(uid)
    await render_panel(
        bot=bot,
        user_id=uid,
        text=home_text,
        reply_markup=kb,
    )
    await callback.answer(f"Отложено на {label}")
