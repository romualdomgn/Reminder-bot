import html
from datetime import datetime, timedelta, timezone
from aiogram import Router, Bot, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from database import (
    get_reminder_any_by_id,
    snooze_or_clone_reminder,
    get_user_now,
    format_tz_label,
    format_recurrence_label,
    add_pending_notification,
    get_pending_notification_by_msg,
    remove_pending_notification,
    get_pending_notifications_count,
)
from keyboards import (
    main_menu_kb,
    notification_ack_kb,
    notification_snooze_kb,
)
from .common import (
    safe_delete_message,
    render_panel,
    build_home_text,
    start_date_selection,
    get_user_main_menu_kb,
    sync_user_commands,
)

router = Router()


async def send_reminder_notification(bot: Bot, user_id: int, reminder_id: int, text: str, recurrence: str) -> None:
    rec_lbl = format_recurrence_label(recurrence)
    # Если повтор не задан («Один раз» / «once»), то строку повтора не пишем вообще.
    # Если задан, выводим его в чистом виде (например, «Каждый день», «Каждые две недели» и т.д.)
    rec_line = f"\n{rec_lbl}" if rec_lbl and recurrence != "once" else ""
    
    alert_text = (
        f"<b>Напоминание!</b>{rec_line}\n\n"
        f"💬 {html.escape(text)}"
    )
    sent_msg = await bot.send_message(
        chat_id=user_id,
        text=alert_text,
        reply_markup=notification_ack_kb(0),
    )
    await add_pending_notification(user_id, reminder_id, sent_msg.message_id, text, recurrence)

    from keyboards import notification_ack_kb as real_ack_kb
    try:
        await bot.edit_message_reply_markup(
            chat_id=user_id,
            message_id=sent_msg.message_id,
            reply_markup=real_ack_kb(sent_msg.message_id),
        )
    except Exception:
        pass

    await sync_user_commands(bot, user_id)


@router.message(Command("notifications", ignore_case=True))
async def cmd_notifications(message: Message, state: FSMContext, bot: Bot) -> None:
    await safe_delete_message(bot, message.chat.id, message.message_id)
    await state.clear()
    uid = message.from_user.id
    count = await get_pending_notifications_count(uid)
    if count == 0:
        home_text = await build_home_text(uid, notice="У вас нет непрочитанных уведомлений.")
        kb = await get_user_main_menu_kb(uid)
        await render_panel(bot, uid, home_text, kb, force_new=True)
    else:
        home_text = await build_home_text(uid, notice=f"У вас имеется непрочитанных уведомлений: {count}.")
        kb = await get_user_main_menu_kb(uid)
        await render_panel(bot, uid, home_text, kb, force_new=True)


@router.callback_query(F.data == "notifications:list")
async def cb_notifications_list(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await callback.answer()
    await state.clear()
    uid = callback.from_user.id
    count = await get_pending_notifications_count(uid)
    home_text = await build_home_text(uid, notice=f"Непрочитанных уведомлений: {count}. Они отображаются выше в чате.")
    kb = await get_user_main_menu_kb(uid)
    await render_panel(bot, uid, home_text, kb)


@router.callback_query(F.data.startswith("notif:ack:"))
async def cb_notif_ack(callback: CallbackQuery, bot: Bot) -> None:
    uid = callback.from_user.id
    msg_id = callback.message.message_id if callback.message else 0
    notif = await get_pending_notification_by_msg(uid, msg_id)
    if notif:
        await remove_pending_notification(notif.id)

    if callback.message:
        await safe_delete_message(bot, uid, callback.message.message_id)
    await callback.answer("Прочитано")
    await sync_user_commands(bot, uid)


@router.callback_query(F.data.startswith("notif:repeat:"))
async def cb_notif_repeat(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    parts = callback.data.split(":")
    notif_id_or_msg = int(parts[2])
    uid = callback.from_user.id

    notif = await get_pending_notification_by_msg(uid, notif_id_or_msg)
    reminder_id = notif.reminder_id if notif else notif_id_or_msg
    reminder = await get_reminder_any_by_id(uid, reminder_id)

    if notif:
        await remove_pending_notification(notif.id)

    if callback.message:
        await safe_delete_message(bot, uid, callback.message.message_id)

    if not reminder:
        await callback.answer("Напоминание не найдено", show_alert=True)
        await sync_user_commands(bot, uid)
        return

    await state.clear()
    await start_date_selection(
        bot=bot,
        user_id=uid,
        state=state,
        reminder_text=reminder.text,
        header_title="🔁 <b>Повтор напоминания — Шаг 1 из 4</b>",
    )
    await callback.answer()
    await sync_user_commands(bot, uid)


@router.callback_query(F.data.startswith("notif:snooze_menu:"))
async def cb_notif_snooze_menu(callback: CallbackQuery) -> None:
    parts = callback.data.split(":")
    notif_id_or_msg = int(parts[2])
    if callback.message:
        try:
            await callback.message.edit_reply_markup(
                reply_markup=notification_snooze_kb(notif_id_or_msg)
            )
        except Exception:
            pass
    await callback.answer("Выберите, на сколько отложить")


@router.callback_query(F.data.startswith("notif:back:"))
async def cb_notif_back(callback: CallbackQuery) -> None:
    parts = callback.data.split(":")
    notif_id_or_msg = int(parts[2])
    if callback.message:
        try:
            await callback.message.edit_reply_markup(
                reply_markup=notification_ack_kb(notif_id_or_msg)
            )
        except Exception:
            pass
    await callback.answer()


@router.callback_query(F.data.startswith("notif:snooze:"))
async def cb_notif_snooze_apply(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    parts = callback.data.split(":")
    interval_code = parts[2]
    notif_id_or_msg = int(parts[3])

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
    notif = await get_pending_notification_by_msg(uid, notif_id_or_msg)
    reminder_id = notif.reminder_id if notif else notif_id_or_msg

    if notif:
        await remove_pending_notification(notif.id)

    snoozed = await snooze_or_clone_reminder(uid, reminder_id, new_utc_dt)

    if callback.message:
        await safe_delete_message(bot, uid, callback.message.message_id)

    if not snoozed:
        await callback.answer("Напоминание не найдено", show_alert=True)
        await sync_user_commands(bot, uid)
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
    await sync_user_commands(bot, uid)
