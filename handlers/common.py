import asyncio
import calendar
import html
import re
from datetime import datetime, date, time
from aiogram import Bot
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, InlineKeyboardMarkup, BotCommand, BotCommandScopeChat
from aiogram.exceptions import TelegramBadRequest

from database import (
    get_panel_message_id,
    set_panel_message_id,
    pop_tracked_messages,
    pop_all_window_messages,
    get_user_now,
    format_tz_label,
    is_admin_id,
    user_has_invited_anyone,
)
from keyboards import main_menu_kb, date_selection_kb
from .states import ReminderFSM


async def get_user_main_menu_kb(
    user_id: int,
    create_btn_text: str = "➕ Создать напоминание",
) -> InlineKeyboardMarkup:
    if is_admin_id(user_id):
        return main_menu_kb(
            is_admin=True,
            has_user_section=False,
            create_btn_text=create_btn_text,
        )
    has_sec = await user_has_invited_anyone(user_id)
    return main_menu_kb(
        is_admin=False,
        has_user_section=has_sec,
        create_btn_text=create_btn_text,
    )


async def sync_user_commands(bot: Bot, user_id: int) -> None:
    if is_admin_id(user_id):
        return
    if await user_has_invited_anyone(user_id):
        commands = [
            BotCommand(command="start", description="🎛 Открыть пульт напоминаний"),
            BotCommand(command="reminders", description="📋 Напоминания"),
            BotCommand(command="user", description="👥 Пользователи"),
            BotCommand(command="settings", description="⚙️ Настройки"),
            BotCommand(command="info", description="ℹ️ Информация"),
        ]
        try:
            await bot.set_my_commands(commands, scope=BotCommandScopeChat(chat_id=user_id))
        except Exception:
            pass


def add_one_month(src_date: date) -> date:
    year = src_date.year + (src_date.month // 12)
    month = (src_date.month % 12) + 1
    max_day = calendar.monthrange(year, month)[1]
    return date(year, month, min(src_date.day, max_day))


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
    """Поддерживает ввод времени с любым знаком или символом между ЧЧ и ММ."""
    match = re.match(r"^\s*(\d{1,2})\D+(\d{1,2})\s*$", raw)
    if not match:
        return None
    hour, minute = int(match.group(1)), int(match.group(2))
    if 0 <= hour <= 23 and 0 <= minute <= 59:
        return time(hour, minute)
    return None


def extract_message_text(message: Message) -> str | None:
    text = (message.text or message.caption or "").strip()
    if not text:
        if message.document:
            text = f"📎 Документ: {message.document.file_name or 'файл'}"
        elif message.photo:
            text = "🖼 Фотография"
        elif message.video:
            text = "🎬 Видео"
        elif message.voice:
            text = "🎤 Голосовое сообщение"
        elif message.audio:
            text = f"🎵 Аудио: {message.audio.title or message.audio.file_name or 'аудиозапись'}"
        elif message.video_note:
            text = "📹 Видеосообщение"
        elif message.contact:
            name = f"{message.contact.first_name or ''} {message.contact.last_name or ''}".strip()
            text = f"👤 Контакт: {name} ({message.contact.phone_number})"
        elif message.location:
            text = f"📍 Геолокация: {message.location.latitude}, {message.location.longitude}"
        elif message.poll:
            text = f"📊 Опрос: {message.poll.question}"
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
    tracked_ids = await pop_tracked_messages(user_id) if cleanup else []
    if extra_delete_ids:
        tracked_ids.extend(extra_delete_ids)

    if panel_id and not force_new:
        try:
            await bot.edit_message_text(
                chat_id=user_id,
                message_id=panel_id,
                text=text,
                reply_markup=reply_markup,
            )
            if tracked_ids:
                await safe_delete_messages_batch(bot, user_id, tracked_ids)
            return
        except TelegramBadRequest as e:
            if "message is not modified" in str(e).lower():
                if tracked_ids:
                    await safe_delete_messages_batch(bot, user_id, tracked_ids)
                return
            tracked_ids.append(panel_id)

    elif panel_id and force_new:
        tracked_ids.append(panel_id)

    sent = await bot.send_message(
        chat_id=user_id,
        text=text,
        reply_markup=reply_markup,
    )
    await set_panel_message_id(user_id, sent.message_id)

    if tracked_ids:
        await safe_delete_messages_batch(bot, user_id, tracked_ids)


async def build_home_text(
    user_id: int,
    notice: str = "",
    show_footer: bool = True,
) -> str:
    user_now, offset_mins = await get_user_now(user_id)
    current_str = user_now.strftime("%d.%m.%Y %H:%M")
    tz_label = format_tz_label(offset_mins)
    parts = [
        "🎛 <b>Пульт управления напоминаниями</b>\n"
        f"🕒 Ваше время: <code>{current_str} ({tz_label})</code>"
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
    header_title: str = "📅 <b>Создание напоминания — Выбор даты</b>",
) -> None:
    await state.update_data(reminder_text=reminder_text)
    await state.set_state(ReminderFSM.waiting_for_date)

    safe_preview = html.escape(reminder_text)
    text = (
        f"{header_title}\n\n"
        f"💬 <b>Сообщение:</b> <i>{safe_preview}</i>\n\n"
        "Выберите, <b>в какой день</b> прислать напоминание, или нажмите кнопку для ручного ввода даты:"
    )
    await render_panel(
        bot=bot,
        user_id=user_id,
        text=text,
        reply_markup=date_selection_kb(),
    )
