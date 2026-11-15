import html
from aiogram import Router, Bot, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery

from config import ADMIN_IDS
from database import (
    get_panel_message_id,
    add_tracked_message,
    is_admin_id,
    get_all_bot_users,
    get_bot_user,
    add_bot_user,
    update_bot_user_name,
    remove_bot_user,
    user_has_invited_anyone,
    get_invited_users,
    get_invited_bot_user,
    update_invited_bot_user_name,
    remove_invited_bot_user,
)
from keyboards import (
    admin_ok_kb,
    users_section_kb,
    add_user_cancel_kb,
    users_edit_select_kb,
    user_edit_card_kb,
    user_edit_name_cancel_kb,
    users_delete_kb,
    my_users_section_kb,
    my_users_edit_select_kb,
    my_user_edit_card_kb,
    my_user_edit_name_cancel_kb,
    my_users_delete_kb,
)
from .states import ReminderFSM
from .settings import show_settings_screen
from .common import (
    safe_delete_message,
    cleanup_old_messages,
    render_panel,
    build_home_text,
    get_user_main_menu_kb,
    sync_user_commands,
)

router = Router()

ADD_USER_PROMPT_TEXT = (
    "➕ <b>Добавление нового пользователя</b>\n\n"
    "Отправьте в чат <b>Telegram ID нового пользователя</b> (только цифры, например: 123456789).\n"
    "Telegram ID того, кого Вы хотите добавить можно узнать в боте @userinfobot"
)

WELCOME_INVITE_TEXT = (
    "Привет. Вы приглашены в бот Напоминалкин.\n\n"
    "Нажмите Menu или Start.\n\n"
    "Ознакомиться с тем, как работает бот можно в Меню в разделе Информация.\n\n"
    "Перед началом работы задайте в Настройках свой текущий часовой пояс, чтобы время бота и Вашего устройства совпадало"
)


# =====================================================================
# 1. РАЗДЕЛ /users (ДЛЯ АДМИНИСТРАТОРА — ВСЕ ПОЛЬЗОВАТЕЛИ БОТА)
# =====================================================================

async def show_users_screen(bot: Bot, admin_id: int, notice: str = "") -> None:
    users = await get_all_bot_users()
    removable_users = [u for u in users if not u.is_admin]

    lines = ["👥 <b>Раздел «Пользователи»</b>"]
    if notice:
        lines.append(notice)

    if not users:
        lines.append("Список пользователей пуст.")
    else:
        user_lines = [f"Всего пользователей с доступом: <b>{len(users)}</b>\n"]
        for idx, u in enumerate(users, start=1):
            role = "👑 Админ" if u.is_admin else "👤 Пользователь"
            display_name = html.escape(u.name) if u.name else "<i>Без имени</i>"
            user_lines.append(f"<b>{idx}.</b> <b>{display_name}</b> (<code>{u.user_id}</code>) — {role}")
        lines.append("\n".join(user_lines))

    await render_panel(
        bot=bot,
        user_id=admin_id,
        text="\n\n".join(lines),
        reply_markup=users_section_kb(
            has_users=bool(users),
            has_removable_users=bool(removable_users),
        ),
    )


@router.message(Command("users", ignore_case=True))
async def cmd_users(message: Message, state: FSMContext, bot: Bot) -> None:
    await safe_delete_message(bot, message.chat.id, message.message_id)
    await state.clear()
    uid = message.from_user.id
    if not is_admin_id(uid):
        home_text = await build_home_text(
            uid, notice="⛔ <b>Доступ к разделу /users есть только у администратора.</b>"
        )
        kb = await get_user_main_menu_kb(uid)
        await render_panel(bot, uid, home_text, kb)
        return
    await show_users_screen(bot, uid)


