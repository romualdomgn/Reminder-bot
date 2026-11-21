import logging
from datetime import datetime, timedelta, timezone
from aiogram import Router, Bot, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from database import (
    get_reminder_any_by_id,
    snooze_or_clone_reminder,
    format_recurrence_label,
    add_pending_notification,
    update_pending_notification_msg_id,
    get_pending_notifications,
    get_pending_notification_by_id,
    get_pending_notification_by_message_id,
    remove_pending_notification,
    get_pending_notifications_count,
    pop_all_window_messages,
    set_panel_message_id,
)
from keyboards import (
    notification_ack_kb,
    notification_snooze_kb,
    notifications_section_kb,
)
from .common import (
    safe_delete_message,
    safe_delete_messages_batch,
    safe_answer_callback,
    render_panel,
    build_home_text,
    start_date_selection,
    get_user_main_menu_kb,
    sync_user_commands,
)

logger = logging.getLogger(__name__)
router = Router()


def format_notification_alert_text(text: str, recurrence: str) -> str:
    rec_lbl = format_recurrence_label(recurrence)
    if rec_lbl and recurrence != "once":
        return f"{rec_lbl}\n\n{text}"
    return text


async def _find_pending_notification(
    user_id: int, notif_id: int, callback: CallbackQuery
):
    notif = await get_pending_notification_by_id(user_id, notif_id)
    if not notif and callback.message:
        notif = await get_pending_notification_by_message_id(
            user_id, callback.message.message_id
        )
    return notif


async def send_reminder_notification(
    bot: Bot, user_id: int, reminder_id: int, text: str, recurrence: str
) -> None:
    notif = await add_pending_notification(
        user_id=user_id,
        reminder_id=reminder_id,
        message_id=0,
        text=text,
        recurrence=recurrence,
    )
    alert_text = format_notification_alert_text(text, recurrence)
    try:
        sent_msg = await bot.send_message(
            chat_id=user_id,
            text=alert_text,
            reply_markup=notification_ack_kb(notif.id),
        )
    except Exception:
        try:
            await remove_pending_notification(notif.id)
        except Exception:
            logger.exception(
                "Не удалось удалить неотправленное уведомление ID=%s", notif.id
            )
        raise

    try:
        await update_pending_notification_msg_id(notif.id, sent_msg.message_id)
    except Exception:
        logger.exception(
            "Не удалось сохранить message_id=%s для уведомления ID=%s",
            sent_msg.message_id,
            notif.id,
        )

    try:
        await sync_user_commands(bot, user_id)
    except Exception:
        logger.exception(
            "Не удалось синхронизировать команды пользователя %s после отправки уведомления",
            user_id,
        )


async def show_notifications_screen(
    bot: Bot,
    user_id: int,
    extra_delete_ids: list[int] | None = None,
) -> None:
    old_ids = await pop_all_window_messages(user_id)
    if extra_delete_ids:
        old_ids.extend(extra_delete_ids)

    try:
        pending_list = await get_pending_notifications(user_id)
        if not pending_list:
            await sync_user_commands(bot, user_id)
            home_text = await build_home_text(user_id)
            kb = await get_user_main_menu_kb(user_id)
            sent_panel = await bot.send_message(
                chat_id=user_id,
                text=home_text,
                reply_markup=kb,
                disable_notification=True,
            )
            await set_panel_message_id(user_id, sent_panel.message_id)
            return

        for notif in pending_list:
            alert_text = format_notification_alert_text(notif.text, notif.recurrence)
            sent_item = await bot.send_message(
                chat_id=user_id,
                text=alert_text,
                reply_markup=notification_ack_kb(notif.id),
                disable_notification=True,
            )
            await update_pending_notification_msg_id(notif.id, sent_item.message_id)

        panel_text = (
            "🔔 <b>Раздел «Уведомления»</b>\n\n"
            f"Непрочитанных уведомлений: <b>{len(pending_list)}</b>\n"
            "Выберите действие под нужным уведомлением выше:"
        )
        sent_panel = await bot.send_message(
            chat_id=user_id,
            text=panel_text,
            reply_markup=notifications_section_kb(),
            disable_notification=True,
        )
        await set_panel_message_id(user_id, sent_panel.message_id)
        await sync_user_commands(bot, user_id)
    finally:
        if old_ids:
            await safe_delete_messages_batch(bot, user_id, old_ids)


@router.message(Command("notifications", ignore_case=True))
async def cmd_notifications(message: Message, state: FSMContext, bot: Bot) -> None:
    await state.clear()
    await show_notifications_screen(
        bot=bot,
        user_id=message.from_user.id,
        extra_delete_ids=[message.message_id],
    )


