import asyncio
import calendar
import html
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
from aiogram.exceptions import TelegramBadRequest

from config import WEBAPP_URL
from database import (
    get_panel_message_id,
    set_panel_message_id,
    pop_tracked_messages,
    pop_all_window_messages,
    get_user_now,
    is_admin_id,
    user_has_invited_anyone,
    get_pending_notifications_count,
)
from keyboards import main_menu_kb, date_selection_kb
from .states import ReminderFSM

RU_MONTHS_GENITIVE: dict[int, str] = {
    1: "января", 2: "февраля", 3: "марта", 4: "апреля",
    5: "мая", 6: "июня", 7: "июля", 8: "августа",
    9: "сентября", 10: "октября", 11: "ноября", 12: "декабря",
}

RU_WEEKDAYS: dict[int, str] = {
    0: "понедельник",
    1: "вторник",
    2: "среда",
    3: "четверг",
    4: "пятница",
    5: "суббота",
    6: "воскресенье",
}

_LAST_SYNCED_COMMANDS: dict[int, tuple[tuple[str, str], ...]] = {}
_LAST_SYNCED_MENU_BUTTON: dict[int, str] = {}


async def safe_answer_callback(
    callback: CallbackQuery,
    text: str | None = None,
    show_alert: bool = False,
) -> None:
    try:
        await callback.answer(text=text, show_alert=show_alert)
    except Exception:
        pass


def format_date_text_ru(target_date: date, current_year: int) -> str:
    month_str = RU_MONTHS_GENITIVE[target_date.month]
    if target_date.year == current_year:
        return f"{target_date.day} {month_str}"
    return f"{target_date.day} {month_str} {target_date.year}"


def format_date_with_weekday(target_date: date) -> str:
    return f"{target_date.strftime('%d.%m.%Y')}, {RU_WEEKDAYS[target_date.weekday()]}"


async def get_user_main_menu_kb(
    user_id: int,
    create_btn_text: str = "➕ Создать напоминание",
) -> InlineKeyboardMarkup:
    is_adm = is_admin_id(user_id)
    has_sec = await user_has_invited_anyone(user_id)
    pending_count = await get_pending_notifications_count(user_id)
    return main_menu_kb(
        is_admin=is_adm,
        has_user_section=has_sec,
        has_pending_notifications=(pending_count > 0),
        create_btn_text=create_btn_text,
        webapp_url=WEBAPP_URL,
    )


async def sync_user_commands(bot: Bot, user_id: int, force: bool = False) -> None:
    pending_count = await get_pending_notifications_count(user_id)

    if is_admin_id(user_id):
        commands = [BotCommand(command="start", description="🧭 Главное меню")]
        if pending_count > 0:
            commands.append(BotCommand(command="notifications", description="🔔 Уведомления"))
        commands.extend([
            BotCommand(command="reminders", description="📋 Напоминания"),
            BotCommand(command="users", description="👥 Пользователи"),
            BotCommand(command="settings", description="⚙️ Настройки"),
        ])
    else:
        has_sec = await user_has_invited_anyone(user_id)
        commands = [BotCommand(command="start", description="🧭 Главное меню")]
        if pending_count > 0:
            commands.append(BotCommand(command="notifications", description="🔔 Уведомления"))
        commands.append(BotCommand(command="reminders", description="📋 Напоминания"))
        if has_sec:
            commands.append(BotCommand(command="user", description="👥 Пользователи"))
        commands.extend([
            BotCommand(command="settings", description="⚙️ Настройки"),
            BotCommand(command="info", description="ℹ️ Информация"),
        ])

    signature = tuple((c.command, c.description) for c in commands)
    if force or _LAST_SYNCED_COMMANDS.get(user_id) != signature:
        try:
            await bot.set_my_commands(commands, scope=BotCommandScopeChat(chat_id=user_id))
            _LAST_SYNCED_COMMANDS[user_id] = signature
        except Exception:
            pass

    # Кнопка Menu -> Mini App пока включается только для ADMIN_TELEGRAM_ID
    desired_menu = f"webapp:{WEBAPP_URL}" if WEBAPP_URL else "commands"
    if force or _LAST_SYNCED_MENU_BUTTON.get(user_id) != desired_menu:
        try:
            if desired_menu.startswith("webapp:"):
                await bot.set_chat_menu_button(
                    chat_id=user_id,
                    menu_button=MenuButtonWebApp(
                        text="Mini App",
                        web_app=WebAppInfo(url=WEBAPP_URL),
                    ),
                )
            else:
                await bot.set_chat_menu_button(
                    chat_id=user_id,
                    menu_button=MenuButtonCommands(),
                )
            _LAST_SYNCED_MENU_BUTTON[user_id] = desired_menu
        except Exception:
            pass


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


