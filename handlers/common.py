import asyncio
import calendar
import html
import logging
import re
from datetime import datetime, date, time
from aiogram import Bot
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    BotCommand,
    BotCommandScopeChat,
    MenuButtonCommands,
    MenuButtonWebApp,
    WebAppInfo,
)
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

from config import WEBAPP_URL
from database import (
    add_tracked_messages_batch,
    get_panel_message_id,
    set_panel_message_id,
    pop_tracked_messages,
    pop_all_window_messages,
    get_user_language,
    get_user_now,
    is_admin_id,
    user_has_invited_anyone,
    get_pending_notifications_count,
)
from i18n import (
    DEFAULT_LANG,
    MONTHS_GENITIVE,
    WEEKDAYS,
    format_date_human,
    format_date_with_weekday as _i18n_format_date_with_weekday,
    format_full_date_human,
    t,
)
from keyboards import main_menu_kb, date_selection_kb
from .states import ReminderFSM

logger = logging.getLogger(__name__)

RU_MONTHS_GENITIVE: dict[int, str] = MONTHS_GENITIVE["ru"]
RU_WEEKDAYS: dict[int, str] = WEEKDAYS["ru"]

_PERMANENT_DELETE_ERRORS = (
    "message to delete not found",
    "message can't be deleted",
    "message identifier is not specified",
    "chat not found",
    "user is deactivated",
)

_LAST_SYNCED_COMMANDS: dict[int, tuple[tuple[str, str], ...]] = {}
_LAST_SYNCED_MENU_BUTTON: dict[int, str] = {}


def clear_user_sync_cache(user_id: int) -> None:
    _LAST_SYNCED_COMMANDS.pop(user_id, None)
    _LAST_SYNCED_MENU_BUTTON.pop(user_id, None)


def parse_cb_int(parts: list[str], index: int) -> int | None:
    if index < 0 or index >= len(parts):
        return None
    raw = parts[index].strip()
    if not raw.isdigit():
        return None
    return int(raw)


def parse_cb_signed_int(parts: list[str], index: int) -> int | None:
    if index < 0 or index >= len(parts):
        return None
    try:
        return int(parts[index].strip())
    except ValueError:
        return None


async def safe_answer_callback(
    callback: CallbackQuery, text: str | None = None, show_alert: bool = False,
) -> None:
    try:
        await callback.answer(text=text, show_alert=show_alert)
    except Exception as exc:
        logger.debug("callback.answer failed: %s", exc)


def format_date_text_ru(target_date: date, current_year: int, lang: str = DEFAULT_LANG) -> str:
    return format_date_human(target_date, current_year, lang=lang)


def format_date_with_weekday(target_date: date, lang: str = DEFAULT_LANG) -> str:
    return _i18n_format_date_with_weekday(target_date, lang=lang)


async def get_user_main_menu_kb(
    user_id: int, create_btn_text: str | None = None, lang: str | None = None,
) -> InlineKeyboardMarkup:
    user_lang = lang or await get_user_language(user_id)
    is_adm = is_admin_id(user_id)
    has_sec = await user_has_invited_anyone(user_id)
    pending_count = await get_pending_notifications_count(user_id)
    return main_menu_kb(
        is_admin=is_adm,
        has_user_section=has_sec,
        has_pending_notifications=(pending_count > 0),
        create_btn_text=create_btn_text,
        webapp_url=WEBAPP_URL,
        lang=user_lang,
    )


async def sync_user_commands(bot: Bot, user_id: int, force: bool = False) -> None:
    pending_count = await get_pending_notifications_count(user_id)
    lang = await get_user_language(user_id)

    if is_admin_id(user_id):
        commands = [BotCommand(command="start", description=t(lang, "cmd_start"))]
        if pending_count > 0:
            commands.append(BotCommand(command="notifications", description=t(lang, "cmd_notifications")))
        commands.extend([
            BotCommand(command="reminders", description=t(lang, "cmd_reminders")),
            BotCommand(command="users", description=t(lang, "cmd_users")),
            BotCommand(command="settings", description=t(lang, "cmd_settings")),
        ])
    else:
        has_sec = await user_has_invited_anyone(user_id)
        commands = [BotCommand(command="start", description=t(lang, "cmd_start"))]
        if pending_count > 0:
            commands.append(BotCommand(command="notifications", description=t(lang, "cmd_notifications")))
        commands.append(BotCommand(command="reminders", description=t(lang, "cmd_reminders")))
        if has_sec:
            commands.append(BotCommand(command="user", description=t(lang, "cmd_users")))
        commands.extend([
            BotCommand(command="settings", description=t(lang, "cmd_settings")),
            BotCommand(command="info", description=t(lang, "cmd_info")),
        ])

    signature = tuple((c.command, c.description) for c in commands)
    if force or _LAST_SYNCED_COMMANDS.get(user_id) != signature:
        try:
            await bot.set_my_commands(commands, scope=BotCommandScopeChat(chat_id=user_id))
            _LAST_SYNCED_COMMANDS[user_id] = signature
        except Exception as exc:
            logger.debug("set_my_commands failed for user %s: %s", user_id, exc)

    desired_menu = f"webapp:{WEBAPP_URL}" if WEBAPP_URL else "commands"
    if force or _LAST_SYNCED_MENU_BUTTON.get(user_id) != desired_menu:
        try:
            if desired_menu.startswith("webapp:"):
                await bot.set_chat_menu_button(
                    chat_id=user_id,
                    menu_button=MenuButtonWebApp(text="Mini App", web_app=WebAppInfo(url=WEBAPP_URL)),
                )
            else:
                await bot.set_chat_menu_button(chat_id=user_id, menu_button=MenuButtonCommands())
            _LAST_SYNCED_MENU_BUTTON[user_id] = desired_menu
        except Exception as exc:
            logger.debug("set_chat_menu_button failed for user %s: %s", user_id, exc)


