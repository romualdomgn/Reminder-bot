import calendar
from datetime import date
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from database import BotUser

RU_MONTH_NAMES: dict[int, str] = {
    1: "Январь",
    2: "Февраль",
    3: "Март",
    4: "Апрель",
    5: "Май",
    6: "Июнь",
    7: "Июль",
    8: "Август",
    9: "Сентябрь",
    10: "Октябрь",
    11: "Ноябрь",
    12: "Декабрь",
}

RU_MONTH_SHORT: dict[int, str] = {
    1: "Янв",
    2: "Фев",
    3: "Мар",
    4: "Апр",
    5: "Май",
    6: "Июн",
    7: "Июл",
    8: "Авг",
    9: "Сен",
    10: "Окт",
    11: "Ноя",
    12: "Дек",
}

WEEKDAY_HEADERS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]


def build_calendar_kb(
    year: int,
    month: int,
    today: date,
    nav_prefix: str,
    ym_prefix: str,
    pick_prefix: str,
    back_callback: str,
    plain_home: bool = False,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []

    month_title = f"{RU_MONTH_NAMES.get(month, '')} {year} >"
    can_go_prev = (year, month) > (today.year, today.month)
    prev_cb = f"{nav_prefix}:{year}:{month}:prev" if can_go_prev else "cal:past_month"
    next_cb = f"{nav_prefix}:{year}:{month}:next"
    ym_cb = f"{ym_prefix}:{year}:{month}"

    # Верхняя строка: «Месяц Год >» и стрелки < >
    rows.append(
        [
            InlineKeyboardButton(text=month_title, callback_data=ym_cb),
            InlineKeyboardButton(text="<", callback_data=prev_cb),
            InlineKeyboardButton(text=">", callback_data=next_cb),
        ]
    )

    # Строка заголовков дней недели
    rows.append(
        [InlineKeyboardButton(text=day_lbl, callback_data="cal:ignore") for day_lbl in WEEKDAY_HEADERS]
    )

    # Сетка дней месяца
    month_matrix = calendar.monthcalendar(year, month)
    for week in month_matrix:
        week_row: list[InlineKeyboardButton] = []
        for day_num in week:
            if day_num == 0:
                week_row.append(InlineKeyboardButton(text=" ", callback_data="cal:ignore"))
            else:
                cell_date = date(year, month, day_num)
                if cell_date < today:
                    week_row.append(
                        InlineKeyboardButton(text=f"·{day_num}·", callback_data="cal:past")
                    )
                elif cell_date == today:
                    week_row.append(
                        InlineKeyboardButton(
                            text=f"[{day_num}]",
                            callback_data=f"{pick_prefix}:{cell_date.isoformat()}",
                        )
                    )
                else:
                    week_row.append(
                        InlineKeyboardButton(
                            text=str(day_num),
                            callback_data=f"{pick_prefix}:{cell_date.isoformat()}",
                        )
                    )
        rows.append(week_row)

    home_text = "В главное меню" if plain_home else "🏠 В главное меню"
    rows.append([InlineKeyboardButton(text="Назад", callback_data=back_callback)])
    rows.append([InlineKeyboardButton(text=home_text, callback_data="menu:home")])

    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_calendar_ym_kb(
    year: int,
    current_month: int,
    today: date,
    year_nav_prefix: str,
    month_pick_prefix: str,
    plain_home: bool = False,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []

    next_year = year + 1
    month_name = RU_MONTH_NAMES.get(current_month, "")
    rows.append(
        [
            InlineKeyboardButton(
                text=f"⏩ На год вперёд: {month_name} {next_year}",
                callback_data=f"{month_pick_prefix}:{next_year}:{current_month}",
            )
        ]
    )

    can_prev_year = year > today.year
    prev_year_cb = f"{year_nav_prefix}:{year}:{current_month}:prev" if can_prev_year else "cal:past_year"
    next_year_cb = f"{year_nav_prefix}:{year}:{current_month}:next"

    rows.append(
        [
            InlineKeyboardButton(text="<", callback_data=prev_year_cb),
            InlineKeyboardButton(
                text=f"Год: {year}",
                callback_data=f"{month_pick_prefix}:{year}:{max(current_month, today.month) if year == today.year else current_month}",
            ),
            InlineKeyboardButton(text=">", callback_data=next_year_cb),
        ]
    )

    for row_idx in range(4):
        m_row: list[InlineKeyboardButton] = []
        for col_idx in range(1, 4):
            m_num = row_idx * 3 + col_idx
            m_label = RU_MONTH_SHORT[m_num]
            if (year, m_num) < (today.year, today.month):
                m_row.append(
                    InlineKeyboardButton(text=f"·{m_label}·", callback_data="cal:past_month")
                )
            elif m_num == current_month:
                m_row.append(
                    InlineKeyboardButton(
                        text=f"[{m_label}]",
                        callback_data=f"{month_pick_prefix}:{year}:{m_num}",
                    )
                )
            else:
                m_row.append(
                    InlineKeyboardButton(
                        text=m_label,
                        callback_data=f"{month_pick_prefix}:{year}:{m_num}",
                    )
                )
        rows.append(m_row)

    back_month = max(current_month, today.month) if year == today.year else current_month
    home_text = "В главное меню" if plain_home else "🏠 В главное меню"
    rows.append(
        [
            InlineKeyboardButton(
                text="Назад",
                callback_data=f"{month_pick_prefix}:{year}:{back_month}",
            )
        ]
    )
    rows.append([InlineKeyboardButton(text=home_text, callback_data="menu:home")])

    return InlineKeyboardMarkup(inline_keyboard=rows)


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


# --- Клавиатуры раздела /user ---

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


# --- Клавиатуры раздела /reminders ---

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
            [InlineKeyboardButton(text="Календарь", callback_data=f"edate:custom:{reminder_id}")],
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
            [InlineKeyboardButton(text="📅 Календарь", callback_data="date:custom")],
            [InlineKeyboardButton(text="Назад", callback_data="menu:list")],
            [InlineKeyboardButton(text="🏠 В главное меню", callback_data="menu:home")],
        ]
    )


def time_selection_kb(skip_btn_text: str = "Сегодня в 15:00") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=skip_btn_text, callback_data="time:skip")],
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
