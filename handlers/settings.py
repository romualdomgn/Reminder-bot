from datetime import datetime, timezone
from aiogram import Router, Bot, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery

from database import (
    get_user_language,
    get_user_now,
    set_user_language,
    set_user_offset_minutes,
    format_tz_label,
)
from i18n import SUPPORTED_LANGS, get_lang_display_name, t
from keyboards import language_selection_kb, settings_menu_kb, tz_selection_kb
from .states import ReminderFSM
from .common import (
    parse_cb_signed_int,
    safe_delete_message,
    safe_answer_callback,
    render_panel,
    parse_user_time,
    sync_user_commands,
)

router = Router()


async def show_settings_screen(bot: Bot, user_id: int, notice: str = "") -> None:
    lang = await get_user_language(user_id)
    user_now, offset_mins = await get_user_now(user_id)
    tz_label = format_tz_label(offset_mins, lang=lang)
    notice_block = f"{notice}\n\n" if notice else ""

    text = (
        f"{t(lang, 'settings_title')}\n\n"
        f"{notice_block}"
        f"{t(lang, 'settings_current_time', dt=user_now.strftime('%d.%m.%Y %H:%M'), tz=tz_label)}\n"
        f"{t(lang, 'settings_current_lang', lang_name=get_lang_display_name(lang))}\n\n"
        f"{t(lang, 'settings_choose')}"
    )
    await render_panel(bot=bot, user_id=user_id, text=text, reply_markup=settings_menu_kb(lang=lang))


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


@router.callback_query(F.data == "menu:lang")
async def cb_menu_lang(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await safe_answer_callback(callback)
    await state.clear()
    uid = callback.from_user.id
    lang = await get_user_language(uid)
    text = (
        f"{t(lang, 'lang_title')}\n\n"
        f"{t(lang, 'lang_current', lang_name=get_lang_display_name(lang))}\n\n"
        f"{t(lang, 'lang_prompt')}"
    )
    await render_panel(bot=bot, user_id=uid, text=text, reply_markup=language_selection_kb(current_lang=lang))


@router.callback_query(F.data.startswith("lang:"))
async def cb_set_lang_button(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    parts = callback.data.split(":")
    new_lang = parts[1].strip().lower() if len(parts) > 1 else ""
    if new_lang not in SUPPORTED_LANGS:
        await safe_answer_callback(callback)
        return
    uid = callback.from_user.id
    saved_lang = await set_user_language(uid, new_lang)
    await state.clear()
    await sync_user_commands(bot, uid, force=True)
    await safe_answer_callback(callback, t(saved_lang, "lang_updated_cb"))
    notice = t(saved_lang, "lang_updated_notice", lang_name=get_lang_display_name(saved_lang))
    await show_settings_screen(bot, uid, notice=notice)


@router.callback_query(F.data == "menu:tz")
async def cb_menu_tz(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await safe_answer_callback(callback)
    await state.clear()
    await state.set_state(ReminderFSM.waiting_for_device_time)
    uid = callback.from_user.id
    lang = await get_user_language(uid)
    user_now, offset_mins = await get_user_now(uid)
    tz_label = format_tz_label(offset_mins, lang=lang)
    text = (
        f"{t(lang, 'tz_title')}\n\n"
        f"{t(lang, 'tz_current', time=user_now.strftime('%H:%M'), tz=tz_label)}\n\n"
        f"{t(lang, 'tz_prompt')}"
    )
    await render_panel(bot=bot, user_id=uid, text=text, reply_markup=tz_selection_kb(lang=lang))


@router.callback_query(F.data.startswith("tz:"))
async def cb_set_tz_button(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    offset_minutes = parse_cb_signed_int(callback.data.split(":"), 1)
    if offset_minutes is None or not (-720 <= offset_minutes <= 840):
        await safe_answer_callback(callback)
        return
    uid = callback.from_user.id
    lang = await get_user_language(uid)
    await set_user_offset_minutes(uid, offset_minutes)
    await state.clear()
    await safe_answer_callback(callback, t(lang, "tz_updated_cb"))
    user_now, _ = await get_user_now(uid)
    tz_label = format_tz_label(offset_minutes, lang=lang)
    notice = t(lang, "tz_synced_notice", dt=user_now.strftime("%d.%m.%Y %H:%M"), tz=tz_label)
    await show_settings_screen(bot, uid, notice=notice)


@router.message(ReminderFSM.waiting_for_device_time, F.text)
async def process_device_time_sync(message: Message, state: FSMContext, bot: Bot) -> None:
    await safe_delete_message(bot, message.chat.id, message.message_id)
    uid = message.from_user.id
    lang = await get_user_language(uid)
    parsed_time = parse_user_time(message.text)
    if not parsed_time:
        text = f"{t(lang, 'tz_title')}\n\n{t(lang, 'tz_bad_format')}"
        await render_panel(bot, uid, text, tz_selection_kb(lang=lang))
        return

    utc_now = datetime.now(timezone.utc)
    diff = (parsed_time.hour * 60 + parsed_time.minute) - (utc_now.hour * 60 + utc_now.minute)
    if diff > 840:
        diff -= 1440
    elif diff < -720:
        diff += 1440

    offset_minutes = int(round(diff / 15.0) * 15)
    await set_user_offset_minutes(uid, offset_minutes)
    await state.clear()

    user_now, _ = await get_user_now(uid)
    tz_label = format_tz_label(offset_minutes, lang=lang)
    notice = t(lang, "tz_synced_device_notice", dt=user_now.strftime("%d.%m.%Y %H:%M"), tz=tz_label)
    await show_settings_screen(bot, uid, notice=notice)
