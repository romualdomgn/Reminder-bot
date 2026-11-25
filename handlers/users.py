import html
import logging
from datetime import timedelta
from aiogram import Router, Bot, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, MenuButtonCommands

from config import ADMIN_IDS, clear_last_deleted_reminder, clear_rendered_reminders_state
from database import (
    add_tracked_message,
    is_admin_id,
    get_all_bot_users,
    get_admin_my_users,
    get_admin_other_users,
    get_bot_user_names_map,
    get_bot_user,
    add_bot_user,
    update_bot_user_name,
    remove_bot_user_with_cleanup,
    user_has_invited_anyone,
    get_invited_users,
    get_invited_bot_user,
    update_invited_bot_user_name,
    get_user_language,
    get_user_now,
)
from i18n import DEFAULT_LANG, t
from keyboards import (
    admin_ok_kb,
    get_grid_page_count,
    users_section_kb,
    users_sublist_kb,
    add_user_cancel_kb,
    users_edit_select_kb,
    user_edit_card_kb,
    user_edit_name_cancel_kb,
    users_delete_kb,
    user_delete_confirm_kb,
    my_users_section_kb,
    my_users_edit_select_kb,
    my_user_edit_card_kb,
    my_user_edit_name_cancel_kb,
    my_users_delete_kb,
    my_user_delete_confirm_kb,
)
from .states import ReminderFSM
from .settings import show_settings_screen
from middlewares import clear_user_lock
from .common import (
    clear_user_sync_cache,
    parse_cb_int,
    safe_delete_message,
    safe_delete_messages_batch,
    safe_answer_callback,
    render_panel,
    build_home_text,
    get_user_main_menu_kb,
    sync_user_commands,
)

logger = logging.getLogger(__name__)
router = Router()


def cleanup_user_memory(user_id: int) -> None:
    clear_last_deleted_reminder(user_id)
    clear_rendered_reminders_state(user_id)
    clear_user_lock(user_id)
    clear_user_sync_cache(user_id)


def _build_users_list_text(users: list, notice: str = "", error_msg: str = "", lang: str = DEFAULT_LANG) -> str:
    lines = [t(lang, "users_title")]
    if notice:
        lines.append(notice)
    if not users:
        lines.append(t(lang, "users_empty"))
    else:
        user_lines = [t(lang, "users_total", count=len(users)) + "\n"]
        for idx, u in enumerate(users, start=1):
            role = t(lang, "role_admin") if u.is_admin else t(lang, "role_user")
            display_name = html.escape(u.name) if u.name else t(lang, "no_name_html")
            user_lines.append(f"<b>{idx}.</b> <b>{display_name}</b> (<code>{u.user_id}</code>) — {role}")
        lines.append("\n".join(user_lines))
    if error_msg:
        lines.append(error_msg)
    return "\n\n".join(lines)


async def show_users_screen(bot: Bot, admin_id: int, notice: str = "", cleanup: bool = False, extra_delete_ids: list[int] | None = None) -> None:
    lang = await get_user_language(admin_id)
    users = await get_all_bot_users()
    await render_panel(
        bot=bot, user_id=admin_id, text=_build_users_list_text(users, notice=notice, lang=lang),
        reply_markup=users_section_kb(has_users=bool(users), has_removable_users=any(not u.is_admin for u in users), lang=lang),
        cleanup=cleanup, extra_delete_ids=extra_delete_ids,
    )


async def show_users_select_grid(bot: Bot, admin_id: int, state: FSMContext, mode: str = "edit", page: int = 0, error_msg: str = "") -> None:
    lang = await get_user_language(admin_id)
    users = await get_all_bot_users()
    if not users:
        await state.clear()
        await show_users_screen(bot, admin_id, notice=t(lang, "users_empty_notice"), cleanup=False)
        return
    user_num_map: dict[str, int] = {}
    items: list[tuple[int, int]] = []
    for idx, u in enumerate(users, start=1):
        user_num_map[str(idx)] = u.user_id
        if mode != "delete" or not u.is_admin:
            items.append((idx, u.user_id))
    if not items:
        await state.clear()
        await show_users_screen(bot, admin_id, notice=t(lang, "users_no_removable"), cleanup=False)
        return
    page = max(0, min(page, max(0, get_grid_page_count(len(items)) - 1)))
    if mode == "delete":
        await state.set_state(ReminderFSM.waiting_for_del_user_id)
        kb = users_delete_kb(items, page=page, lang=lang)
    else:
        await state.set_state(ReminderFSM.waiting_for_edit_user_id)
        kb = users_edit_select_kb(items, page=page, lang=lang)
    await state.update_data(user_num_map=user_num_map, users_select_page=page, users_select_mode=mode)
    await render_panel(bot=bot, user_id=admin_id, text=_build_users_list_text(users, error_msg=error_msg, lang=lang), reply_markup=kb, cleanup=False)