def extract_message_text(message: Message) -> str | None:
    raw_plain = (message.text or message.caption or "").strip()
    if raw_plain:
        if len(raw_plain) > 1000:
            return html.escape(raw_plain[:997]) + "..."
        return (message.html_text or html.escape(raw_plain)).strip()

    if message.document:
        text = f"📎 Документ: {html.escape(message.document.file_name or 'файл')}"
    elif message.photo:
        text = "🖼 Фотография"
    elif message.video:
        text = "🎬 Видео"
    elif message.voice:
        text = "🎤 Голосовое сообщение"
    elif message.audio:
        title = message.audio.title or message.audio.file_name or "аудиозапись"
        text = f"🎵 Аудио: {html.escape(title)}"
    elif message.video_note:
        text = "📹 Видеосообщение"
    elif message.contact:
        name = f"{message.contact.first_name or ''} {message.contact.last_name or ''}".strip()
        text = f"👤 Контакт: {html.escape(name)} ({html.escape(message.contact.phone_number or '')})"
    elif message.location:
        text = f"📍 Геолокация: {message.location.latitude}, {message.location.longitude}"
    elif message.poll:
        text = f"📊 Опрос: {html.escape(message.poll.question)}"
    elif message.forward_origin or message.forward_date:
        text = "📌 Пересланное сообщение"
    else:
        return None

    if len(text) > 1000:
        text = text[:997] + "..."
    return text


async def safe_delete_message(bot: Bot, chat_id: int, message_id: int) -> None:
    try:
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
    except Exception:
        pass


async def safe_delete_messages_batch(bot: Bot, chat_id: int, message_ids: list[int]) -> None:
    unique_ids = sorted({int(mid) for mid in message_ids if mid and int(mid) > 0})
    if not unique_ids:
        return
    for i in range(0, len(unique_ids), 100):
        chunk = unique_ids[i : i + 100]
        try:
            await bot.delete_messages(chat_id=chat_id, message_ids=chunk)
        except Exception:
            await asyncio.gather(
                *(safe_delete_message(bot, chat_id, mid) for mid in chunk),
                return_exceptions=True,
            )


async def cleanup_old_messages(bot: Bot, user_id: int) -> None:
    tracked_ids = await pop_tracked_messages(user_id)
    if tracked_ids:
        await safe_delete_messages_batch(bot, user_id, tracked_ids)


async def clear_chat_window(
    bot: Bot, user_id: int, extra_ids: list[int] | None = None
) -> None:
    ids_to_delete = await pop_all_window_messages(user_id)
    if extra_ids:
        ids_to_delete.extend(extra_ids)
    if ids_to_delete:
        await safe_delete_messages_batch(bot, user_id, ids_to_delete)


async def render_panel(
    bot: Bot,
    user_id: int,
    text: str,
    reply_markup: InlineKeyboardMarkup,
    force_new: bool = False,
    cleanup: bool = True,
    extra_delete_ids: list[int] | None = None,
) -> None:
    panel_id = await get_panel_message_id(user_id)
    old_panel_to_delete: int | None = None

    if panel_id and not force_new:
        try:
            await bot.edit_message_text(
                chat_id=user_id,
                message_id=panel_id,
                text=text,
                reply_markup=reply_markup,
            )
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

    sent = await bot.send_message(
        chat_id=user_id,
        text=text,
        reply_markup=reply_markup,
        disable_notification=True,
    )
    await set_panel_message_id(user_id, sent.message_id)

    ids_to_delete = await pop_tracked_messages(user_id) if cleanup else []
    if old_panel_to_delete:
        ids_to_delete.append(old_panel_to_delete)
    if extra_delete_ids:
        ids_to_delete.extend(extra_delete_ids)

    if ids_to_delete:
        await safe_delete_messages_batch(bot, user_id, ids_to_delete)


async def build_home_text(
    user_id: int,
    notice: str = "",
    show_footer: bool = True,
) -> str:
    user_now, _ = await get_user_now(user_id)
    time_str = user_now.strftime("%H:%M")
    date_ru = f"{user_now.day} {RU_MONTHS_GENITIVE[user_now.month]} {user_now.year}"

    parts = [
        f"Сейчас {time_str}, {date_ru}"
    ]
    if notice:
        parts.append(notice)
    if show_footer:
        parts.append(
            "Выберите действие кнопками ниже, напишите текст или <b>перешлите сюда сообщение</b> из любого чата."
        )
    return "\n\n".join(parts)


async def start_date_selection(
    bot: Bot,
    user_id: int,
    state: FSMContext,
    reminder_text: str,
    header_title: str = "📅 <b>Создание напоминания - Шаг 2 из 4</b>",
) -> None:
    await state.update_data(reminder_text=reminder_text)
    await state.set_state(ReminderFSM.waiting_for_date)

    text = (
        f"{header_title}\n"
        "Выберите желаемую дату\n\n"
        f"💬 <b>Сообщение:</b>\n{reminder_text}"
    )
    await render_panel(
        bot=bot,
        user_id=user_id,
        text=text,
        reply_markup=date_selection_kb(),
    )