def add_months(src_date: date, months: int) -> date:
    total_months = (src_date.year * 12 + (src_date.month - 1)) + months
    year, month_zero = divmod(total_months, 12)
    month = month_zero + 1
    max_day = calendar.monthrange(year, month)[1]
    return date(year, month, min(src_date.day, max_day))


def add_one_month(src_date: date) -> date:
    return add_months(src_date, 1)


def add_one_year(src_date: date) -> date:
    return add_months(src_date, 12)


def step_year_month(year: int, month: int, direction: str) -> tuple[int, int]:
    if direction == "next":
        return (year + 1, 1) if month == 12 else (year, month + 1)
    return (year - 1, 12) if month == 1 else (year, month - 1)


def parse_user_date(raw: str, today: date) -> date | None:
    raw = raw.strip().replace("/", ".").replace("-", ".")
    for fmt in ("%d.%m.%Y", "%d.%m.%y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            pass
    try:
        parsed = datetime.strptime(raw, "%d.%m").date()
        candidate = date(today.year, parsed.month, parsed.day)
        if candidate < today:
            candidate = date(today.year + 1, parsed.month, parsed.day)
        return candidate
    except ValueError:
        return None


def parse_user_time(raw: str) -> time | None:
    match = re.match(r"^\s*(\d{1,2})\D+(\d{1,2})\s*$", raw)
    if not match:
        return None
    hour, minute = int(match.group(1)), int(match.group(2))
    if 0 <= hour <= 23 and 0 <= minute <= 59:
        return time(hour, minute)
    return None


def extract_message_text(message: Message, lang: str = DEFAULT_LANG) -> str | None:
    raw_plain = (message.text or message.caption or "").strip()
    if raw_plain:
        if len(raw_plain) > 1000:
            return html.escape(raw_plain[:997]) + "..."
        return (message.html_text or html.escape(raw_plain)).strip()

    if message.document:
        doc_name = message.document.file_name or t(lang, "msg_doc_fallback")
        text = t(lang, "msg_doc", name=html.escape(doc_name))
    elif message.photo:
        text = t(lang, "msg_photo")
    elif message.video:
        text = t(lang, "msg_video")
    elif message.voice:
        text = t(lang, "msg_voice")
    elif message.audio:
        title = message.audio.title or message.audio.file_name or t(lang, "msg_audio_fallback")
        text = t(lang, "msg_audio", title=html.escape(title))
    elif message.video_note:
        text = t(lang, "msg_video_note")
    elif message.contact:
        name = f"{message.contact.first_name or ''} {message.contact.last_name or ''}".strip()
        text = t(lang, "msg_contact", name=html.escape(name), phone=html.escape(message.contact.phone_number or ""))
    elif message.location:
        text = t(lang, "msg_location", lat=message.location.latitude, lon=message.location.longitude)
    elif message.poll:
        text = t(lang, "msg_poll", question=html.escape(message.poll.question))
    elif message.forward_origin or message.forward_date:
        text = t(lang, "msg_forwarded")
    else:
        return None

    if len(text) > 1000:
        text = text[:997] + "..."
    return text


async def safe_delete_message(bot: Bot, chat_id: int, message_id: int) -> bool:
    try:
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
        return True
    except TelegramForbiddenError:
        return True
    except TelegramBadRequest as exc:
        if any(marker in str(exc).lower() for marker in _PERMANENT_DELETE_ERRORS):
            return True
        logger.debug("Transient TelegramBadRequest deleting msg %s in %s: %s", message_id, chat_id, exc)
        return False
    except Exception as exc:
        logger.debug("Transient error deleting msg %s in %s: %s", message_id, chat_id, exc)
        return False


async def safe_delete_messages_batch(
    bot: Bot, chat_id: int, message_ids: list[int], requeue_on_failure: bool = True,
) -> list[int]:
    unique_ids = sorted({int(mid) for mid in message_ids if mid and int(mid) > 0})
    if not unique_ids:
        return []
    failed_ids: list[int] = []
    for i in range(0, len(unique_ids), 100):
        chunk = unique_ids[i : i + 100]
        try:
            await bot.delete_messages(chat_id=chat_id, message_ids=chunk)
        except Exception:
            results = await asyncio.gather(*(safe_delete_message(bot, chat_id, mid) for mid in chunk))
            for mid, ok in zip(chunk, results):
                if not ok:
                    failed_ids.append(mid)
    if failed_ids and requeue_on_failure:
        try:
            await add_tracked_messages_batch(chat_id, failed_ids)
        except Exception as exc:
            logger.debug("Failed to requeue undeleted messages for %s: %s", chat_id, exc)
    return failed_ids


async def cleanup_old_messages(bot: Bot, user_id: int) -> None:
    tracked_ids = await pop_tracked_messages(user_id)
    if tracked_ids:
        await safe_delete_messages_batch(bot, user_id, tracked_ids)


async def clear_chat_window(bot: Bot, user_id: int, extra_ids: list[int] | None = None) -> None:
    ids_to_delete = await pop_all_window_messages(user_id)
    if extra_ids:
        ids_to_delete.extend(extra_ids)
    if ids_to_delete:
        await safe_delete_messages_batch(bot, user_id, ids_to_delete)


async def render_panel(
    bot: Bot, user_id: int, text: str, reply_markup: InlineKeyboardMarkup,
    force_new: bool = False, cleanup: bool = True, extra_delete_ids: list[int] | None = None,
) -> None:
    panel_id = await get_panel_message_id(user_id)
    old_panel_to_delete: int | None = None

    if panel_id and not force_new:
        try:
            await bot.edit_message_text(chat_id=user_id, message_id=panel_id, text=text, reply_markup=reply_markup)
            ids_to_delete = await pop_tracked_messages(user_id) if cleanup else []
            if extra_delete_ids:
                ids_to_delete.extend(extra_delete_ids)
            if ids_to_delete:
                await safe_delete_messages_batch(bot, user_id, ids_to_delete)
            return
        except TelegramBadRequest as e:
            if "message is not modified" in str(e).lower():
                ids_to_delete = await pop_tracked_messages(user_id) if cleanup else []
                if extra_delete_ids:
                    ids_to_delete.extend(extra_delete_ids)
                if ids_to_delete:
                    await safe_delete_messages_batch(bot, user_id, ids_to_delete)
                return
            old_panel_to_delete = panel_id
    elif panel_id and force_new:
        old_panel_to_delete = panel_id

    sent = await bot.send_message(chat_id=user_id, text=text, reply_markup=reply_markup, disable_notification=True)
    await set_panel_message_id(user_id, sent.message_id)

    ids_to_delete = await pop_tracked_messages(user_id) if cleanup else []
    if old_panel_to_delete:
        ids_to_delete.append(old_panel_to_delete)
    if extra_delete_ids:
        ids_to_delete.extend(extra_delete_ids)
    if ids_to_delete:
        await safe_delete_messages_batch(bot, user_id, ids_to_delete)


async def build_home_text(
    user_id: int, notice: str = "", show_footer: bool = True, lang: str | None = None,
) -> str:
    user_lang = lang or await get_user_language(user_id)
    user_now, _ = await get_user_now(user_id)
    time_str = user_now.strftime("%H:%M")
    date_str = format_full_date_human(user_now.date(), lang=user_lang)
    parts = [t(user_lang, "home_now", time=time_str, date=date_str)]
    if notice:
        parts.append(notice)
    if show_footer:
        parts.append(t(user_lang, "home_footer"))
    return "\n\n".join(parts)


async def start_date_selection(
    bot: Bot, user_id: int, state: FSMContext, reminder_text: str,
    header_title: str | None = None, lang: str | None = None,
) -> None:
    user_lang = lang or await get_user_language(user_id)
    await state.update_data(reminder_text=reminder_text)
    await state.set_state(ReminderFSM.waiting_for_date)
    resolved_header = header_title or t(user_lang, "create_step2_header")
    text = t(user_lang, "create_step2_body", header=resolved_header, text=reminder_text)
    await render_panel(bot=bot, user_id=user_id, text=text, reply_markup=date_selection_kb(lang=user_lang))