@router.callback_query(F.data == "users:list")
async def cb_users_list(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await state.clear()
    if not is_admin_id(callback.from_user.id):
        await callback.answer("⛔ Доступно только администратору", show_alert=True)
        return
    await show_users_screen(bot, callback.from_user.id)
    await callback.answer()


# =====================================================================
# 2. РАЗДЕЛ /user (ДЛЯ ПОЛЬЗОВАТЕЛЕЙ, ДОБАВИВШИХ ХОТЯ БЫ ОДНОГО УЧАСТНИКА)
# =====================================================================

async def show_my_users_screen(bot: Bot, user_id: int, notice: str = "") -> None:
    invited_users = await get_invited_users(user_id)

    lines = ["👥 <b>Раздел «Пользователи» (/user)</b>"]
    if notice:
        lines.append(notice)

    if not invited_users:
        lines.append("Список добавленных вами пользователей пуст.")
    else:
        user_lines = [f"Добавленные вами пользователи (<b>{len(invited_users)}</b>):\n"]
        for idx, u in enumerate(invited_users, start=1):
            display_name = html.escape(u.name) if u.name else "<i>Без имени</i>"
            user_lines.append(f"<b>{idx}.</b> <b>{display_name}</b> (<code>{u.user_id}</code>)")
        lines.append("\n".join(user_lines))

    await render_panel(
        bot=bot,
        user_id=user_id,
        text="\n\n".join(lines),
        reply_markup=my_users_section_kb(),
    )


@router.message(Command("user", ignore_case=True))
async def cmd_my_user_section(message: Message, state: FSMContext, bot: Bot) -> None:
    await safe_delete_message(bot, message.chat.id, message.message_id)
    await state.clear()
    uid = message.from_user.id

    if is_admin_id(uid):
        await show_users_screen(bot, uid)
        return

    if not await user_has_invited_anyone(uid):
        home_text = await build_home_text(
            uid,
            notice="ℹ️ <b>Раздел /user появится после того, как вы добавите хотя бы одного нового пользователя в Настройках (/settings).</b>",
        )
        kb = await get_user_main_menu_kb(uid)
        await render_panel(bot, uid, home_text, kb)
        return

    await show_my_users_screen(bot, uid)


@router.callback_query(F.data == "my_users:list")
async def cb_my_users_list(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await state.clear()
    uid = callback.from_user.id
    if is_admin_id(uid):
        await show_users_screen(bot, uid)
        await callback.answer()
        return

    if not await user_has_invited_anyone(uid):
        await callback.answer("Сначала добавьте пользователя через Настройки", show_alert=True)
        return

    await show_my_users_screen(bot, uid)
    await callback.answer()


# =====================================================================
# 3. ДОБАВЛЕНИЕ НОВОГО ПОЛЬЗОВАТЕЛЯ (ИЗ /settings, /user ИЛИ /users)
# =====================================================================

@router.callback_query(F.data.in_({"users:add", "settings:add_user", "my_users:add"}))
async def cb_users_add(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    uid = callback.from_user.id
    if callback.data == "users:add" and is_admin_id(uid):
        origin = "users"
    elif callback.data == "my_users:add":
        origin = "my_users"
    else:
        origin = "settings"

    await state.clear()
    await state.set_state(ReminderFSM.waiting_for_new_user_id)
    await state.update_data(add_user_origin=origin)

    await render_panel(
        bot=bot,
        user_id=uid,
        text=ADD_USER_PROMPT_TEXT,
        reply_markup=add_user_cancel_kb(origin=origin),
    )
    await callback.answer()


@router.message(ReminderFSM.waiting_for_new_user_id, F.text)
async def process_add_user_id(message: Message, state: FSMContext, bot: Bot) -> None:
    await safe_delete_message(bot, message.chat.id, message.message_id)
    uid = message.from_user.id
    data = await state.get_data()
    origin = data.get("add_user_origin", "settings")
    if origin == "users" and not is_admin_id(uid):
        origin = "settings"

    raw_id = message.text.strip()
    if not raw_id.isdigit() or int(raw_id) <= 0:
        text = (
            f"{ADD_USER_PROMPT_TEXT}\n\n"
            "⚠️ <b>Некорректный Telegram ID!</b> Пожалуйста, отправьте только цифры:"
        )
        await render_panel(bot, uid, text, add_user_cancel_kb(origin=origin))
        return

    new_user_id = int(raw_id)
    existing = await get_bot_user(new_user_id)
    if existing:
        if is_admin_id(uid):
            existing_name = html.escape(existing.name) if existing.name else "Без имени"
            role = "👑 Админ" if existing.is_admin else "👤 Пользователь"
            dup_details = (
                f"⚠️ <b>Такой пользователь уже существует!</b>\n"
                f"👤 Имя: <b>{existing_name}</b>\n"
                f"🆔 Telegram ID: <code>{new_user_id}</code> ({role})"
            )
        else:
            dup_details = f"⚠️ <b>Такой пользователь (<code>{new_user_id}</code>) уже существует!</b>"

        text = (
            "➕ <b>Добавление нового пользователя</b>\n\n"
            f"{dup_details}\n\n"
            "Введите другой <b>Telegram ID нового пользователя</b> или вернитесь назад:"
        )
        await render_panel(bot, uid, text, add_user_cancel_kb(origin=origin))
        return

    await state.update_data(new_user_id=new_user_id, add_user_origin=origin)
    await state.set_state(ReminderFSM.waiting_for_new_user_name)

    text = (
        "➕ <b>Добавление нового пользователя</b>\n\n"
        f"🆔 <b>Telegram ID:</b> <code>{new_user_id}</code>\n\n"
        "Теперь отправьте в чат <b>имя пользователя</b> (например: <code>Иван</code> или <code>Мария</code>):"
    )
    await render_panel(
        bot=bot,
        user_id=uid,
        text=text,
        reply_markup=add_user_cancel_kb(origin=origin),
    )


@router.message(ReminderFSM.waiting_for_new_user_name, F.text)
async def process_add_user_name(message: Message, state: FSMContext, bot: Bot) -> None:
    await safe_delete_message(bot, message.chat.id, message.message_id)
    uid = message.from_user.id

    user_name = message.text.strip()
    data = await state.get_data()
    new_user_id = data.get("new_user_id")
    origin = data.get("add_user_origin", "settings")
    if origin == "users" and not is_admin_id(uid):
        origin = "settings"

    if not new_user_id:
        await state.clear()
        if origin == "users":
            await show_users_screen(bot, uid)
        elif origin == "my_users":
            await show_my_users_screen(bot, uid)
        else:
            await show_settings_screen(bot, uid)
        return

    if not user_name or len(user_name) > 100:
        text = (
            "➕ <b>Добавление нового пользователя</b>\n\n"
            f"🆔 <b>Telegram ID:</b> <code>{new_user_id}</code>\n\n"
            "⚠️ <b>Некорректное имя!</b>\n"
            "Введите имя пользователя (до 100 символов):"
        )
        await render_panel(bot, uid, text, add_user_cancel_kb(origin=origin))
        return

    added = await add_bot_user(new_user_id, user_name, invited_by=uid)
    await state.clear()

    safe_name = html.escape(user_name)
    if not added:
        dup_msg = f"⚠️ <b>Такой пользователь уже существует!</b> (<code>{new_user_id}</code>)"
        if origin == "users":
            await show_users_screen(bot, uid, notice=dup_msg)
        elif origin == "my_users":
            await show_my_users_screen(bot, uid, notice=dup_msg)
        else:
            await show_settings_screen(bot, uid, notice=dup_msg)
        return

    # Активируем раздел /user в меню команд для пригласившего пользователя
    await sync_user_commands(bot, uid)

    # Если нового пользователя добавил не админ — отправляем уведомление админу с кнопкой «Ok»
    if not is_admin_id(uid):
        inviter_user = await get_bot_user(uid)
        inviter_label = (
            f"{html.escape(inviter_user.name)} (<code>{uid}</code>)"
            if inviter_user and inviter_user.name
            else f"<code>{uid}</code>"
        )
        admin_alert_text = (
            "👤 <b>Добавлен новый пользователь</b>\n\n"
            f"👤 <b>Имя:</b> {safe_name}\n"
            f"🆔 <b>Telegram ID:</b> <code>{new_user_id}</code>\n"
            f"➕ <b>Пригласил:</b> {inviter_label}"
        )
        for admin_id in ADMIN_IDS:
            try:
                await bot.send_message(
                    chat_id=admin_id,
                    text=admin_alert_text,
                    reply_markup=admin_ok_kb(),
                )
            except Exception:
                pass

    notify_status = "приглашение отправлено"
    try:
        welcome_msg = await bot.send_message(
            chat_id=new_user_id,
            text=WELCOME_INVITE_TEXT,
        )
        await add_tracked_message(new_user_id, welcome_msg.message_id)
    except Exception:
        notify_status = "получит доступ сразу после запуска бота (/start)"

    success_notice = (
        f"✅ <b>Пользователь {safe_name} (<code>{new_user_id}</code>) добавлен</b> ({notify_status})."
    )
    if origin == "users":
        await show_users_screen(bot, uid, notice=success_notice)
    else:
        await show_my_users_screen(bot, uid, notice=success_notice)


# =====================================================================
# 4. РЕДАКТИРОВАНИЕ И УДАЛЕНИЕ В РАЗДЕЛЕ /user (ТОЛЬКО СВОИ ПРИГЛАШЁННЫЕ)
# =====================================================================

@router.callback_query(F.data == "my_users:edit_menu")
async def cb_my_users_edit_menu(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    uid = callback.from_user.id
    invited_users = await get_invited_users(uid)
    if not invited_users:
        await show_my_users_screen(
            bot, uid, notice="ℹ️ У вас пока нет добавленных пользователей для редактирования."
        )
        await callback.answer()
        return

    await state.clear()
    await state.set_state(ReminderFSM.waiting_for_my_edit_user_id)

    text = (
        "✏️ <b>Редактирование пользователя</b>\n\n"
        "Выберите пользователя, которого вы добавили, кнопкой ниже или отправьте его <b>Telegram ID</b> в чат:"
    )
    await render_panel(
        bot=bot,
        user_id=uid,
        text=text,
        reply_markup=my_users_edit_select_kb(invited_users),
    )
    await callback.answer()


async def show_my_user_edit_card(
    bot: Bot, inviter_id: int, target_user_id: int, notice: str = ""
) -> None:
    user = await get_invited_bot_user(inviter_id, target_user_id)
    if not user:
        await show_my_users_screen(
            bot,
            inviter_id,
            notice=f"⚠️ Пользователь <code>{target_user_id}</code> не найден среди добавленных вами.",
        )
        return

    display_name = html.escape(user.name) if user.name else "<i>Без имени</i>"
    notice_block = f"{notice}\n\n" if notice else ""

    text = (
        "✏️ <b>Карточка пользователя</b>\n\n"
        f"{notice_block}"
        f"👤 <b>Имя:</b> {display_name}\n"
        f"🆔 <b>Telegram ID:</b> <code>{user.user_id}</code>\n\n"
        "Выберите действие:"
    )
    await render_panel(
        bot=bot,
        user_id=inviter_id,
        text=text,
        reply_markup=my_user_edit_card_kb(user.user_id),
    )


@router.callback_query(F.data.startswith("my_users:edit_open:"))
async def cb_my_users_edit_open(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await state.clear()
    target_user_id = int(callback.data.split(":")[2])
    await show_my_user_edit_card(bot, callback.from_user.id, target_user_id)
    await callback.answer()


@router.message(ReminderFSM.waiting_for_my_edit_user_id, F.text)
async def process_my_edit_user_id_input(message: Message, state: FSMContext, bot: Bot) -> None:
    await safe_delete_message(bot, message.chat.id, message.message_id)
    uid = message.from_user.id
    raw_id = message.text.strip()

    if not raw_id.isdigit():
        invited_users = await get_invited_users(uid)
        text = (
            "✏️ <b>Редактирование пользователя</b>\n\n"
            "⚠️ <b>Некорректный Telegram ID!</b>\n"
            "Выберите пользователя кнопкой ниже или введите его числовой Telegram ID:"
        )
        await render_panel(bot, uid, text, my_users_edit_select_kb(invited_users))
        return

    await state.clear()
    await show_my_user_edit_card(bot, uid, int(raw_id))


@router.callback_query(F.data.startswith("my_users:edit_name:"))
async def cb_my_users_edit_name(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    uid = callback.from_user.id
    target_user_id = int(callback.data.split(":")[2])
    user = await get_invited_bot_user(uid, target_user_id)
    if not user:
        await show_my_users_screen(
            bot, uid, notice="⚠️ Пользователь не найден среди добавленных вами."
        )
        await callback.answer()
        return

    await state.set_state(ReminderFSM.waiting_for_my_edit_user_name)
    await state.update_data(my_edit_target_user_id=target_user_id)

    current_name = html.escape(user.name) if user.name else "<i>Без имени</i>"
    text = (
        "✏️ <b>Изменение имени пользователя</b>\n\n"
        f"🆔 <b>Telegram ID:</b> <code>{user.user_id}</code>\n"
        f"👤 <b>Текущее имя:</b> {current_name}\n\n"
        "Отправьте в чат <b>новое имя</b> для этого пользователя:"
    )
    await render_panel(
        bot=bot,
        user_id=uid,
        text=text,
        reply_markup=my_user_edit_name_cancel_kb(target_user_id),
    )
    await callback.answer()


@router.message(ReminderFSM.waiting_for_my_edit_user_name, F.text)
async def process_my_edit_user_name_input(message: Message, state: FSMContext, bot: Bot) -> None:
    await safe_delete_message(bot, message.chat.id, message.message_id)
    uid = message.from_user.id
    new_name = message.text.strip()
    data = await state.get_data()
    target_user_id = data.get("my_edit_target_user_id")

    if not target_user_id:
        await state.clear()
        await show_my_users_screen(bot, uid)
        return

    if not new_name or len(new_name) > 100:
        text = (
            "✏️ <b>Изменение имени пользователя</b>\n\n"
            f"🆔 <b>Telegram ID:</b> <code>{target_user_id}</code>\n\n"
            "⚠️ <b>Некорректное имя!</b>\n"
            "Введите новое имя пользователя (от 1 до 100 символов):"
        )
        await render_panel(
            bot,
            uid,
            text,
            my_user_edit_name_cancel_kb(target_user_id),
        )
        return

    updated = await update_invited_bot_user_name(uid, target_user_id, new_name)
    await state.clear()

    if not updated:
        await show_my_users_screen(
            bot, uid, notice="⚠️ Пользователь не найден среди добавленных вами."
        )
        return

    await show_my_user_edit_card(
        bot,
        uid,
        target_user_id,
        notice=f"✅ <b>Имя успешно изменено на «{html.escape(new_name)}»!</b>",
    )


@router.callback_query(F.data == "my_users:del_menu")
async def cb_my_users_del_menu(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    uid = callback.from_user.id
    invited_users = await get_invited_users(uid)
    if not invited_users:
        await show_my_users_screen(
            bot, uid, notice="ℹ️ У вас нет добавленных пользователей для удаления."
        )
        await callback.answer()
        return

    await state.clear()
    await state.set_state(ReminderFSM.waiting_for_my_del_user_id)

    text = (
        "🗑 <b>Удаление пользователя</b>\n\n"
        "Выберите пользователя, которого вы добавили, кнопкой ниже или отправьте его <b>Telegram ID</b> в чат:"
    )
    await render_panel(
        bot=bot,
        user_id=uid,
        text=text,
        reply_markup=my_users_delete_kb(invited_users),
    )
    await callback.answer()


async def execute_my_user_removal(
    bot: Bot, inviter_id: int, state: FSMContext, target_user_id: int
) -> None:
    user_obj = await get_invited_bot_user(inviter_id, target_user_id)
    if not user_obj:
        await state.clear()
        await show_my_users_screen(
            bot,
            inviter_id,
            notice=f"⚠️ Пользователь <code>{target_user_id}</code> не найден среди добавленных вами.",
        )
        return

    user_label = (
        f"<b>{html.escape(user_obj.name)}</b> (<code>{target_user_id}</code>)"
        if user_obj.name
        else f"<code>{target_user_id}</code>"
    )

    removed = await remove_invited_bot_user(inviter_id, target_user_id)
    await state.clear()

    if not removed:
        await show_my_users_screen(
            bot,
            inviter_id,
            notice=f"⚠️ Не удалось удалить пользователя <code>{target_user_id}</code>.",
        )
        return

    await cleanup_old_messages(bot, target_user_id)
    old_panel_id = await get_panel_message_id(target_user_id)
    if old_panel_id:
        await safe_delete_message(bot, target_user_id, old_panel_id)

    notify_status = "уведомление отправлено"
    try:
        await bot.send_message(
            chat_id=target_user_id,
            text="⛔ <b>Вы удалены из списка пользователей, доступ к боту прекращён.</b>",
        )
    except Exception:
        notify_status = "доступ закрыт"

    await show_my_users_screen(
        bot,
        inviter_id,
        notice=f"✅ <b>Пользователь {user_label} удалён</b> ({notify_status}).",
    )


@router.callback_query(F.data.startswith("my_users:del:"))
async def cb_my_users_del_confirm(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    target_user_id = int(callback.data.split(":")[2])
    await execute_my_user_removal(bot, callback.from_user.id, state, target_user_id)
    await callback.answer("Пользователь удалён")


@router.message(ReminderFSM.waiting_for_my_del_user_id, F.text)
async def process_my_del_user_id(message: Message, state: FSMContext, bot: Bot) -> None:
    await safe_delete_message(bot, message.chat.id, message.message_id)
    uid = message.from_user.id
    raw_id = message.text.strip()

    if not raw_id.isdigit():
        invited_users = await get_invited_users(uid)
        text = (
            "🗑 <b>Удаление пользователя</b>\n\n"
            "⚠️ <b>Некорректный Telegram ID!</b>\n"
            "Выберите пользователя кнопкой ниже или введите его числовой Telegram ID:"
        )
        await render_panel(bot, uid, text, my_users_delete_kb(invited_users))
        return

    await execute_my_user_removal(bot, uid, state, int(raw_id))


# =====================================================================
# 5. РЕДАКТИРОВАНИЕ И УДАЛЕНИЕ В РАЗДЕЛЕ /users (ТОЛЬКО ДЛЯ АДМИНА)
# =====================================================================

@router.callback_query(F.data == "users:edit_menu")
async def cb_users_edit_menu(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    if not is_admin_id(callback.from_user.id):
        await callback.answer("⛔ Доступно только администратору", show_alert=True)
        return

    users = await get_all_bot_users()
    if not users:
        await show_users_screen(bot, callback.from_user.id, notice="ℹ️ Список пользователей пуст.")
        await callback.answer()
        return

    await state.clear()
    await state.set_state(ReminderFSM.waiting_for_edit_user_id)

    text = (
        "✏️ <b>Редактирование пользователя</b>\n\n"
        "Выберите пользователя кнопкой ниже или отправьте его <b>Telegram ID</b> в чат:"
    )
    await render_panel(
        bot=bot,
        user_id=callback.from_user.id,
        text=text,
        reply_markup=users_edit_select_kb(users),
    )
    await callback.answer()


async def show_user_edit_card(
    bot: Bot, admin_id: int, target_user_id: int, notice: str = ""
) -> None:
    user = await get_bot_user(target_user_id)
    if not user:
        await show_users_screen(
            bot,
            admin_id,
            notice=f"⚠️ Пользователь <code>{target_user_id}</code> не найден.",
        )
        return

    role = "👑 Администратор" if user.is_admin else "👤 Пользователь"
    display_name = html.escape(user.name) if user.name else "<i>Без имени</i>"
    notice_block = f"{notice}\n\n" if notice else ""

    text = (
        "✏️ <b>Карточка пользователя</b>\n\n"
        f"{notice_block}"
        f"👤 <b>Имя:</b> {display_name}\n"
        f"🆔 <b>Telegram ID:</b> <code>{user.user_id}</code>\n"
        f"🔑 <b>Роль:</b> {role}\n\n"
        "Выберите действие:"
    )
    await render_panel(
        bot=bot,
        user_id=admin_id,
        text=text,
        reply_markup=user_edit_card_kb(user.user_id, user.is_admin),
    )


@router.callback_query(F.data.startswith("users:edit_open:"))
async def cb_users_edit_open(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    if not is_admin_id(callback.from_user.id):
        await callback.answer("⛔ Доступно только администратору", show_alert=True)
        return

    await state.clear()
    target_user_id = int(callback.data.split(":")[2])
    await show_user_edit_card(bot, callback.from_user.id, target_user_id)
    await callback.answer()


@router.message(ReminderFSM.waiting_for_edit_user_id, F.text)
async def process_edit_user_id_input(message: Message, state: FSMContext, bot: Bot) -> None:
    await safe_delete_message(bot, message.chat.id, message.message_id)
    if not is_admin_id(message.from_user.id):
        await state.clear()
        return

    raw_id = message.text.strip()
    if not raw_id.isdigit():
        users = await get_all_bot_users()
        text = (
            "✏️ <b>Редактирование пользователя</b>\n\n"
            "⚠️ <b>Некорректный Telegram ID!</b>\n"
            "Выберите пользователя кнопкой ниже или введите его числовой Telegram ID:"
        )
        await render_panel(bot, message.from_user.id, text, users_edit_select_kb(users))
        return

    await state.clear()
    await show_user_edit_card(bot, message.from_user.id, int(raw_id))


@router.callback_query(F.data.startswith("users:edit_name:"))
async def cb_users_edit_name(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    if not is_admin_id(callback.from_user.id):
        await callback.answer("⛔ Доступно только администратору", show_alert=True)
        return

    target_user_id = int(callback.data.split(":")[2])
    user = await get_bot_user(target_user_id)
    if not user:
        await show_users_screen(
            bot, callback.from_user.id, notice="⚠️ Пользователь не найден."
        )
        await callback.answer()
        return

    await state.set_state(ReminderFSM.waiting_for_edit_user_name)
    await state.update_data(edit_target_user_id=target_user_id)

    current_name = html.escape(user.name) if user.name else "<i>Без имени</i>"
    text = (
        "✏️ <b>Изменение имени пользователя</b>\n\n"
        f"🆔 <b>Telegram ID:</b> <code>{user.user_id}</code>\n"
        f"👤 <b>Текущее имя:</b> {current_name}\n\n"
        "Отправьте в чат <b>новое имя</b> для этого пользователя:"
    )
    await render_panel(
        bot=bot,
        user_id=callback.from_user.id,
        text=text,
        reply_markup=user_edit_name_cancel_kb(target_user_id),
    )
    await callback.answer()


@router.message(ReminderFSM.waiting_for_edit_user_name, F.text)
async def process_edit_user_name_input(message: Message, state: FSMContext, bot: Bot) -> None:
    await safe_delete_message(bot, message.chat.id, message.message_id)
    if not is_admin_id(message.from_user.id):
        await state.clear()
        return

    new_name = message.text.strip()
    data = await state.get_data()
    target_user_id = data.get("edit_target_user_id")

    if not target_user_id:
        await state.clear()
        await show_users_screen(bot, message.from_user.id)
        return

    if not new_name or len(new_name) > 100:
        text = (
            "✏️ <b>Изменение имени пользователя</b>\n\n"
            f"🆔 <b>Telegram ID:</b> <code>{target_user_id}</code>\n\n"
            "⚠️ <b>Некорректное имя!</b>\n"
            "Введите новое имя пользователя (от 1 до 100 символов):"
        )
        await render_panel(
            bot,
            message.from_user.id,
            text,
            user_edit_name_cancel_kb(target_user_id),
        )
        return

    updated = await update_bot_user_name(target_user_id, new_name)
    await state.clear()

    if not updated:
        await show_users_screen(
            bot, message.from_user.id, notice="⚠️ Пользователь не найден."
        )
        return

    await show_user_edit_card(
        bot,
        message.from_user.id,
        target_user_id,
        notice=f"✅ <b>Имя успешно изменено на «{html.escape(new_name)}»!</b>",
    )


@router.callback_query(F.data == "users:del_menu")
async def cb_users_del_menu(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    if not is_admin_id(callback.from_user.id):
        await callback.answer("⛔ Доступно только администратору", show_alert=True)
        return

    users = await get_all_bot_users()
    removable_users = [u for u in users if not u.is_admin]
    if not removable_users:
        await show_users_screen(
            bot, callback.from_user.id, notice="ℹ️ Нет пользователей для удаления."
        )
        await callback.answer()
        return

    await state.clear()
    await state.set_state(ReminderFSM.waiting_for_del_user_id)

    text = (
        "🗑 <b>Удаление пользователя</b>\n\n"
        "Выберите пользователя кнопкой ниже или отправьте его <b>Telegram ID</b> в чат:"
    )
    await render_panel(
        bot=bot,
        user_id=callback.from_user.id,
        text=text,
        reply_markup=users_delete_kb(removable_users),
    )
    await callback.answer()


async def execute_user_removal(
    bot: Bot, admin_id: int, state: FSMContext, target_user_id: int
) -> None:
    if is_admin_id(target_user_id):
        await show_users_screen(
            bot, admin_id, notice="⚠️ Нельзя удалить администратора бота."
        )
        return

    user_obj = await get_bot_user(target_user_id)
    user_label = (
        f"<b>{html.escape(user_obj.name)}</b> (<code>{target_user_id}</code>)"
        if user_obj and user_obj.name
        else f"<code>{target_user_id}</code>"
    )

    removed = await remove_bot_user(target_user_id)
    await state.clear()

    if not removed:
        await show_users_screen(
            bot,
            admin_id,
            notice=f"⚠️ Пользователь <code>{target_user_id}</code> не найден в базе.",
        )
        return

    await cleanup_old_messages(bot, target_user_id)
    old_panel_id = await get_panel_message_id(target_user_id)
    if old_panel_id:
        await safe_delete_message(bot, target_user_id, old_panel_id)

    notify_status = "уведомление отправлено"
    try:
        await bot.send_message(
            chat_id=target_user_id,
            text="⛔ <b>Вы удалены из списка пользователей, доступ к боту прекращён.</b>",
        )
    except Exception:
        notify_status = "доступ закрыт"

    await show_users_screen(
        bot,
        admin_id,
        notice=f"✅ <b>Пользователь {user_label} удалён</b> ({notify_status}).",
    )


@router.callback_query(F.data.startswith("users:del:"))
async def cb_users_del_confirm(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    if not is_admin_id(callback.from_user.id):
        await callback.answer("⛔ Доступно только администратору", show_alert=True)
        return

    target_user_id = int(callback.data.split(":")[2])
    await execute_user_removal(bot, callback.from_user.id, state, target_user_id)
    await callback.answer("Пользователь удалён")


@router.message(ReminderFSM.waiting_for_del_user_id, F.text)
async def process_del_user_id(message: Message, state: FSMContext, bot: Bot) -> None:
    await safe_delete_message(bot, message.chat.id, message.message_id)
    if not is_admin_id(message.from_user.id):
        await state.clear()
        return

    raw_id = message.text.strip()
    if not raw_id.isdigit():
        users = await get_all_bot_users()
        removable_users = [u for u in users if not u.is_admin]
        text = (
            "🗑 <b>Удаление пользователя</b>\n\n"
            "⚠️ <b>Некорректный Telegram ID!</b>\n"
            "Выберите пользователя кнопкой ниже или введите его числовой Telegram ID:"
        )
        await render_panel(bot, message.from_user.id, text, users_delete_kb(removable_users))
        return

    await execute_user_removal(bot, message.from_user.id, state, int(raw_id))
