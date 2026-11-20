import calendar
from datetime import date, datetime
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from database import BotUser

RU_MONTH_NAMES: dict[int, str] = {
    1: "Январь", 2: "Февраль", 3: "Март", 4: "Апрель",
    5: "Май", 6: "Июнь", 7: "Июль", 8: "Август",
    9: "Сентябрь", 10: "Октябрь", 11: "Ноябрь", 12: "Декабрь",
}

RU_MONTH_SHORT: dict[int, str] = {
    1: "Янв", 2: "Фев", 3: "Мар", 4: "Апр",
    5: "Май", 6: "Июн", 7: "Июл", 8: "Авг",
    9: "Сен", 10: "Окт", 11: "Ноя", 12: "Дек",
}

WEEKDAY_HEADERS = ["Пн", "Вт", "Ср", "Чт", "Пт", "𝐂б", "𝐁𝐜"]

_BOLD_DIGITS_MAP = str.maketrans("0123456789", "𝟎𝟏𝟐𝟑𝟒𝟓𝟔𝟕𝟖𝟗")


def to_bold_digits(val: int | str) -> str:
    return str(val).translate(_BOLD_DIGITS_MAP)


def _split_grid_pages(
    items: list[tuple[int, int]],
) -> list[tuple[list[tuple[int, int]], bool, bool]]:
    total = len(items)
    if total <= 15:
        return [(items, False, False)]

    pages: list[tuple[list[tuple[int, int]], bool, bool]] = [(items[:14], False, True)]
    pos = 14
    while pos < total:
        remaining = total - pos
        if remaining <= 14:
            pages.append((items[pos:], True, False))
            break
        pages.append((items[pos : pos + 13], True, True))
        pos += 13
    return pages


def get_grid_page_count(total: int) -> int:
    if total <= 15:
        return 1
    remaining = total - 14
    pages = 1
    while remaining > 14:
        remaining -= 13
        pages += 1
    return pages + 1


def get_reminder_grid_page_count(total: int) -> int:
    return get_grid_page_count(total)


def _distribute_buttons_grid(
    buttons: list[InlineKeyboardButton],
) -> list[list[InlineKeyboardButton]]:
    n = len(buttons)
    if n == 0:
        return []
    if n <= 5:
        num_rows = 1
    elif n <= 10:
        num_rows = 2
    else:
        num_rows = 3

    base, rem = divmod(n, num_rows)
    rows: list[list[InlineKeyboardButton]] = []
    pos = 0
    for r in range(num_rows):
        row_len = base + (1 if r < rem else 0)
        rows.append(buttons[pos : pos + row_len])
        pos += row_len
    return rows


def _build_numbered_grid_rows(
    items: list[tuple[int, int]],
    page: int,
    item_prefix: str,
    page_prefix: str,
    include_idx_in_callback: bool = True,
) -> list[list[InlineKeyboardButton]]:
    pages = _split_grid_pages(items)
    page = max(0, min(page, len(pages) - 1))
    page_items, has_prev, has_next = pages[page]

    grid_buttons: list[InlineKeyboardButton] = []
    if has_prev:
        grid_buttons.append(
            InlineKeyboardButton(
                text="⬅️",
                callback_data=f"{page_prefix}:{page - 1}",
            )
        )
    for idx, item_id in page_items:
        cb_data = f"{item_prefix}:{item_id}:{idx}" if include_idx_in_callback else f"{item_prefix}:{item_id}"
        grid_buttons.append(
            InlineKeyboardButton(
                text=str(idx),
                callback_data=cb_data,
            )
        )
    if has_next:
        grid_buttons.append(
            InlineKeyboardButton(
                text="➡️",
                callback_data=f"{page_prefix}:{page + 1}",
            )
        )

    return _distribute_buttons_grid(grid_buttons)