@router.callback_query(F.data == "notifications:list")
async def cb_notifications_list(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await safe_answer_callback(callback)
    await state.clear()
    await show_notifications_screen(bot=bot, user_id=callback.from_user.id)


@router.callback_query(F.data == "ack_alert")
async def cb_admin_ack_alert(callback: CallbackQuery, bot: Bot) -> None:
    await safe_answer_callback(callback)
    if callback.message:
        await safe_delete_message(bot, callback.message.chat.id, callback.message.message_id)


@router.callback_query(F.data.startswith("notif:ack:"))
async def cb_notif_ack(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    uid = callback.from_user.id
    parts = callback.data.split(":")
    notif_id = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0

    notif = await _find_pending_notification(uid, notif_id, callback)
    if not notif:
        await safe_answer_callback(callback, "Уведомление уже обработано")
        if callback.message:
            await safe_delete_message(bot, uid, callback.message.message_id)
        await sync_user_commands(bot, uid)
        return

    await safe_answer_callback(callback, "Прочитано")
    await remove_pending_notification(notif.id)

    if callback.message:
        await safe_delete_message(bot, uid, callback.message.message_id)

    await sync_user_commands(bot, uid)

    remaining = await get_pending_notifications_count(uid)
    current_state = await state.get_state()
    if current_state is None and remaining == 0:
        home_text = await build_home_text(uid)
        kb = await get_user_main_menu_kb(uid)
        await render_panel(bot, uid, home_text, kb, cleanup=True)


@router.callback_query(F.data.startswith("notif:repeat:"))
async def cb_notif_repeat(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    parts = callback.data.split(":")
    notif_id = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0
    uid = callback.from_user.id

    notif = await _find_pending_notification(uid, notif_id, callback)
    if not notif:
        await safe_answer_callback(callback, "Уведомление уже обработано", show_alert=True)
        if callback.message:
            await safe_delete_message(bot, uid, callback.message.message_id)
        await sync_user_commands(bot, uid)
        return

    reminder_text = notif.text
    if not reminder_text:
        reminder = await get_reminder_any_by_id(uid, notif.reminder_id)
        if reminder:
            reminder_text = reminder.text

    await remove_pending_notification(notif.id)

    if callback.message:
        await safe_delete_message(bot, uid, callback.message.message_id)

    if not reminder_text:
        await safe_answer_callback(callback, "Напоминание не найдено", show_alert=True)
        await sync_user_commands(bot, uid)
        return

    await safe_answer_callback(callback)
    await state.clear()
    await start_date_selection(
        bot=bot,
        user_id=uid,
        state=state,
        reminder_text=reminder_text,
    )
    await sync_user_commands(bot, uid)


@router.callback_query(F.data.startswith("notif:snooze_menu:"))
async def cb_notif_snooze_menu(callback: CallbackQuery, bot: Bot) -> None:
    parts = callback.data.split(":")
    notif_id = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0
    uid = callback.from_user.id

    notif = await _find_pending_notification(uid, notif_id, callback)
    if not notif:
        await safe_answer_callback(callback, "Уведомление уже обработано", show_alert=True)
        if callback.message:
            await safe_delete_message(bot, uid, callback.message.message_id)
        await sync_user_commands(bot, uid)
        return

    await safe_answer_callback(callback, "Выберите, на сколько отложить")
    if callback.message:
        try:
            await callback.message.edit_reply_markup(
                reply_markup=notification_snooze_kb(notif.id)
            )
        except Exception:
            pass


@router.callback_query(F.data.startswith("notif:back:"))
async def cb_notif_back(callback: CallbackQuery, bot: Bot) -> None:
    parts = callback.data.split(":")
    notif_id = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0
    uid = callback.from_user.id

    notif = await _find_pending_notification(uid, notif_id, callback)
    if not notif:
        await safe_answer_callback(callback, "Уведомление уже обработано")
        if callback.message:
            await safe_delete_message(bot, uid, callback.message.message_id)
        await sync_user_commands(bot, uid)
        return

    await safe_answer_callback(callback)
    if callback.message:
        try:
            await callback.message.edit_reply_markup(
                reply_markup=notification_ack_kb(notif.id)
            )
        except Exception:
            pass


@router.callback_query(F.data.startswith("notif:snooze:"))
async def cb_notif_snooze_apply(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    parts = callback.data.split(":")
    if len(parts) < 4 or not parts[3].isdigit():
        await safe_answer_callback(callback, "Уведомление уже обработано", show_alert=True)
        return

    interval_code = parts[2]
    notif_id = int(parts[3])

    if interval_code == "5m":
        delta = timedelta(minutes=5)
        label = "5 минут"
    elif interval_code == "30m":
        delta = timedelta(minutes=30)
        label = "30 минут"
    elif interval_code == "1h":
        delta = timedelta(hours=1)
        label = "1 час"
    else:
        delta = timedelta(days=1)
        label = "1 день"

    now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
    new_utc_dt = now_utc + delta

    uid = callback.from_user.id
    notif = await _find_pending_notification(uid, notif_id, callback)
    if not notif:
        await safe_answer_callback(callback, "Уведомление уже обработано", show_alert=True)
        if callback.message:
            await safe_delete_message(bot, uid, callback.message.message_id)
        await sync_user_commands(bot, uid)
        return

    await remove_pending_notification(notif.id)
    snoozed = await snooze_or_clone_reminder(uid, notif.reminder_id, new_utc_dt)

    if not snoozed:
        await safe_answer_callback(callback, "Напоминание не найдено", show_alert=True)
        if callback.message:
            await safe_delete_message(bot, uid, callback.message.message_id)
        await sync_user_commands(bot, uid)
        return

    await safe_answer_callback(callback, f"Отложено на {label}")
    if callback.message:
        await safe_delete_message(bot, uid, callback.message.message_id)

    await sync_user_commands(bot, uid)

    remaining = await get_pending_notifications_count(uid)
    current_state = await state.get_state()
    if current_state is None and remaining == 0:
        home_text = await build_home_text(uid)
        kb = await get_user_main_menu_kb(uid)
        await render_panel(bot, uid, home_text, kb, cleanup=True)