async def show_user_delete_confirm(bot: Bot, admin_id: int, target_user_id: int, back_callback: str = "users:list") -> None:
    lang = await get_user_language(admin_id)
    if is_admin_id(target_user_id):
        await show_users_screen(bot, admin_id, notice=t(lang, "users_cannot_del_admin"), cleanup=False)
        return
    user = await get_bot_user(target_user_id)
    if not user or user.is_admin:
        await show_users_screen(bot, admin_id, notice=t(lang, "users_not_found_del", uid=target_user_id), cleanup=False)
        return
    display_name = html.escape(user.name) if user.name else t(lang, "no_name_html")
    await render_panel(
        bot=bot, user_id=admin_id, text=t(lang, "users_del_confirm", name=display_name, uid=user.user_id),
        reply_markup=user_delete_confirm_kb(user.user_id, back_callback=back_callback, lang=lang), cleanup=False,
    )


async def show_admin_my_users_screen(bot: Bot, admin_id: int) -> None:
    lang = await get_user_language(admin_id)
    my_added_users = await get_admin_my_users()
    _, offset_mins = await get_user_now(admin_id)
    delta = timedelta(minutes=offset_mins)
    lines = [t(lang, "users_admin_my_title")]
    if not my_added_users:
        lines.append(t(lang, "users_admin_my_empty"))
    else:
        user_lines = [t(lang, "users_admin_my_total", count=len(my_added_users)) + "\n"]
        for idx, u in enumerate(my_added_users, start=1):
            display_name = html.escape(u.name) if u.name else t(lang, "no_name_html")
            created_str = (u.created_at + delta).strftime("%d.%m.%Y %H:%M")
            user_lines.append(f"<b>{idx}.</b> <b>{display_name}</b> (<code>{u.user_id}</code>)\n   {t(lang, 'users_added_date', dt=created_str)}")
        lines.append("\n\n".join(user_lines))
    await render_panel(bot=bot, user_id=admin_id, text="\n\n".join(lines), reply_markup=users_sublist_kb(lang=lang), cleanup=False)


async def show_admin_all_users_screen(bot: Bot, admin_id: int) -> None:
    lang = await get_user_language(admin_id)
    other_added_users = await get_admin_other_users()
    inviter_names = await get_bot_user_names_map({u.invited_by for u in other_added_users if u.invited_by is not None})
    _, offset_mins = await get_user_now(admin_id)
    delta = timedelta(minutes=offset_mins)
    lines = [t(lang, "users_admin_all_title")]
    if not other_added_users:
        lines.append(t(lang, "users_admin_all_empty"))
    else:
        user_lines = [t(lang, "users_admin_all_total", count=len(other_added_users)) + "\n"]
        for idx, u in enumerate(other_added_users, start=1):
            display_name = html.escape(u.name) if u.name else t(lang, "no_name_html")
            created_str = (u.created_at + delta).strftime("%d.%m.%Y %H:%M")
            if u.invited_by in inviter_names:
                raw_inv_name = inviter_names[u.invited_by]
                inv_name = html.escape(raw_inv_name) if raw_inv_name else t(lang, "no_name")
                inviter_label = f"<b>{inv_name}</b> (<code>{u.invited_by}</code>)"
            else:
                inviter_label = f"<code>{u.invited_by}</code>"
            user_lines.append(
                f"<b>{idx}.</b> <b>{display_name}</b> (<code>{u.user_id}</code>)\n"
                f"   {t(lang, 'users_added_date', dt=created_str)}\n"
                f"   {t(lang, 'users_added_by', inviter=inviter_label)}"
            )
        lines.append("\n\n".join(user_lines))
    await render_panel(bot=bot, user_id=admin_id, text="\n\n".join(lines), reply_markup=users_sublist_kb(lang=lang), cleanup=False)


@router.message(Command("users", ignore_case=True))
async def cmd_users(message: Message, state: FSMContext, bot: Bot) -> None:
    await state.clear()
    uid = message.from_user.id
    if not is_admin_id(uid):
        lang = await get_user_language(uid)
        await render_panel(bot, uid, await build_home_text(uid, notice=t(lang, "admin_only_users_cmd"), lang=lang), await get_user_main_menu_kb(uid, lang=lang), extra_delete_ids=[message.message_id])
        return
    await show_users_screen(bot, uid, cleanup=True, extra_delete_ids=[message.message_id])