def build_calendar_kb(
    year: int, month: int, today: date,
    nav_prefix: str, ym_prefix: str, pick_prefix: str,
    back_callback: str, plain_home: bool = False,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    month_title = f"{RU_MONTH_NAMES.get(month, '')} {year} >"
    can_go_prev = (year, month) > (today.year, today.month)
    prev_cb = f"{nav_prefix}:{year}:{month}:prev" if can_go_prev else "cal:past_month"
    next_cb = f"{nav_prefix}:{year}:{month}:next"
    ym_cb = f"{ym_prefix}:{year}:{month}"

    rows.append([
        InlineKeyboardButton(text=month_title, callback_data=ym_cb),
        InlineKeyboardButton(text="<", callback_data=prev_cb),
        InlineKeyboardButton(text=">", callback_data=next_cb),
    ])
    rows.append([InlineKeyboardButton(text=day_lbl, callback_data="cal:ignore") for day_lbl in WEEKDAY_HEADERS])

    month_matrix = calendar.monthcalendar(year, month)
    for week in month_matrix:
        week_row: list[InlineKeyboardButton] = []
        for col_idx, day_num in enumerate(week):
            if day_num == 0:
                week_row.append(InlineKeyboardButton(text=" ", callback_data="cal:ignore"))
            else:
                cell_date = date(year, month, day_num)
                is_weekend = col_idx in (5, 6)
                day_str = to_bold_digits(day_num) if (cell_date == today or is_weekend) else str(day_num)
                if cell_date < today:
                    week_row.append(InlineKeyboardButton(text=f"·{day_str}·", callback_data="cal:past"))
                elif cell_date == today:
                    week_row.append(InlineKeyboardButton(text=f"[{day_str}]", callback_data=f"{pick_prefix}:{cell_date.isoformat()}"))
                else:
                    week_row.append(InlineKeyboardButton(text=day_str, callback_data=f"{pick_prefix}:{cell_date.isoformat()}"))
        rows.append(week_row)

    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data=back_callback)])
    rows.append([InlineKeyboardButton(text="🏠 В главное меню", callback_data="menu:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_calendar_ym_kb(
    year: int, current_month: int, today: date,
    year_nav_prefix: str, month_pick_prefix: str, plain_home: bool = False,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    next_year = year + 1
    month_name = RU_MONTH_NAMES.get(current_month, "")
    rows.append([InlineKeyboardButton(text=f"⏩ На год вперёд: {month_name} {next_year}", callback_data=f"{month_pick_prefix}:{next_year}:{current_month}")])

    can_prev_year = year > today.year
    prev_year_cb = f"{year_nav_prefix}:{year}:{current_month}:prev" if can_prev_year else "cal:past_year"
    next_year_cb = f"{year_nav_prefix}:{year}:{current_month}:next"

    rows.append([
        InlineKeyboardButton(text="<", callback_data=prev_year_cb),
        InlineKeyboardButton(text=f"Год: {year}", callback_data=f"{month_pick_prefix}:{year}:{max(current_month, today.month) if year == today.year else current_month}"),
        InlineKeyboardButton(text=">", callback_data=next_year_cb),
    ])

    for row_idx in range(4):
        m_row: list[InlineKeyboardButton] = []
        for col_idx in range(1, 4):
            m_num = row_idx * 3 + col_idx
            m_label = RU_MONTH_SHORT[m_num]
            if (year, m_num) < (today.year, today.month):
                m_row.append(InlineKeyboardButton(text=f"·{m_label}·", callback_data="cal:past_month"))
            elif m_num == current_month:
                m_row.append(InlineKeyboardButton(text=f"[{m_label}]", callback_data=f"{month_pick_prefix}:{year}:{m_num}"))
            else:
                m_row.append(InlineKeyboardButton(text=m_label, callback_data=f"{month_pick_prefix}:{year}:{m_num}"))
        rows.append(m_row)

    back_month = max(current_month, today.month) if year == today.year else current_month
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data=f"{month_pick_prefix}:{year}:{back_month}")])
    rows.append([InlineKeyboardButton(text="🏠 В главное меню", callback_data="menu:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_hours_picker_kb(
    target_date: date, user_now: datetime, skip_btn_text: str,
    skip_callback: str, hour_prefix: str, change_date_callback: str | None,
    back_callback: str, plain_style: bool = False,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    today = user_now.date()
    now_naive = user_now.replace(tzinfo=None)

    skip_label = skip_btn_text if skip_btn_text.startswith("⏰") else f"⏰ {skip_btn_text}"
    rows.append([InlineKeyboardButton(text=skip_label, callback_data=skip_callback)])

    for row_idx in range(4):
        h_row: list[InlineKeyboardButton] = []
        for col_idx in range(6):
            h = row_idx * 6 + col_idx
            h_str = f"{h:02d}"
            is_past = (
                target_date < today
                or (target_date == today and (h < now_naive.hour or (h == now_naive.hour and now_naive.minute >= 59)))
            )
            if is_past:
                h_row.append(InlineKeyboardButton(text=f"·{h_str}·", callback_data="cal:past_time"))
            else:
                h_row.append(InlineKeyboardButton(text=h_str, callback_data=f"{hour_prefix}:{h}"))
        rows.append(h_row)

    if change_date_callback:
        rows.append([InlineKeyboardButton(text="📅 Изменить дату", callback_data=change_date_callback)])

    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data=back_callback)])
    rows.append([InlineKeyboardButton(text="🏠 В главное меню", callback_data="menu:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_minutes_drum_kb(
    hour: int, minute: int, target_date: date, user_now: datetime,
    drum_prefix: str, pick_prefix: str, back_to_hours_callback: str,
    back_callback: str, plain_style: bool = False,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    today = user_now.date()
    now_naive = user_now.replace(tzinfo=None)

    prev_h = (hour - 1) % 24
    next_h = (hour + 1) % 24
    prev_m = (minute - 1) % 60
    next_m = (minute + 1) % 60

    rows.append([
        InlineKeyboardButton(text=f"▲ {prev_h:02d} ч", callback_data=f"{drum_prefix}:{prev_h}:{minute}"),
        InlineKeyboardButton(text=f"▲ {prev_m:02d} мин", callback_data=f"{drum_prefix}:{hour}:{prev_m}"),
    ])
    rows.append([InlineKeyboardButton(text=f"✅ Выбрать {hour:02d}:{minute:02d}", callback_data=f"{pick_prefix}:{hour}:{minute}")])
    rows.append([
        InlineKeyboardButton(text=f"▼ {next_h:02d} ч", callback_data=f"{drum_prefix}:{next_h}:{minute}"),
        InlineKeyboardButton(text=f"▼ {next_m:02d} мин", callback_data=f"{drum_prefix}:{hour}:{next_m}"),
    ])

    for row_idx in range(3):
        m_row: list[InlineKeyboardButton] = []
        for col_idx in range(4):
            m_val = (row_idx * 4 + col_idx) * 5
            label = f"{hour:02d}:{m_val:02d}"
            is_past = (
                target_date < today
                or (target_date == today and (hour, m_val) <= (now_naive.hour, now_naive.minute))
            )
            if is_past:
                m_row.append(InlineKeyboardButton(text=f"·{label}·", callback_data="cal:past_time"))
            elif m_val == minute:
                m_row.append(InlineKeyboardButton(text=f"[{label}]", callback_data=f"{pick_prefix}:{hour}:{m_val}"))
            else:
                m_row.append(InlineKeyboardButton(text=label, callback_data=f"{pick_prefix}:{hour}:{m_val}"))
        rows.append(m_row)

    rows.append([InlineKeyboardButton(text="⬅️ К выбору часа", callback_data=back_to_hours_callback)])
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data=back_callback)])
    rows.append([InlineKeyboardButton(text="🏠 В главное меню", callback_data="menu:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def main_menu_kb(
    is_admin: bool = False,
    has_user_section: bool = False,
    has_pending_notifications: bool = False,
    create_btn_text: str = "➕ Создать напоминание",
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(text=create_btn_text, callback_data="menu:create")],
        [InlineKeyboardButton(text="📋 Напоминания", callback_data="menu:list")],
    ]
    if has_pending_notifications:
        rows.append([InlineKeyboardButton(text="🔔 Уведомления", callback_data="notifications:list")])
    if is_admin:
        rows.append([InlineKeyboardButton(text="👥 Пользователи", callback_data="users:list")])
    elif has_user_section:
        rows.append([InlineKeyboardButton(text="👥 Пользователи", callback_data="my_users:list")])
    rows.append([InlineKeyboardButton(text="⚙️ Настройки", callback_data="menu:settings")])
    if not is_admin:
        rows.append([InlineKeyboardButton(text="ℹ️ Информация", callback_data="info:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def notifications_section_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🏠 В главное меню", callback_data="menu:home")],
        ]
    )


