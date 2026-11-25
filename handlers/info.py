import html
from aiogram import Router, Bot, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery

from config import REPOSITORY_URL, ADMIN_TG_USERNAME, get_app_version_info
from database import get_user_language
from i18n import t
from keyboards import info_menu_kb, info_card_kb
from .common import safe_delete_message, safe_answer_callback, render_panel

router = Router()


async def show_info_main(bot: Bot, user_id: int) -> None:
    lang = await get_user_language(user_id)
    await render_panel(bot=bot, user_id=user_id, text=t(lang, "info_title"), reply_markup=info_menu_kb(lang=lang))


@router.message(Command("info", ignore_case=True))
async def cmd_info(message: Message, state: FSMContext, bot: Bot) -> None:
    await safe_delete_message(bot, message.chat.id, message.message_id)
    await state.clear()
    await show_info_main(bot, message.from_user.id)


@router.callback_query(F.data == "info:main")
async def cb_info_main(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await safe_answer_callback(callback)
    await state.clear()
    await show_info_main(bot, callback.from_user.id)


async def _show_info_key(callback: CallbackQuery, state: FSMContext, bot: Bot, key: str) -> None:
    await safe_answer_callback(callback)
    await state.clear()
    uid = callback.from_user.id
    lang = await get_user_language(uid)
    await render_panel(bot=bot, user_id=uid, text=t(lang, key), reply_markup=info_card_kb(lang=lang))


@router.callback_query(F.data == "info:reminders")
async def cb_info_reminders(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await _show_info_key(callback, state, bot, "info_chat_reminders")


@router.callback_query(F.data == "info:notifications")
async def cb_info_notifications(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await _show_info_key(callback, state, bot, "info_chat_notifications")


@router.callback_query(F.data == "info:settings")
async def cb_info_settings(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await _show_info_key(callback, state, bot, "info_chat_settings")


@router.callback_query(F.data == "info:add_user")
async def cb_info_add_user(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await _show_info_key(callback, state, bot, "info_chat_add_user")


@router.callback_query(F.data == "info:app_mode")
async def cb_info_app_mode(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await _show_info_key(callback, state, bot, "info_chat_app_mode")


@router.callback_query(F.data == "info:general")
async def cb_info_general(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await safe_answer_callback(callback)
    await state.clear()
    uid = callback.from_user.id
    lang = await get_user_language(uid)
    version_str, last_update_str = get_app_version_info()
    text = t(
        lang,
        "info_chat_general",
        repo=html.escape(REPOSITORY_URL),
        admin=html.escape(ADMIN_TG_USERNAME),
        ver=version_str,
        date=last_update_str,
    )
    await render_panel(bot=bot, user_id=uid, text=text, reply_markup=info_card_kb(lang=lang))
