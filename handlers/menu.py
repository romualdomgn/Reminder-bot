from aiogram import Router, Bot, F
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery

from .common import (
    safe_delete_message,
    render_panel,
    build_home_text,
    get_user_main_menu_kb,
    sync_user_commands,
)

router = Router()


@router.message(CommandStart())
@router.message(Command("menu", ignore_case=True))
@router.message(Command("clear", ignore_case=True))
async def cmd_start(message: Message, state: FSMContext, bot: Bot) -> None:
    await safe_delete_message(bot, message.chat.id, message.message_id)
    await state.clear()
    uid = message.from_user.id
    await sync_user_commands(bot, uid)
    home_text = await build_home_text(uid)
    kb = await get_user_main_menu_kb(uid)
    await render_panel(
        bot=bot,
        user_id=uid,
        text=home_text,
        reply_markup=kb,
        force_new=True,
    )


@router.callback_query(F.data == "menu:home")
async def cb_menu_home(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await state.clear()
    uid = callback.from_user.id
    home_text = await build_home_text(uid)
    kb = await get_user_main_menu_kb(uid)
    await render_panel(
        bot=bot,
        user_id=uid,
        text=home_text,
        reply_markup=kb,
    )
    await callback.answer()