def info_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📋 Как создать напоминание", callback_data="info:reminders")],
            [InlineKeyboardButton(text="🔔 Работа с уведомлениями", callback_data="info:notifications")],
            [InlineKeyboardButton(text="🕒 Выбор часового пояса", callback_data="info:settings")],
            [InlineKeyboardButton(text="👤 Как добавить нового пользователя", callback_data="info:add_user")],
            [InlineKeyboardButton(text="🌐 О приложении", callback_data="info:general")],
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
            [InlineKeyboardButton(text="🕒 Настроить время бота", callback_data="menu:tz")],
            [InlineKeyboardButton(text="➕ Добавить нового пользователя", callback_data="settings:add_user")],
            [InlineKeyboardButton(text="🏠 В главное меню", callback_data="menu:home")],
        ]
    )


def users_section_kb(has_users: bool, has_removable_users: bool) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(text="Мои пользователи", callback_data="users:my_list")],
        [InlineKeyboardButton(text="Все пользователи", callback_data="users:all_list")],
        [InlineKeyboardButton(text="➕ Добавить нового пользователя", callback_data="users:add")],
    ]
    if has_users:
        rows.append([InlineKeyboardButton(text="✏️ Редактировать пользователя", callback_data="users:edit_menu")])
    if has_removable_users:
        rows.append([InlineKeyboardButton(text="🗑 Удалить пользователя", callback_data="users:del_menu")])
    rows.append([InlineKeyboardButton(text="🏠 В главное меню", callback_data="menu:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def users_sublist_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Назад", callback_data="users:list")],
            [InlineKeyboardButton(text="🏠 В главное меню", callback_data="menu:home")],
        ]
    )


