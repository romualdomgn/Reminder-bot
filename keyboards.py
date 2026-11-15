from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from database import BotUser


def main_menu_kb(
    is_admin: bool = False,
    has_user_section: bool = False,
    create_btn_text: str = "➕ Создать напоминание",
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(text=create_btn_text, callback_data="menu:create")],
        [InlineKeyboardButton(text="📋 Напоминания", callback_data="menu:list")],
    ]
    if is_admin:
        rows.append([InlineKeyboardButton(text="👥 Пользователи", callback_data="users:list")])
    elif has_user_section:
        rows.append([InlineKeyboardButton(text="👥 Пользователи", callback_data="my_users:list")])
    rows.append([InlineKeyboardButton(text="⚙️ Настройки", callback_data="menu:settings")])
    if not is_admin:
        rows.append([InlineKeyboardButton(text="ℹ️ Информация", callback_data="info:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def info_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Напоминания", callback_data="info:reminders")],
            [InlineKeyboardButton(text="Настройки", callback_data="info:settings")],
            [InlineKeyboardButton(text="Добавление нового пользователя", callback_data="info:add_user")],
            [InlineKeyboardButton(text="О приложении", callback_data="info:general")],
            [InlineKeyboardButton(text="🏠 В главное меню", callback_data="menu:home")],
        ]
    )


def info_card_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Назад", callback_data="info:main")],
            [InlineKeyboardButton(text="🏠 В главное меню", callback_data="menu:home")],
        ]
    )


def admin_ok_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Ok", callback_data="ack_alert")],
        ]
    )


def settings_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🕒 Настроить время устройства", callback_data="menu:tz")],
            [InlineKeyboardButton(text="➕ Добавить нового пользователя", callback_data="settings:add_user")],
            [InlineKeyboardButton(text="🏠 В главное меню", callback_data="menu:home")],
        ]
    )


# --- Клавиатуры раздела /users (для администратора) ---

