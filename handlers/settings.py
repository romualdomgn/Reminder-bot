from datetime import datetime, timezone
from aiogram import Router, Bot, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery

from database import (
    get_user_now,
    set_user_offset_minutes,
    format_tz_label,
)
from keyboards import settings_menu_kb, tz_selection_kb
from .states import ReminderFSM
from .common import (
    safe_delete_message,
    safe_answer_callback,
    render_panel,
    parse_user_time,
)

router = Router()


async def show_settings_screen(bot: Bot, user_id: int, notice: str = "") -> None:
    user_now, offset_mins = await get_user_now(user_id)
    tz_label = format_tz_label(offset_mins)
    notice_block = f"{notice}\n\n" if notice else ""

    text = (
        "⚙️ <b>Раздел «Настройки»</b>\n\n"
        f"{notice_block}"
        f"🕒 Текущее время: <code>{user_now.strftime('%d.%m.%Y %H:%M')} — {tz_label}</code>\n\n"
        "Выберите нужный пункт настроек:"
    )
    await render_panel(
        bot=bot,
        user_id=user_id,
        text=text,
        reply_markup=settings_menu_kb(),
    )


@router.message(Command("settings", ignore_case=True))
async def cmd_settings(message: Message, state: FSMContext, bot: Bot) -> None:
    await safe_delete_message(bot, message.chat.id, message.message_id)
    await state.clear()
    await show_settings_screen(bot, message.from_user.id)


@router.callback_query(F.data == "menu:settings")
async def cb_menu_settings(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await safe_answer_callback(callback)
    await state.clear()
    await show_settings_screen(bot, callback.from_user.id)


@router.callback_query(F.data == "menu:tz")
async def cb_menu_tz(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await safe_answer_callback(callback)
    await state.clear()
    await state.set_state(ReminderFSM.waiting_for_device_time)
    user_now, offset_mins = await get_user_now(callback.from_user.id)
    tz_label = format_tz_label(offset_mins)

    text = (
        "🕒 <b>Настроить время бота</b>\n\n"
        f"Сейчас установлено: <code>{user_now.strftime('%H:%M')} — {tz_label}</code>\n\n"
        "Выберите часовой пояс кнопкой ниже <b>ИЛИ отправьте в чат текущее время на вашем устройстве</b> "
        "в формате <code>ЧЧ:ММ</code> (например, <code>21:30</code>):"
    )
    await render_panel(
        bot=bot,
        user_id=callback.from_user.id,
        text=text,
        reply_markup=tz_selection_kb(),
    )


@router.callback_query(F.data.startswith("tz:"))
async def cb_set_tz_button(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    offset_minutes = int(callback.data.split(":")[1])
    await set_user_offset_minutes(callback.from_user.id, offset_minutes)
    await state.clear()
    await safe_answer_callback(callback, "Время обновлено!")

    user_now, _ = await get_user_now(callback.from_user.id)
    tz_label = format_tz_label(offset_minutes)
    notice = f"✅ Время синхронизировано: <code>{user_now.strftime('%d.%m.%Y %H:%M')} — {tz_label}</code>"
    await show_settings_screen(bot, callback.from_user.id, notice=notice)


@router.message(ReminderFSM.waiting_for_device_time, F.text)
async def process_device_time_sync(message: Message, state: FSMContext, bot: Bot) -> None:
    await safe_delete_message(bot, message.chat.id, message.message_id)

    parsed_time = parse_user_time(message.text)
    if not parsed_time:
        text = (
            "🕒 <b>Настроить время бота</b>\n\n"
            "⚠️ <b>Неверный формат!</b>\n"
            "Введите текущее время с вашего устройства в формате <code>ЧЧ:ММ</code> (например, <code>19:45</code>) "
            "или нажмите одну из кнопок ниже:"
        )
        await render_panel(bot, message.from_user.id, text, tz_selection_kb())
        return

    utc_now = datetime.now(timezone.utc)
    utc_minutes = utc_now.hour * 60 + utc_now.minute
    device_minutes = parsed_time.hour * 60 + parsed_time.minute

    diff = device_minutes - utc_minutes
    if diff > 840:
        diff -= 1440
    elif diff < -720:
        diff += 1440

    offset_minutes = int(round(diff / 15.0) * 15)
    await set_user_offset_minutes(message.from_user.id, offset_minutes)
    await state.clear()

    user_now, _ = await get_user_now(message.from_user.id)
    tz_label = format_tz_label(offset_minutes)
    notice = f"✅ Время синхронизировано с устройством: <code>{user_now.strftime('%d.%m.%Y %H:%M')} — {tz_label}</code>"
    await show_settings_screen(bot, message.from_user.id, notice=notice)