def add_user_cancel_kb(origin: str = "settings") -> InlineKeyboardMarkup:
    if origin == "users":
        back_btn = InlineKeyboardButton(text="⬅️ Назад", callback_data="users:list")
    elif origin == "my_users":
        back_btn = InlineKeyboardButton(text="⬅️ Назад", callback_data="my_users:list")
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


def users_edit_select_kb(
    items: list[tuple[int, int]],
    page: int = 0,
) -> InlineKeyboardMarkup:
    rows = _build_numbered_grid_rows(
        items=items,
        page=page,
        item_prefix="users:edit_open",
        page_prefix="users:edit_page",
        include_idx_in_callback=False,
    )
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="users:list")])
    rows.append([InlineKeyboardButton(text="🏠 В главное меню", callback_data="menu:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def user_edit_card_kb(user_id: int, is_admin: bool) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(text="✏️ Изменить имя", callback_data=f"users:edit_name:{user_id}")],
    ]
    if not is_admin:
        rows.append([InlineKeyboardButton(text="🗑 Удалить пользователя", callback_data=f"users:del_ask:{user_id}:card")])
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


def users_delete_kb(
    items: list[tuple[int, int]],
    page: int = 0,
) -> InlineKeyboardMarkup:
    rows = _build_numbered_grid_rows(
        items=items,
        page=page,
        item_prefix="users:del_ask",
        page_prefix="users:del_page",
        include_idx_in_callback=False,
    )
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="users:list")])
    rows.append([InlineKeyboardButton(text="🏠 В главное меню", callback_data="menu:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def user_delete_confirm_kb(
    user_id: int,
    back_callback: str = "users:list",
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Да, удалить", callback_data=f"users:del_confirm:{user_id}")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data=back_callback)],
            [InlineKeyboardButton(text="🏠 В главное меню", callback_data="menu:home")],
        ]
    )


def my_users_section_kb(has_users: bool = True) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(text="➕ Добавить нового пользователя", callback_data="my_users:add")],
    ]
    if has_users:
        rows.append([InlineKeyboardButton(text="✏️ Редактировать пользователя", callback_data="my_users:edit_menu")])
        rows.append([InlineKeyboardButton(text="🗑 Удалить пользователя", callback_data="my_users:del_menu")])
    rows.append([InlineKeyboardButton(text="🏠 В главное меню", callback_data="menu:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def my_users_edit_select_kb(
    items: list[tuple[int, int]],
    page: int = 0,
) -> InlineKeyboardMarkup:
    rows = _build_numbered_grid_rows(
        items=items,
        page=page,
        item_prefix="my_users:edit_open",
        page_prefix="my_users:edit_page",
        include_idx_in_callback=False,
    )
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="my_users:list")])
    rows.append([InlineKeyboardButton(text="🏠 В главное меню", callback_data="menu:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def my_user_edit_card_kb(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✏️ Изменить имя", callback_data=f"my_users:edit_name:{user_id}")],
            [InlineKeyboardButton(text="🗑 Удалить пользователя", callback_data=f"my_users:del_ask:{user_id}:card")],
            [InlineKeyboardButton(text="⬅️ К выбору пользователя", callback_data="my_users:edit_menu")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="my_users:list")],
            [InlineKeyboardButton(text="🏠 В главное меню", callback_data="menu:home")],
        ]
    )