def users_section_kb(has_users: bool, has_removable_users: bool) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(text="➕ Добавить нового пользователя", callback_data="users:add")],
    ]
    if has_users:
        rows.append([InlineKeyboardButton(text="✏️ Редактировать пользователя", callback_data="users:edit_menu")])
    if has_removable_users:
        rows.append([InlineKeyboardButton(text="🗑 Удалить пользователя", callback_data="users:del_menu")])
    rows.append([InlineKeyboardButton(text="🏠 В главное меню", callback_data="menu:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def add_user_cancel_kb(origin: str = "settings") -> InlineKeyboardMarkup:
    if origin == "users":
        back_btn = InlineKeyboardButton(text="⬅️ Назад к пользователям", callback_data="users:list")
    elif origin == "my_users":
        back_btn = InlineKeyboardButton(text="Назад", callback_data="my_users:list")
    else:
        back_btn = InlineKeyboardButton(text="⬅️ Назад в настройки", callback_data="menu:settings")
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [back_btn],
            [InlineKeyboardButton(text="🏠 В главное меню", callback_data="menu:home")],
        ]
    )


def users_cancel_kb() -> InlineKeyboardMarkup:
    return add_user_cancel_kb(origin="users")


def users_edit_select_kb(users: list[BotUser]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for u in users:
        role_icon = "👑" if u.is_admin else "👤"
        display_name = u.name if u.name else "Без имени"
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"✏️ {role_icon} {display_name} ({u.user_id})",
                    callback_data=f"users:edit_open:{u.user_id}",
                )
            ]
        )
    rows.append([InlineKeyboardButton(text="⬅️ Назад к пользователям", callback_data="users:list")])
    rows.append([InlineKeyboardButton(text="🏠 В главное меню", callback_data="menu:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def user_edit_card_kb(user_id: int, is_admin: bool) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(text="✏️ Изменить имя", callback_data=f"users:edit_name:{user_id}")],
    ]
    if not is_admin:
        rows.append([InlineKeyboardButton(text="🗑 Удалить пользователя", callback_data=f"users:del:{user_id}")])
    rows.append([InlineKeyboardButton(text="⬅️ К выбору пользователя", callback_data="users:edit_menu")])
    rows.append([InlineKeyboardButton(text="👥 В раздел «Пользователи»", callback_data="users:list")])
    rows.append([InlineKeyboardButton(text="🏠 В главное меню", callback_data="menu:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def user_edit_name_cancel_kb(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Назад к пользователю", callback_data=f"users:edit_open:{user_id}")],
            [InlineKeyboardButton(text="👥 В раздел «Пользователи»", callback_data="users:list")],
            [InlineKeyboardButton(text="🏠 В главное меню", callback_data="menu:home")],
        ]
    )


def users_delete_kb(removable_users: list[BotUser]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for u in removable_users:
        display_name = u.name if u.name else "Без имени"
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"🗑 Удалить: {display_name} ({u.user_id})",
                    callback_data=f"users:del:{u.user_id}",
                )
            ]
        )
    rows.append([InlineKeyboardButton(text="⬅️ Назад к пользователям", callback_data="users:list")])
    rows.append([InlineKeyboardButton(text="🏠 В главное меню", callback_data="menu:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# --- Клавиатуры раздела /user (все кнопки возврата в /user названы «Назад») ---

def my_users_section_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Добавить нового пользователя", callback_data="my_users:add")],
            [InlineKeyboardButton(text="Редактировать пользователя", callback_data="my_users:edit_menu")],
            [InlineKeyboardButton(text="Удалить пользователя", callback_data="my_users:del_menu")],
            [InlineKeyboardButton(text="🏠 В главное меню", callback_data="menu:home")],
        ]
    )


def my_users_edit_select_kb(users: list[BotUser]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for u in users:
        display_name = u.name if u.name else "Без имени"
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"✏️ {display_name} ({u.user_id})",
                    callback_data=f"my_users:edit_open:{u.user_id}",
                )
            ]
        )
    rows.append([InlineKeyboardButton(text="Назад", callback_data="my_users:list")])
    rows.append([InlineKeyboardButton(text="🏠 В главное меню", callback_data="menu:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def my_user_edit_card_kb(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✏️ Изменить имя", callback_data=f"my_users:edit_name:{user_id}")],
            [InlineKeyboardButton(text="🗑 Удалить пользователя", callback_data=f"my_users:del:{user_id}")],
            [InlineKeyboardButton(text="⬅️ К выбору пользователя", callback_data="my_users:edit_menu")],
            [InlineKeyboardButton(text="Назад", callback_data="my_users:list")],
            [InlineKeyboardButton(text="🏠 В главное меню", callback_data="menu:home")],
        ]
    )


def my_user_edit_name_cancel_kb(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Назад к пользователю", callback_data=f"my_users:edit_open:{user_id}")],
            [InlineKeyboardButton(text="Назад", callback_data="my_users:list")],
            [InlineKeyboardButton(text="🏠 В главное меню", callback_data="menu:home")],
        ]
    )


