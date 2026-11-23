import logging
from datetime import datetime, timedelta, timezone
from aiogram import Router, Bot, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from database import (
    add_pending_notification,
    add_tracked_messages_batch,
    claim_and_ack_notification,
    claim_and_repeat_notification,
    claim_and_snooze_notification,
    format_recurrence_label,
    get_or_create_pending_for_trigger,
    get_pending_notification_by_id,
    get_pending_notification_by_message_id,
    get_pending_notifications,
    get_pending_notifications_count,
    pop_all_window_messages,
    remove_pending_notification,
    set_panel_message_id,
    update_pending_notification_msg_id,
)
from keyboards import (
    notification_ack_kb,
    notification_snooze_kb,
    notifications_section_kb,
)
from .common import (
    parse_cb_int,
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
    bot: Bot,
    user_id: int,
    reminder_id: int,
    text: str,
    recurrence: str,
    scheduled_at: datetime | None = None,
) -> tuple[int, int]:
    """Отправляет уведомление и возвращает (notif_id, sent_message_id).

    При повторном вызове для уже отправленного (reminder_id, scheduled_at) не шлёт дубль.
    """
    if scheduled_at is not None:
        notif, already_sent = await get_or_create_pending_for_trigger(
            user_id=user_id,
            reminder_id=reminder_id,
            text_val=text,
            recurrence=recurrence,
            scheduled_at=scheduled_at,
        )
        if already_sent:
            return notif.id, int(notif.message_id)
    else:
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

    return notif.id, int(sent_msg.message_id)


async def show_notifications_screen(
    bot: Bot,
    user_id: int,
    extra_delete_ids: list[int] | None = None,
) -> None:
    old_ids = await pop_all_window_messages(user_id)
    if extra_delete_ids:
        old_ids.extend(extra_delete_ids)

    sent_ok = False
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
            sent_ok = True
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
        sent_ok = True
    finally:
        if old_ids:
            if sent_ok:
                await safe_delete_messages_batch(bot, user_id, old_ids)
            else:
                await add_tracked_messages_batch(user_id, old_ids)


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
    notif_id = parse_cb_int(parts, 2) or 0
    fallback_msg_id = callback.message.message_id if callback.message else 0

    claimed_msg_id = await claim_and_ack_notification(uid, notif_id, fallback_msg_id)
    if claimed_msg_id is None:
        await safe_answer_callback(callback, "Уведомление уже обработано")
        if callback.message:
            await safe_delete_message(bot, uid, callback.message.message_id)
        await sync_user_commands(bot, uid)
        return

    await safe_answer_callback(callback, "Прочитано")
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
    notif_id = parse_cb_int(parts, 2) or 0
    uid = callback.from_user.id
    fallback_msg_id = callback.message.message_id if callback.message else 0

    status, reminder_text, _ = await claim_and_repeat_notification(
        uid, notif_id, fallback_msg_id
    )
    if status == "already_processed":
        await safe_answer_callback(callback, "Уведомление уже обработано", show_alert=True)
        if callback.message:
            await safe_delete_message(bot, uid, callback.message.message_id)
        await sync_user_commands(bot, uid)
        return

    if callback.message:
        await safe_delete_message(bot, uid, callback.message.message_id)

    if status != "ok" or not reminder_text:
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
    notif_id = parse_cb_int(parts, 2) or 0
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
        except Exception as exc:
            logger.debug("edit_reply_markup (snooze_menu) failed: %s", exc)


@router.callback_query(F.data.startswith("notif:back:"))
async def cb_notif_back(callback: CallbackQuery, bot: Bot) -> None:
    parts = callback.data.split(":")
    notif_id = parse_cb_int(parts, 2) or 0
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
        except Exception as exc:
            logger.debug("edit_reply_markup (notif:back) failed: %s", exc)


@router.callback_query(F.data.startswith("notif:snooze:"))
async def cb_notif_snooze_apply(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    parts = callback.data.split(":")
    notif_id = parse_cb_int(parts, 3)
    if len(parts) < 4 or notif_id is None:
        await safe_answer_callback(callback, "Уведомление уже обработано", show_alert=True)
        return

    interval_code = parts[2]
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
    fallback_msg_id = callback.message.message_id if callback.message else 0
    status, _ = await claim_and_snooze_notification(
        uid, notif_id, new_utc_dt, fallback_msg_id
    )

    if status == "already_processed":
        await safe_answer_callback(callback, "Уведомление уже обработано", show_alert=True)
        if callback.message:
            await safe_delete_message(bot, uid, callback.message.message_id)
        await sync_user_commands(bot, uid)
        return

    if status == "reminder_not_found":
        await safe_answer_callback(
            callback,
            "Исходное напоминание не найдено. Уведомление сохранено.",
            show_alert=True,
        )
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