def my_user_edit_name_cancel_kb(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Назад к пользователю", callback_data=f"my_users:edit_open:{user_id}")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="my_users:list")],
            [InlineKeyboardButton(text="🏠 В главное меню", callback_data="menu:home")],
        ]
    )


def my_users_delete_kb(
    items: list[tuple[int, int]],
    page: int = 0,
) -> InlineKeyboardMarkup:
    rows = _build_numbered_grid_rows(
        items=items,
        page=page,
        item_prefix="my_users:del_ask",
        page_prefix="my_users:del_page",
        include_idx_in_callback=False,
    )
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="my_users:list")])
    rows.append([InlineKeyboardButton(text="🏠 В главное меню", callback_data="menu:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def my_user_delete_confirm_kb(
    user_id: int,
    back_callback: str = "my_users:list",
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Да, удалить", callback_data=f"my_users:del_confirm:{user_id}")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data=back_callback)],
            [InlineKeyboardButton(text="🏠 В главное меню", callback_data="menu:home")],
        ]
    )


def reminders_section_kb(
    has_reminders: bool,
    can_undo_delete: bool = False,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if can_undo_delete:
        rows.append([InlineKeyboardButton(text="↩️ Отменить удаление", callback_data="rem:undo_delete")])
    if has_reminders:
        rows.append([InlineKeyboardButton(text="✏️ Редактировать напоминания", callback_data="rem:edit_prompt")])
        rows.append([InlineKeyboardButton(text="🗑 Удалить напоминание", callback_data="rem:del_prompt")])
    rows.append([InlineKeyboardButton(text="➕ Создать напоминание", callback_data="menu:create")])
    rows.append([InlineKeyboardButton(text="🏠 В главное меню", callback_data="menu:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def reminders_edit_select_kb(
    items: list[tuple[int, int]],
    total_count: int | None = None,
    page: int = 0,
    item_prefix: str = "rem:open",
    page_prefix: str = "rem:edit_page",
) -> InlineKeyboardMarkup:
    rows = _build_numbered_grid_rows(
        items=items,
        page=page,
        item_prefix=item_prefix,
        page_prefix=page_prefix,
        include_idx_in_callback=True,
    )
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="rem:back_panel")])
    rows.append([InlineKeyboardButton(text="🏠 В главное меню", callback_data="menu:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def reminder_number_prompt_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="rem:back_panel")],
            [InlineKeyboardButton(text="🏠 В главное меню", callback_data="menu:home")],
        ]
    )


def reminder_edit_menu_kb(reminder_id: int, number_label: str = "") -> InlineKeyboardMarkup:
    del_cb = f"del:ask:{reminder_id}:{number_label}" if number_label else f"del:ask:{reminder_id}"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✏️ Изменить текст", callback_data=f"edit:text:{reminder_id}")],
            [InlineKeyboardButton(text="📅 Изменить дату", callback_data=f"edit:date:{reminder_id}")],
            [InlineKeyboardButton(text="⏰ Изменить время", callback_data=f"edit:time:{reminder_id}")],
            [InlineKeyboardButton(text="🔁 Изменить периодичность", callback_data=f"edit:rec:{reminder_id}")],
            [InlineKeyboardButton(text="🗑 Удалить напоминание", callback_data=del_cb)],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="rem:back_panel")],
            [InlineKeyboardButton(text="🏠 В главное меню", callback_data="menu:home")],
        ]
    )