def my_users_delete_kb(users: list[BotUser]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for u in users:
        display_name = u.name if u.name else "Без имени"
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"🗑 Удалить: {display_name} ({u.user_id})",
                    callback_data=f"my_users:del:{u.user_id}",
                )
            ]
        )
    rows.append([InlineKeyboardButton(text="Назад", callback_data="my_users:list")])
    rows.append([InlineKeyboardButton(text="🏠 В главное меню", callback_data="menu:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# --- Клавиатуры раздела /reminders (без значков и эмодзи) ---

def reminders_section_kb(has_reminders: bool) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if has_reminders:
        rows.append([InlineKeyboardButton(text="Редактировать напоминания", callback_data="rem:edit_prompt")])
    rows.append([InlineKeyboardButton(text="Создать напоминание", callback_data="menu:create")])
    rows.append([InlineKeyboardButton(text="В главное меню", callback_data="menu:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def reminder_number_prompt_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Назад к напоминаниям", callback_data="menu:list")],
            [InlineKeyboardButton(text="В главное меню", callback_data="menu:home")],
        ]
    )


def reminder_edit_menu_kb(reminder_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Изменить текст", callback_data=f"edit:text:{reminder_id}")],
            [InlineKeyboardButton(text="Изменить дату", callback_data=f"edit:date:{reminder_id}")],
            [InlineKeyboardButton(text="Изменить время", callback_data=f"edit:time:{reminder_id}")],
            [InlineKeyboardButton(text="Изменить периодичность", callback_data=f"edit:rec:{reminder_id}")],
            [InlineKeyboardButton(text="Удалить напоминание", callback_data=f"del:{reminder_id}")],
            [InlineKeyboardButton(text="Назад к напоминаниям", callback_data="menu:list")],
            [InlineKeyboardButton(text="В главное меню", callback_data="menu:home")],
        ]
    )


def edit_text_cancel_kb(reminder_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Назад к напоминанию", callback_data=f"rem:open:{reminder_id}")],
            [InlineKeyboardButton(text="Назад к напоминаниям", callback_data="menu:list")],
            [InlineKeyboardButton(text="В главное меню", callback_data="menu:home")],
        ]
    )


def edit_date_selection_kb(reminder_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Сегодня", callback_data=f"edate:today:{reminder_id}")],
            [InlineKeyboardButton(text="Завтра", callback_data=f"edate:1d:{reminder_id}")],
            [InlineKeyboardButton(text="Через неделю", callback_data=f"edate:1w:{reminder_id}")],
            [InlineKeyboardButton(text="Через месяц", callback_data=f"edate:1m:{reminder_id}")],
            [InlineKeyboardButton(text="Ввести дату напоминания", callback_data=f"edate:custom:{reminder_id}")],
            [InlineKeyboardButton(text="Назад к напоминанию", callback_data=f"rem:open:{reminder_id}")],
            [InlineKeyboardButton(text="В главное меню", callback_data="menu:home")],
        ]
    )


def edit_time_selection_kb(reminder_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Установить 15:00", callback_data=f"etime:skip:{reminder_id}")],
            [InlineKeyboardButton(text="Назад к напоминанию", callback_data=f"rem:open:{reminder_id}")],
            [InlineKeyboardButton(text="В главное меню", callback_data="menu:home")],
        ]
    )


def edit_recurrence_type_kb(reminder_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Один раз", callback_data=f"erec:once:{reminder_id}")],
            [InlineKeyboardButton(text="Повторяющееся", callback_data=f"erec:menu:{reminder_id}")],
            [InlineKeyboardButton(text="Назад к напоминанию", callback_data=f"rem:open:{reminder_id}")],
            [InlineKeyboardButton(text="В главное меню", callback_data="menu:home")],
        ]
    )


def edit_recurrence_period_kb(reminder_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Каждый день", callback_data=f"erec_set:daily:{reminder_id}")],
            [InlineKeyboardButton(text="Раз в неделю", callback_data=f"erec_set:weekly:{reminder_id}")],
            [InlineKeyboardButton(text="Раз в месяц", callback_data=f"erec_set:monthly:{reminder_id}")],
            [InlineKeyboardButton(text="Раз в год", callback_data=f"erec_set:yearly:{reminder_id}")],
            [InlineKeyboardButton(text="Назад", callback_data=f"edit:rec:{reminder_id}")],
            [InlineKeyboardButton(text="В главное меню", callback_data="menu:home")],
        ]
    )


# --- Клавиатуры создания напоминаний и настроек ---

def cancel_to_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Назад", callback_data="menu:list")],
            [InlineKeyboardButton(text="🏠 В главное меню", callback_data="menu:home")],
        ]
    )