@router.callback_query(F.data == "users:list")
async def cb_users_list(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    uid = callback.from_user.id
    if not is_admin_id(uid):
        await safe_answer_callback(callback, t(await get_user_language(uid), "admin_only"), show_alert=True)
        return
    await safe_answer_callback(callback)
    await state.clear()
    await show_users_screen(bot, uid, cleanup=False)


@router.callback_query(F.data == "users:my_list")
async def cb_users_my_list(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    uid = callback.from_user.id
    if not is_admin_id(uid):
        await safe_answer_callback(callback, t(await get_user_language(uid), "admin_only"), show_alert=True)
        return
    await safe_answer_callback(callback)
    await state.clear()
    await show_admin_my_users_screen(bot, uid)


@router.callback_query(F.data == "users:all_list")
async def cb_users_all_list(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    uid = callback.from_user.id
    if not is_admin_id(uid):
        await safe_answer_callback(callback, t(await get_user_language(uid), "admin_only"), show_alert=True)
        return
    await safe_answer_callback(callback)
    await state.clear()
    await show_admin_all_users_screen(bot, uid)


def _build_my_users_list_text(invited_users: list, notice: str = "", error_msg: str = "", lang: str = DEFAULT_LANG) -> str:
    lines = [t(lang, "users_title")]
    if notice:
        lines.append(notice)
    if not invited_users:
        lines.append(t(lang, "users_my_empty"))
    else:
        user_lines = [t(lang, "users_my_total", count=len(invited_users)) + "\n"]
        for idx, u in enumerate(invited_users, start=1):
            display_name = html.escape(u.name) if u.name else t(lang, "no_name_html")
            user_lines.append(f"<b>{idx}.</b> <b>{display_name}</b> (<code>{u.user_id}</code>)")
        lines.append("\n".join(user_lines))
    if error_msg:
        lines.append(error_msg)
    return "\n\n".join(lines)


async def show_my_users_screen(bot: Bot, user_id: int, notice: str = "", cleanup: bool = False, extra_delete_ids: list[int] | None = None) -> None:
    lang = await get_user_language(user_id)
    invited_users = await get_invited_users(user_id)
    await render_panel(
        bot=bot, user_id=user_id, text=_build_my_users_list_text(invited_users, notice=notice, lang=lang),
        reply_markup=my_users_section_kb(has_users=bool(invited_users), lang=lang), cleanup=cleanup, extra_delete_ids=extra_delete_ids,
    )


async def show_my_users_select_grid(bot: Bot, user_id: int, state: FSMContext, mode: str = "edit", page: int = 0, error_msg: str = "") -> None:
    lang = await get_user_language(user_id)
    invited_users = await get_invited_users(user_id)
    if not invited_users:
        await state.clear()
        await show_my_users_screen(bot, user_id, notice=t(lang, "my_users_no_del" if mode == "delete" else "my_users_no_edit"), cleanup=False)
        return
    my_user_num_map = {str(idx): u.user_id for idx, u in enumerate(invited_users, start=1)}
    items = [(idx, u.user_id) for idx, u in enumerate(invited_users, start=1)]
    page = max(0, min(page, max(0, get_grid_page_count(len(items)) - 1)))
    if mode == "delete":
        await state.set_state(ReminderFSM.waiting_for_my_del_user_id)
        kb = my_users_delete_kb(items, page=page, lang=lang)
    else:
        await state.set_state(ReminderFSM.waiting_for_my_edit_user_id)
        kb = my_users_edit_select_kb(items, page=page, lang=lang)
    await state.update_data(my_user_num_map=my_user_num_map, my_users_select_page=page, my_users_select_mode=mode)
    await render_panel(bot=bot, user_id=user_id, text=_build_my_users_list_text(invited_users, error_msg=error_msg, lang=lang), reply_markup=kb, cleanup=False)


async def show_my_user_delete_confirm(bot: Bot, inviter_id: int, target_user_id: int, back_callback: str = "my_users:list") -> None:
    lang = await get_user_language(inviter_id)
    user = await get_invited_bot_user(inviter_id, target_user_id)
    if not user:
        await show_my_users_screen(bot, inviter_id, notice=t(lang, "users_not_found_my", uid=target_user_id), cleanup=False)
        return
    display_name = html.escape(user.name) if user.name else t(lang, "no_name_html")
    await render_panel(
        bot=bot, user_id=inviter_id, text=t(lang, "users_del_confirm", name=display_name, uid=user.user_id),
        reply_markup=my_user_delete_confirm_kb(user.user_id, back_callback=back_callback, lang=lang), cleanup=False,
    )


@router.message(Command("user", ignore_case=True))
async def cmd_my_user_section(message: Message, state: FSMContext, bot: Bot) -> None:
    await state.clear()
    uid = message.from_user.id
    if is_admin_id(uid):
        await show_users_screen(bot, uid, cleanup=True, extra_delete_ids=[message.message_id])
        return
    if not await user_has_invited_anyone(uid):
        lang = await get_user_language(uid)
        await render_panel(bot, uid, await build_home_text(uid, notice=t(lang, "user_sec_hint"), lang=lang), await get_user_main_menu_kb(uid, lang=lang), extra_delete_ids=[message.message_id])
        return
    await show_my_users_screen(bot, uid, cleanup=True, extra_delete_ids=[message.message_id])


@router.callback_query(F.data == "my_users:list")
async def cb_my_users_list(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await state.clear()
    uid = callback.from_user.id
    if is_admin_id(uid):
        await safe_answer_callback(callback)
        await show_users_screen(bot, uid, cleanup=False)
        return
    if not await user_has_invited_anyone(uid):
        await safe_answer_callback(callback, t(await get_user_language(uid), "user_sec_alert"), show_alert=True)
        return
    await safe_answer_callback(callback)
    await show_my_users_screen(bot, uid, cleanup=False)


@router.callback_query(F.data.in_({"users:add", "settings:add_user", "my_users:add"}))
async def cb_users_add(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    uid = callback.from_user.id
    lang = await get_user_language(uid)
    if callback.data == "users:add":
        if not is_admin_id(uid):
            await safe_answer_callback(callback, t(lang, "admin_only"), show_alert=True)
            return
        origin = "users"
    elif callback.data == "my_users:add":
        origin = "my_users"
    else:
        origin = "settings"
    await safe_answer_callback(callback)
    await state.clear()
    await state.set_state(ReminderFSM.waiting_for_new_user_id)
    await state.update_data(add_user_origin=origin)
    await render_panel(bot=bot, user_id=uid, text=t(lang, "add_user_prompt"), reply_markup=add_user_cancel_kb(origin=origin, lang=lang), cleanup=(origin not in ("users", "my_users")))


@router.message(ReminderFSM.waiting_for_new_user_id, F.text)
async def process_add_user_id(message: Message, state: FSMContext, bot: Bot) -> None:
    await safe_delete_message(bot, message.chat.id, message.message_id)
    uid = message.from_user.id
    lang = await get_user_language(uid)
    origin = (await state.get_data()).get("add_user_origin", "settings")
    if origin == "users" and not is_admin_id(uid):
        origin = "settings"
    raw_id = message.text.strip()
    if not raw_id.isdigit() or int(raw_id) <= 0:
        await render_panel(bot, uid, f"{t(lang, 'add_user_prompt')}\n\n{t(lang, 'add_user_bad_id')}", add_user_cancel_kb(origin=origin, lang=lang), cleanup=False)
        return
    new_user_id = int(raw_id)
    existing = await get_bot_user(new_user_id)
    if existing:
        if is_admin_id(uid):
            dup_details = t(lang, "add_user_dup_admin", name=html.escape(existing.name) if existing.name else t(lang, "no_name"), uid=new_user_id, role=t(lang, "role_admin") if existing.is_admin else t(lang, "role_user"))
        else:
            dup_details = t(lang, "add_user_dup_user", uid=new_user_id)
        await render_panel(bot, uid, f"{t(lang, 'add_user_title')}\n\n{dup_details}\n\n{t(lang, 'add_user_dup_retry')}", add_user_cancel_kb(origin=origin, lang=lang), cleanup=False)
        return
    await state.update_data(new_user_id=new_user_id, add_user_origin=origin)
    await state.set_state(ReminderFSM.waiting_for_new_user_name)
    await render_panel(bot=bot, user_id=uid, text=t(lang, "add_user_ask_name", uid=new_user_id), reply_markup=add_user_cancel_kb(origin=origin, lang=lang), cleanup=False)


@router.message(ReminderFSM.waiting_for_new_user_name, F.text)
async def process_add_user_name(message: Message, state: FSMContext, bot: Bot) -> None:
    await safe_delete_message(bot, message.chat.id, message.message_id)
    uid = message.from_user.id
    lang = await get_user_language(uid)
    user_name = message.text.strip()
    data = await state.get_data()
    new_user_id = data.get("new_user_id")
    origin = data.get("add_user_origin", "settings")
    if origin == "users" and not is_admin_id(uid):
        origin = "settings"
    if not new_user_id:
        await state.clear()
        if is_admin_id(uid):
            await show_users_screen(bot, uid, cleanup=False)
        elif origin == "my_users":
            await show_my_users_screen(bot, uid, cleanup=False)
        else:
            await show_settings_screen(bot, uid)
        return
    if not user_name or len(user_name) > 100:
        await render_panel(bot, uid, t(lang, "add_user_bad_name", uid=new_user_id), add_user_cancel_kb(origin=origin, lang=lang), cleanup=False)
        return
    added = await add_bot_user(new_user_id, user_name, invited_by=uid)
    await state.clear()
    safe_name = html.escape(user_name)
    if not added:
        dup_msg = t(lang, "add_user_dup_short", uid=new_user_id)
        if is_admin_id(uid):
            await show_users_screen(bot, uid, notice=dup_msg, cleanup=False)
        elif origin == "my_users":
            await show_my_users_screen(bot, uid, notice=dup_msg, cleanup=False)
        else:
            await show_settings_screen(bot, uid, notice=dup_msg)
        return
    await sync_user_commands(bot, uid)
    if not is_admin_id(uid):
        inviter_user = await get_bot_user(uid)
        inviter_label = f"{html.escape(inviter_user.name)} (<code>{uid}</code>)" if inviter_user and inviter_user.name else f"<code>{uid}</code>"
        for admin_id in ADMIN_IDS:
            try:
                admin_lang = await get_user_language(admin_id)
                await bot.send_message(
                    chat_id=admin_id,
                    text=t(admin_lang, "admin_new_user_alert", new_name=safe_name, new_user_id=new_user_id, inviter_label=inviter_label),
                    reply_markup=admin_ok_kb(lang=admin_lang),
                )
            except Exception as exc:
                logger.debug("Failed to send admin alert to %s: %s", admin_id, exc)
    notify_status = t(lang, "add_user_invite_sent")
    try:
        welcome_msg = await bot.send_message(chat_id=new_user_id, text=t(lang, "welcome_invite"))
        await add_tracked_message(new_user_id, welcome_msg.message_id)
    except Exception:
        notify_status = t(lang, "add_user_invite_pending")
    success_notice = t(lang, "add_user_success", name=safe_name, uid=new_user_id, status=notify_status)
    if is_admin_id(uid):
        await show_users_screen(bot, uid, notice=success_notice, cleanup=False)
    else:
        await show_my_users_screen(bot, uid, notice=success_notice, cleanup=False)


@router.callback_query(F.data == "my_users:edit_menu")
async def cb_my_users_edit_menu(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await safe_answer_callback(callback, t(await get_user_language(callback.from_user.id), "cb_pick_num_edit"))
    await state.clear()
    await show_my_users_select_grid(bot, callback.from_user.id, state, mode="edit", page=0)


@router.callback_query(F.data.startswith("my_users:edit_page:"))
async def cb_my_users_edit_page(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await safe_answer_callback(callback)
    page = parse_cb_int(callback.data.split(":"), 2)
    if page is None:
        return
    await show_my_users_select_grid(bot, callback.from_user.id, state, mode="edit", page=page)


async def show_my_user_edit_card(bot: Bot, inviter_id: int, target_user_id: int, notice: str = "") -> None:
    lang = await get_user_language(inviter_id)
    user = await get_invited_bot_user(inviter_id, target_user_id)
    if not user:
        await show_my_users_screen(bot, inviter_id, notice=t(lang, "users_not_found_my", uid=target_user_id), cleanup=False)
        return
    display_name = html.escape(user.name) if user.name else t(lang, "no_name_html")
    await render_panel(
        bot=bot, user_id=inviter_id,
        text=t(lang, "user_card_my", notice_block=f"{notice}\n\n" if notice else "", name=display_name, uid=user.user_id),
        reply_markup=my_user_edit_card_kb(user.user_id, lang=lang), cleanup=False,
    )


@router.callback_query(F.data.startswith("my_users:edit_open:"))
async def cb_my_users_edit_open(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await safe_answer_callback(callback)
    await state.clear()
    target_user_id = parse_cb_int(callback.data.split(":"), 2)
    if target_user_id is None:
        return
    await show_my_user_edit_card(bot, callback.from_user.id, target_user_id)


@router.message(ReminderFSM.waiting_for_my_edit_user_id, F.text)
async def process_my_edit_user_id_input(message: Message, state: FSMContext, bot: Bot) -> None:
    await safe_delete_message(bot, message.chat.id, message.message_id)
    uid = message.from_user.id
    lang = await get_user_language(uid)
    raw_val = message.text.strip()
    data = await state.get_data()
    if not raw_val.isdigit():
        await show_my_users_select_grid(bot, uid, state, mode="edit", page=data.get("my_users_select_page", 0), error_msg=t(lang, "user_bad_num_or_id"))
        return
    target_user_id = (data.get("my_user_num_map") or {}).get(raw_val, int(raw_val))
    await state.clear()
    await show_my_user_edit_card(bot, uid, target_user_id)


@router.callback_query(F.data.startswith("my_users:edit_name:"))
async def cb_my_users_edit_name(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await safe_answer_callback(callback)
    uid = callback.from_user.id
    lang = await get_user_language(uid)
    target_user_id = parse_cb_int(callback.data.split(":"), 2)
    if target_user_id is None:
        return
    user = await get_invited_bot_user(uid, target_user_id)
    if not user:
        await show_my_users_screen(bot, uid, notice=t(lang, "users_not_found_my_short"), cleanup=False)
        return
    await state.set_state(ReminderFSM.waiting_for_my_edit_user_name)
    await state.update_data(my_edit_target_user_id=target_user_id)
    current_name = html.escape(user.name) if user.name else t(lang, "no_name_html")
    await render_panel(bot=bot, user_id=uid, text=t(lang, "user_edit_name_prompt", uid=user.user_id, name=current_name), reply_markup=my_user_edit_name_cancel_kb(target_user_id, lang=lang), cleanup=False)


@router.message(ReminderFSM.waiting_for_my_edit_user_name, F.text)
async def process_my_edit_user_name_input(message: Message, state: FSMContext, bot: Bot) -> None:
    await safe_delete_message(bot, message.chat.id, message.message_id)
    uid = message.from_user.id
    lang = await get_user_language(uid)
    new_name = message.text.strip()
    target_user_id = (await state.get_data()).get("my_edit_target_user_id")
    if not target_user_id:
        await state.clear()
        await show_my_users_screen(bot, uid, cleanup=False)
        return
    if not new_name or len(new_name) > 100:
        await render_panel(bot, uid, t(lang, "user_edit_name_bad", uid=target_user_id), my_user_edit_name_cancel_kb(target_user_id, lang=lang), cleanup=False)
        return
    updated = await update_invited_bot_user_name(uid, target_user_id, new_name)
    await state.clear()
    if not updated:
        await show_my_users_screen(bot, uid, notice=t(lang, "users_not_found_my_short"), cleanup=False)
        return
    await show_my_user_edit_card(bot, uid, target_user_id, notice=t(lang, "user_name_updated", name=html.escape(new_name)))


@router.callback_query(F.data == "my_users:del_menu")
async def cb_my_users_del_menu(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await safe_answer_callback(callback, t(await get_user_language(callback.from_user.id), "cb_pick_num_del"))
    await state.clear()
    await show_my_users_select_grid(bot, callback.from_user.id, state, mode="delete", page=0)


@router.callback_query(F.data.startswith("my_users:del_page:"))
async def cb_my_users_del_page(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await safe_answer_callback(callback)
    page = parse_cb_int(callback.data.split(":"), 2)
    if page is None:
        return
    await show_my_users_select_grid(bot, callback.from_user.id, state, mode="delete", page=page)


@router.callback_query(F.data.startswith("my_users:del_ask:"))
async def cb_my_users_del_ask(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await safe_answer_callback(callback)
    await state.clear()
    parts = callback.data.split(":")
    target_user_id = parse_cb_int(parts, 2)
    if target_user_id is None:
        return
    back_cb = f"my_users:edit_open:{target_user_id}" if (len(parts) > 3 and parts[3] == "card") else "my_users:list"
    await show_my_user_delete_confirm(bot, callback.from_user.id, target_user_id, back_callback=back_cb)


async def execute_my_user_removal(bot: Bot, inviter_id: int, state: FSMContext, target_user_id: int) -> None:
    lang = await get_user_language(inviter_id)
    target_lang = await get_user_language(target_user_id)
    user_obj = await get_invited_bot_user(inviter_id, target_user_id)
    if not user_obj:
        await state.clear()
        await show_my_users_screen(bot, inviter_id, notice=t(lang, "users_not_found_my", uid=target_user_id), cleanup=False)
        return
    user_label = f"<b>{html.escape(user_obj.name)}</b> (<code>{target_user_id}</code>)" if user_obj.name else f"<code>{target_user_id}</code>"
    removed, old_msg_ids = await remove_bot_user_with_cleanup(target_user_id, inviter_id=inviter_id)
    await state.clear()
    if not removed:
        await show_my_users_screen(bot, inviter_id, notice=t(lang, "users_del_failed", uid=target_user_id), cleanup=False)
        return
    cleanup_user_memory(target_user_id)
    if old_msg_ids:
        await safe_delete_messages_batch(bot, target_user_id, old_msg_ids, requeue_on_failure=False)
    try:
        await bot.set_chat_menu_button(chat_id=target_user_id, menu_button=MenuButtonCommands())
    except Exception as exc:
        logger.debug("set_chat_menu_button reset failed for %s: %s", target_user_id, exc)
    notify_status = t(lang, "user_del_notified")
    try:
        await bot.send_message(chat_id=target_user_id, text=t(target_lang, "user_removed_notice"))
    except Exception:
        notify_status = t(lang, "user_del_closed")
    await show_my_users_screen(bot, inviter_id, notice=t(lang, "user_del_success", label=user_label, status=notify_status), cleanup=False)


@router.callback_query(F.data.startswith("my_users:del_confirm:"))
async def cb_my_users_del_confirm_exec(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    target_user_id = parse_cb_int(callback.data.split(":"), 2)
    if target_user_id is None:
        await safe_answer_callback(callback)
        return
    await safe_answer_callback(callback, t(await get_user_language(callback.from_user.id), "user_deleted_cb"))
    await execute_my_user_removal(bot, callback.from_user.id, state, target_user_id)


@router.callback_query(F.data.startswith("my_users:del:"))
async def cb_my_users_del_legacy(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await safe_answer_callback(callback)
    await state.clear()
    target_user_id = parse_cb_int(callback.data.split(":"), 2)
    if target_user_id is None:
        return
    await show_my_user_delete_confirm(bot, callback.from_user.id, target_user_id, back_callback="my_users:list")


@router.message(ReminderFSM.waiting_for_my_del_user_id, F.text)
async def process_my_del_user_id(message: Message, state: FSMContext, bot: Bot) -> None:
    await safe_delete_message(bot, message.chat.id, message.message_id)
    uid = message.from_user.id
    lang = await get_user_language(uid)
    raw_val = message.text.strip()
    data = await state.get_data()
    if not raw_val.isdigit():
        await show_my_users_select_grid(bot, uid, state, mode="delete", page=data.get("my_users_select_page", 0), error_msg=t(lang, "user_bad_num_or_id"))
        return
    target_user_id = (data.get("my_user_num_map") or {}).get(raw_val, int(raw_val))
    await state.clear()
    await show_my_user_delete_confirm(bot, uid, target_user_id, back_callback="my_users:list")


@router.callback_query(F.data == "users:edit_menu")
async def cb_users_edit_menu(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    uid = callback.from_user.id
    lang = await get_user_language(uid)
    if not is_admin_id(uid):
        await safe_answer_callback(callback, t(lang, "admin_only"), show_alert=True)
        return
    await safe_answer_callback(callback, t(lang, "cb_pick_num_edit"))
    await state.clear()
    await show_users_select_grid(bot, uid, state, mode="edit", page=0)


@router.callback_query(F.data.startswith("users:edit_page:"))
async def cb_users_edit_page(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    uid = callback.from_user.id
    if not is_admin_id(uid):
        await safe_answer_callback(callback, t(await get_user_language(uid), "admin_only"), show_alert=True)
        return
    await safe_answer_callback(callback)
    page = parse_cb_int(callback.data.split(":"), 2)
    if page is None:
        return
    await show_users_select_grid(bot, uid, state, mode="edit", page=page)


async def show_user_edit_card(bot: Bot, admin_id: int, target_user_id: int, notice: str = "") -> None:
    lang = await get_user_language(admin_id)
    user = await get_bot_user(target_user_id)
    if not user:
        await show_users_screen(bot, admin_id, notice=t(lang, "users_not_found", uid=target_user_id), cleanup=False)
        return
    role = t(lang, "role_admin_full") if user.is_admin else t(lang, "role_user")
    display_name = html.escape(user.name) if user.name else t(lang, "no_name_html")
    await render_panel(
        bot=bot, user_id=admin_id,
        text=t(lang, "user_card_admin", notice_block=f"{notice}\n\n" if notice else "", name=display_name, uid=user.user_id, role=role),
        reply_markup=user_edit_card_kb(user.user_id, user.is_admin, lang=lang), cleanup=False,
    )


@router.callback_query(F.data.startswith("users:edit_open:"))
async def cb_users_edit_open(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    uid = callback.from_user.id
    if not is_admin_id(uid):
        await safe_answer_callback(callback, t(await get_user_language(uid), "admin_only"), show_alert=True)
        return
    await safe_answer_callback(callback)
    await state.clear()
    target_user_id = parse_cb_int(callback.data.split(":"), 2)
    if target_user_id is None:
        return
    await show_user_edit_card(bot, uid, target_user_id)


@router.message(ReminderFSM.waiting_for_edit_user_id, F.text)
async def process_edit_user_id_input(message: Message, state: FSMContext, bot: Bot) -> None:
    await safe_delete_message(bot, message.chat.id, message.message_id)
    uid = message.from_user.id
    if not is_admin_id(uid):
        await state.clear()
        return
    lang = await get_user_language(uid)
    raw_val = message.text.strip()
    data = await state.get_data()
    if not raw_val.isdigit():
        await show_users_select_grid(bot, uid, state, mode="edit", page=data.get("users_select_page", 0), error_msg=t(lang, "user_bad_num_or_id"))
        return
    target_user_id = (data.get("user_num_map") or {}).get(raw_val, int(raw_val))
    await state.clear()
    await show_user_edit_card(bot, uid, target_user_id)


@router.callback_query(F.data.startswith("users:edit_name:"))
async def cb_users_edit_name(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    uid = callback.from_user.id
    lang = await get_user_language(uid)
    if not is_admin_id(uid):
        await safe_answer_callback(callback, t(lang, "admin_only"), show_alert=True)
        return
    await safe_answer_callback(callback)
    target_user_id = parse_cb_int(callback.data.split(":"), 2)
    if target_user_id is None:
        return
    user = await get_bot_user(target_user_id)
    if not user:
        await show_users_screen(bot, uid, notice=t(lang, "users_not_found_short"), cleanup=False)
        return
    await state.set_state(ReminderFSM.waiting_for_edit_user_name)
    await state.update_data(edit_target_user_id=target_user_id)
    current_name = html.escape(user.name) if user.name else t(lang, "no_name_html")
    await render_panel(bot=bot, user_id=uid, text=t(lang, "user_edit_name_prompt", uid=user.user_id, name=current_name), reply_markup=user_edit_name_cancel_kb(target_user_id, lang=lang), cleanup=False)


@router.message(ReminderFSM.waiting_for_edit_user_name, F.text)
async def process_edit_user_name_input(message: Message, state: FSMContext, bot: Bot) -> None:
    await safe_delete_message(bot, message.chat.id, message.message_id)
    uid = message.from_user.id
    if not is_admin_id(uid):
        await state.clear()
        return
    lang = await get_user_language(uid)
    new_name = message.text.strip()
    target_user_id = (await state.get_data()).get("edit_target_user_id")
    if not target_user_id:
        await state.clear()
        await show_users_screen(bot, uid, cleanup=False)
        return
    if not new_name or len(new_name) > 100:
        await render_panel(bot, uid, t(lang, "user_edit_name_bad", uid=target_user_id), user_edit_name_cancel_kb(target_user_id, lang=lang), cleanup=False)
        return
    updated = await update_bot_user_name(target_user_id, new_name)
    await state.clear()
    if not updated:
        await show_users_screen(bot, uid, notice=t(lang, "users_not_found_short"), cleanup=False)
        return
    await show_user_edit_card(bot, uid, target_user_id, notice=t(lang, "user_name_updated", name=html.escape(new_name)))


@router.callback_query(F.data == "users:del_menu")
async def cb_users_del_menu(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    uid = callback.from_user.id
    lang = await get_user_language(uid)
    if not is_admin_id(uid):
        await safe_answer_callback(callback, t(lang, "admin_only"), show_alert=True)
        return
    await safe_answer_callback(callback, t(lang, "cb_pick_num_del"))
    await state.clear()
    await show_users_select_grid(bot, uid, state, mode="delete", page=0)


@router.callback_query(F.data.startswith("users:del_page:"))
async def cb_users_del_page(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    uid = callback.from_user.id
    if not is_admin_id(uid):
        await safe_answer_callback(callback, t(await get_user_language(uid), "admin_only"), show_alert=True)
        return
    await safe_answer_callback(callback)
    page = parse_cb_int(callback.data.split(":"), 2)
    if page is None:
        return
    await show_users_select_grid(bot, uid, state, mode="delete", page=page)


@router.callback_query(F.data.startswith("users:del_ask:"))
async def cb_users_del_ask(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    uid = callback.from_user.id
    if not is_admin_id(uid):
        await safe_answer_callback(callback, t(await get_user_language(uid), "admin_only"), show_alert=True)
        return
    await safe_answer_callback(callback)
    await state.clear()
    parts = callback.data.split(":")
    target_user_id = parse_cb_int(parts, 2)
    if target_user_id is None:
        return
    back_cb = f"users:edit_open:{target_user_id}" if (len(parts) > 3 and parts[3] == "card") else "users:list"
    await show_user_delete_confirm(bot, uid, target_user_id, back_callback=back_cb)


async def execute_user_removal(bot: Bot, admin_id: int, state: FSMContext, target_user_id: int) -> None:
    lang = await get_user_language(admin_id)
    target_lang = await get_user_language(target_user_id)
    if is_admin_id(target_user_id):
        await state.clear()
        await show_users_screen(bot, admin_id, notice=t(lang, "users_cannot_del_admin"), cleanup=False)
        return
    user_obj = await get_bot_user(target_user_id)
    user_label = f"<b>{html.escape(user_obj.name)}</b> (<code>{target_user_id}</code>)" if user_obj and user_obj.name else f"<code>{target_user_id}</code>"
    removed, old_msg_ids = await remove_bot_user_with_cleanup(target_user_id)
    await state.clear()
    if not removed:
        await show_users_screen(bot, admin_id, notice=t(lang, "users_not_found_db", uid=target_user_id), cleanup=False)
        return
    cleanup_user_memory(target_user_id)
    if old_msg_ids:
        await safe_delete_messages_batch(bot, target_user_id, old_msg_ids, requeue_on_failure=False)
    try:
        await bot.set_chat_menu_button(chat_id=target_user_id, menu_button=MenuButtonCommands())
    except Exception as exc:
        logger.debug("set_chat_menu_button reset failed for %s: %s", target_user_id, exc)
    notify_status = t(lang, "user_del_notified")
    try:
        await bot.send_message(chat_id=target_user_id, text=t(target_lang, "user_removed_notice"))
    except Exception:
        notify_status = t(lang, "user_del_closed")
    await show_users_screen(bot, admin_id, notice=t(lang, "user_del_success", label=user_label, status=notify_status), cleanup=False)


@router.callback_query(F.data.startswith("users:del_confirm:"))
async def cb_users_del_confirm_exec(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    uid = callback.from_user.id
    lang = await get_user_language(uid)
    if not is_admin_id(uid):
        await safe_answer_callback(callback, t(lang, "admin_only"), show_alert=True)
        return
    target_user_id = parse_cb_int(callback.data.split(":"), 2)
    if target_user_id is None:
        await safe_answer_callback(callback)
        return
    await safe_answer_callback(callback, t(lang, "user_deleted_cb"))
    await execute_user_removal(bot, uid, state, target_user_id)


@router.callback_query(F.data.startswith("users:del:"))
async def cb_users_del_legacy(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    uid = callback.from_user.id
    if not is_admin_id(uid):
        await safe_answer_callback(callback, t(await get_user_language(uid), "admin_only"), show_alert=True)
        return
    await safe_answer_callback(callback)
    await state.clear()
    target_user_id = parse_cb_int(callback.data.split(":"), 2)
    if target_user_id is None:
        return
    await show_user_delete_confirm(bot, uid, target_user_id, back_callback="users:list")


@router.message(ReminderFSM.waiting_for_del_user_id, F.text)
async def process_del_user_id(message: Message, state: FSMContext, bot: Bot) -> None:
    await safe_delete_message(bot, message.chat.id, message.message_id)
    uid = message.from_user.id
    if not is_admin_id(uid):
        await state.clear()
        return
    lang = await get_user_language(uid)
    raw_val = message.text.strip()
    data = await state.get_data()
    if not raw_val.isdigit():
        await show_users_select_grid(bot, uid, state, mode="delete", page=data.get("users_select_page", 0), error_msg=t(lang, "user_bad_num_or_id"))
        return
    target_user_id = (data.get("user_num_map") or {}).get(raw_val, int(raw_val))
    await state.clear()
    await show_user_delete_confirm(bot, uid, target_user_id, back_callback="users:list")