def reminder_delete_confirm_kb(
    reminder_id: int,
    back_callback: str,
    number_label: str = "",
) -> InlineKeyboardMarkup:
    confirm_cb = (
        f"del:confirm:{reminder_id}:{number_label}"
        if number_label
        else f"del:confirm:{reminder_id}"
    )
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Да, удалить", callback_data=confirm_cb)],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data=back_callback)],
            [InlineKeyboardButton(text="🏠 В главное меню", callback_data="menu:home")],
        ]
    )


def edit_text_cancel_kb(reminder_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Назад к напоминанию", callback_data=f"rem:open:{reminder_id}")],
            [InlineKeyboardButton(text="📋 Назад", callback_data="rem:back_panel")],
            [InlineKeyboardButton(text="🏠 В главное меню", callback_data="menu:home")],
        ]
    )


def edit_date_selection_kb(reminder_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Сегодня", callback_data=f"edate:today:{reminder_id}")],
            [InlineKeyboardButton(text="Завтра", callback_data=f"edate:1d:{reminder_id}")],
            [InlineKeyboardButton(text="Через неделю", callback_data=f"edate:1w:{reminder_id}")],
            [InlineKeyboardButton(text="Через месяц", callback_data=f"edate:1m:{reminder_id}")],
            [InlineKeyboardButton(text="Через год", callback_data=f"edate:1y:{reminder_id}")],
            [InlineKeyboardButton(text="📅 Календарь", callback_data=f"edate:custom:{reminder_id}")],
            [InlineKeyboardButton(text="⬅️ Назад к напоминанию", callback_data=f"rem:open:{reminder_id}")],
            [InlineKeyboardButton(text="🏠 В главное меню", callback_data="menu:home")],
        ]
    )


def edit_time_selection_kb(reminder_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⏰ Установить 15:00", callback_data=f"etime:skip:{reminder_id}")],
            [InlineKeyboardButton(text="⬅️ Назад к напоминанию", callback_data=f"rem:open:{reminder_id}")],
            [InlineKeyboardButton(text="🏠 В главное меню", callback_data="menu:home")],
        ]
    )


def edit_recurrence_type_kb(reminder_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="1️⃣ Один раз", callback_data=f"erec:once:{reminder_id}")],
            [InlineKeyboardButton(text="🔁 Повторяющееся", callback_data=f"erec:menu:{reminder_id}")],
            [InlineKeyboardButton(text="⬅️ Назад к напоминанию", callback_data=f"rem:open:{reminder_id}")],
            [InlineKeyboardButton(text="🏠 В главное меню", callback_data="menu:home")],
        ]
    )