def date_selection_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Сегодня", callback_data="date:today")],
            [InlineKeyboardButton(text="Завтра", callback_data="date:1d")],
            [InlineKeyboardButton(text="Через неделю", callback_data="date:1w")],
            [InlineKeyboardButton(text="Через месяц", callback_data="date:1m")],
            [InlineKeyboardButton(text="📅 Ввести дату напоминания", callback_data="date:custom")],
            [InlineKeyboardButton(text="Назад", callback_data="menu:list")],
            [InlineKeyboardButton(text="🏠 В главное меню", callback_data="menu:home")],
        ]
    )


def time_selection_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Сегодня в 15:00", callback_data="time:skip")],
            [InlineKeyboardButton(text="⬅️ Изменить дату", callback_data="time:back_to_date")],
            [InlineKeyboardButton(text="Назад", callback_data="menu:list")],
            [InlineKeyboardButton(text="🏠 В главное меню", callback_data="menu:home")],
        ]
    )


def recurrence_type_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Один раз", callback_data="rec:once")],
            [InlineKeyboardButton(text="Повторяющееся", callback_data="rec:menu")],
            [InlineKeyboardButton(text="⬅️ Изменить время", callback_data="rec:back_to_time")],
            [InlineKeyboardButton(text="Назад", callback_data="menu:list")],
            [InlineKeyboardButton(text="🏠 В главное меню", callback_data="menu:home")],
        ]
    )


def recurrence_period_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Каждый день", callback_data="rec_set:daily")],
            [InlineKeyboardButton(text="Раз в неделю", callback_data="rec_set:weekly")],
            [InlineKeyboardButton(text="Раз в месяц", callback_data="rec_set:monthly")],
            [InlineKeyboardButton(text="Раз в год", callback_data="rec_set:yearly")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="rec:back_to_type")],
            [InlineKeyboardButton(text="Назад", callback_data="menu:list")],
            [InlineKeyboardButton(text="🏠 В главное меню", callback_data="menu:home")],
        ]
    )


def tz_selection_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="CET (UTC+1)", callback_data="tz:60")],
            [InlineKeyboardButton(text="Клд (UTC+2)", callback_data="tz:120")],
            [InlineKeyboardButton(text="Мск (UTC+3)", callback_data="tz:180")],
            [InlineKeyboardButton(text="Смр (UTC+4)", callback_data="tz:240")],
            [InlineKeyboardButton(text="Мгн (UTC+5)", callback_data="tz:300")],
            [InlineKeyboardButton(text="Омск (UTC+6)", callback_data="tz:360")],
            [InlineKeyboardButton(text="Крс (UTC+7)", callback_data="tz:420")],
            [InlineKeyboardButton(text="Ирк (UTC+8)", callback_data="tz:480")],
            [InlineKeyboardButton(text="Якт (UTC+9)", callback_data="tz:540")],
            [InlineKeyboardButton(text="⬅️ Назад в настройки", callback_data="menu:settings")],
            [InlineKeyboardButton(text="🏠 В главное меню", callback_data="menu:home")],
        ]
    )


def notification_ack_kb(reminder_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔁 Повторить", callback_data=f"notif:repeat:{reminder_id}")],
            [InlineKeyboardButton(text="⏳ Отложить", callback_data=f"notif:snooze_menu:{reminder_id}")],
            [InlineKeyboardButton(text="✅ Прочитано (скрыть)", callback_data="ack_alert")],
        ]
    )


def notification_snooze_kb(reminder_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="5 минут", callback_data=f"notif:snooze:5m:{reminder_id}")],
            [InlineKeyboardButton(text="1 час", callback_data=f"notif:snooze:1h:{reminder_id}")],
            [InlineKeyboardButton(text="1 день", callback_data=f"notif:snooze:1d:{reminder_id}")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data=f"notif:back:{reminder_id}")],
        ]
    )