def edit_recurrence_period_kb(reminder_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📅 Каждый день", callback_data=f"erec_set:daily:{reminder_id}")],
            [InlineKeyboardButton(text="🗓 Раз в неделю", callback_data=f"erec_set:weekly:{reminder_id}")],
            [InlineKeyboardButton(text="📆 Каждые две недели", callback_data=f"erec_set:biweekly:{reminder_id}")],
            [InlineKeyboardButton(text="🌙 Ежемесячно", callback_data=f"erec_set:monthly:{reminder_id}")],
            [InlineKeyboardButton(text="🎉 Ежегодно", callback_data=f"erec_set:yearly:{reminder_id}")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data=f"edit:rec:{reminder_id}")],
            [InlineKeyboardButton(text="🏠 В главное меню", callback_data="menu:home")],
        ]
    )


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
            [InlineKeyboardButton(text="Через год", callback_data="date:1y")],
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
            [InlineKeyboardButton(text="🔁 Повторяющееся", callback_data="rec:menu")],
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
            [InlineKeyboardButton(text="Каждые две недели", callback_data="rec_set:biweekly")],
            [InlineKeyboardButton(text="Ежемесячно", callback_data="rec_set:monthly")],
            [InlineKeyboardButton(text="Ежегодно", callback_data="rec_set:yearly")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="rec:back_to_type")],
            [InlineKeyboardButton(text="Назад", callback_data="menu:list")],
            [InlineKeyboardButton(text="🏠 В главное меню", callback_data="menu:home")],
        ]
    )


def tz_selection_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="London (UTC+1)", callback_data="tz:60")],
            [InlineKeyboardButton(text="Калининград (UTC+2)", callback_data="tz:120")],
            [InlineKeyboardButton(text="Москва (UTC+3)", callback_data="tz:180")],
            [InlineKeyboardButton(text="Самара (UTC+4)", callback_data="tz:240")],
            [InlineKeyboardButton(text="Магнитогорск (UTC+5)", callback_data="tz:300")],
            [InlineKeyboardButton(text="Омск (UTC+6)", callback_data="tz:360")],
            [InlineKeyboardButton(text="Красноярск (UTC+7)", callback_data="tz:420")],
            [InlineKeyboardButton(text="Иркутск (UTC+8)", callback_data="tz:480")],
            [InlineKeyboardButton(text="Якутск (UTC+9)", callback_data="tz:540")],
            [InlineKeyboardButton(text="Хабаровск (UTC+10)", callback_data="tz:600")],
            [InlineKeyboardButton(text="Магадан (UTC+11)", callback_data="tz:660")],
            [InlineKeyboardButton(text="⬅️ Назад в настройки", callback_data="menu:settings")],
            [InlineKeyboardButton(text="🏠 В главное меню", callback_data="menu:home")],
        ]
    )


def notification_ack_kb(notif_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🔁 Повторить", callback_data=f"notif:repeat:{notif_id}"),
                InlineKeyboardButton(text="⏳ Отложить", callback_data=f"notif:snooze_menu:{notif_id}"),
                InlineKeyboardButton(text="✅ Прочитано", callback_data=f"notif:ack:{notif_id}"),
            ],
        ]
    )


def notification_snooze_kb(notif_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="5 минут", callback_data=f"notif:snooze:5m:{notif_id}")],
            [InlineKeyboardButton(text="30 минут", callback_data=f"notif:snooze:30m:{notif_id}")],
            [InlineKeyboardButton(text="1 час", callback_data=f"notif:snooze:1h:{notif_id}")],
            [InlineKeyboardButton(text="1 день", callback_data=f"notif:snooze:1d:{notif_id}")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data=f"notif:back:{notif_id}")],
        ]
    )
