import calendar
from datetime import date, datetime
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from i18n import (
    DEFAULT_LANG,
    MONTHS_NOMINATIVE,
    MONTHS_SHORT,
    TZ_ABBR_MAPS,
    WEEKDAY_HEADERS as I18N_WEEKDAY_HEADERS,
    get_snooze_label,
    normalize_lang,
    t,
)

RU_MONTH_NAMES: dict[int, str] = MONTHS_NOMINATIVE["ru"]
RU_MONTH_SHORT: dict[int, str] = MONTHS_SHORT["ru"]
WEEKDAY_HEADERS = I18N_WEEKDAY_HEADERS["ru"]

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
    num_rows = 1 if n <= 5 else (2 if n <= 10 else 3)
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
        grid_buttons.append(InlineKeyboardButton(text="⬅️", callback_data=f"{page_prefix}:{page - 1}"))
    for idx, item_id in page_items:
        cb_data = f"{item_prefix}:{item_id}:{idx}" if include_idx_in_callback else f"{item_prefix}:{item_id}"
        grid_buttons.append(InlineKeyboardButton(text=str(idx), callback_data=cb_data))
    if has_next:
        grid_buttons.append(InlineKeyboardButton(text="➡️", callback_data=f"{page_prefix}:{page + 1}"))
    return _distribute_buttons_grid(grid_buttons)


def build_calendar_kb(
    year: int, month: int, today: date,
    nav_prefix: str, ym_prefix: str, pick_prefix: str,
    back_callback: str, plain_home: bool = False,
    lang: str = DEFAULT_LANG,
) -> InlineKeyboardMarkup:
    norm = normalize_lang(lang)
    rows: list[list[InlineKeyboardButton]] = []
    month_title = f"{MONTHS_NOMINATIVE[norm].get(month, '')} {year} >"
    can_go_prev = (year, month) > (today.year, today.month)
    prev_cb = f"{nav_prefix}:{year}:{month}:prev" if can_go_prev else "cal:past_month"
    next_cb = f"{nav_prefix}:{year}:{month}:next"
    ym_cb = f"{ym_prefix}:{year}:{month}"

    rows.append([
        InlineKeyboardButton(text=month_title, callback_data=ym_cb),
        InlineKeyboardButton(text="<", callback_data=prev_cb),
        InlineKeyboardButton(text=">", callback_data=next_cb),
    ])
    rows.append([
        InlineKeyboardButton(text=day_lbl, callback_data="cal:ignore")
        for day_lbl in I18N_WEEKDAY_HEADERS[norm]
    ])

    for week in calendar.monthcalendar(year, month):
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

    rows.append([InlineKeyboardButton(text=t(norm, "btn_back"), callback_data=back_callback)])
    rows.append([InlineKeyboardButton(text=t(norm, "btn_home"), callback_data="menu:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_calendar_ym_kb(
    year: int, current_month: int, today: date,
    year_nav_prefix: str, month_pick_prefix: str, plain_home: bool = False,
    lang: str = DEFAULT_LANG,
) -> InlineKeyboardMarkup:
    norm = normalize_lang(lang)
    rows: list[list[InlineKeyboardButton]] = []
    next_year = year + 1
    month_name = MONTHS_NOMINATIVE[norm].get(current_month, "")
    rows.append([
        InlineKeyboardButton(
            text=t(norm, "cal_year_ahead", month=month_name, year=next_year),
            callback_data=f"{month_pick_prefix}:{next_year}:{current_month}",
        )
    ])

    can_prev_year = year > today.year
    prev_year_cb = f"{year_nav_prefix}:{year}:{current_month}:prev" if can_prev_year else "cal:past_year"
    next_year_cb = f"{year_nav_prefix}:{year}:{current_month}:next"

    rows.append([
        InlineKeyboardButton(text="<", callback_data=prev_year_cb),
        InlineKeyboardButton(
            text=t(norm, "cal_year_lbl", year=year),
            callback_data=f"{month_pick_prefix}:{year}:{max(current_month, today.month) if year == today.year else current_month}",
        ),
        InlineKeyboardButton(text=">", callback_data=next_year_cb),
    ])

    for row_idx in range(4):
        m_row: list[InlineKeyboardButton] = []
        for col_idx in range(1, 4):
            m_num = row_idx * 3 + col_idx
            m_label = MONTHS_SHORT[norm][m_num]
            if (year, m_num) < (today.year, today.month):
                m_row.append(InlineKeyboardButton(text=f"·{m_label}·", callback_data="cal:past_month"))
            elif m_num == current_month:
                m_row.append(InlineKeyboardButton(text=f"[{m_label}]", callback_data=f"{month_pick_prefix}:{year}:{m_num}"))
            else:
                m_row.append(InlineKeyboardButton(text=m_label, callback_data=f"{month_pick_prefix}:{year}:{m_num}"))
        rows.append(m_row)

    back_month = max(current_month, today.month) if year == today.year else current_month
    rows.append([InlineKeyboardButton(text=t(norm, "btn_back"), callback_data=f"{month_pick_prefix}:{year}:{back_month}")])
    rows.append([InlineKeyboardButton(text=t(norm, "btn_home"), callback_data="menu:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_hours_picker_kb(
    target_date: date, user_now: datetime, skip_btn_text: str,
    skip_callback: str, hour_prefix: str, change_date_callback: str | None,
    back_callback: str, plain_style: bool = False,
    lang: str = DEFAULT_LANG,
) -> InlineKeyboardMarkup:
    norm = normalize_lang(lang)
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
        rows.append([InlineKeyboardButton(text=t(norm, "btn_change_date"), callback_data=change_date_callback)])

    rows.append([InlineKeyboardButton(text=t(norm, "btn_back"), callback_data=back_callback)])
    rows.append([InlineKeyboardButton(text=t(norm, "btn_home"), callback_data="menu:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_minutes_drum_kb(
    hour: int, minute: int, target_date: date, user_now: datetime,
    drum_prefix: str, pick_prefix: str, back_to_hours_callback: str,
    back_callback: str, plain_style: bool = False,
    lang: str = DEFAULT_LANG,
) -> InlineKeyboardMarkup:
    norm = normalize_lang(lang)
    rows: list[list[InlineKeyboardButton]] = []
    today = user_now.date()
    now_naive = user_now.replace(tzinfo=None)

    prev_h = (hour - 1) % 24
    next_h = (hour + 1) % 24
    prev_m = (minute - 1) % 60
    next_m = (minute + 1) % 60

    rows.append([
        InlineKeyboardButton(text=t(norm, "drum_hour_up", h=prev_h), callback_data=f"{drum_prefix}:{prev_h}:{minute}"),
        InlineKeyboardButton(text=t(norm, "drum_min_up", m=prev_m), callback_data=f"{drum_prefix}:{hour}:{prev_m}"),
    ])
    rows.append([InlineKeyboardButton(text=t(norm, "drum_pick", h=hour, m=minute), callback_data=f"{pick_prefix}:{hour}:{minute}")])
    rows.append([
        InlineKeyboardButton(text=t(norm, "drum_hour_down", h=next_h), callback_data=f"{drum_prefix}:{next_h}:{minute}"),
        InlineKeyboardButton(text=t(norm, "drum_min_down", m=next_m), callback_data=f"{drum_prefix}:{hour}:{next_m}"),
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

    rows.append([InlineKeyboardButton(text=t(norm, "btn_back_to_hours"), callback_data=back_to_hours_callback)])
    rows.append([InlineKeyboardButton(text=t(norm, "btn_back"), callback_data=back_callback)])
    rows.append([InlineKeyboardButton(text=t(norm, "btn_home"), callback_data="menu:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def main_menu_kb(
    is_admin: bool = False,
    has_user_section: bool = False,
    has_pending_notifications: bool = False,
    create_btn_text: str | None = None,
    webapp_url: str = "",
    lang: str = DEFAULT_LANG,
) -> InlineKeyboardMarkup:
    norm = normalize_lang(lang)
    btn_create = create_btn_text or t(norm, "btn_create_rem")
    rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(text=btn_create, callback_data="menu:create")],
        [InlineKeyboardButton(text=t(norm, "btn_reminders"), callback_data="menu:list")],
    ]
    if has_pending_notifications:
        rows.append([InlineKeyboardButton(text=t(norm, "btn_notifications"), callback_data="notifications:list")])
    if is_admin:
        rows.append([InlineKeyboardButton(text=t(norm, "btn_users"), callback_data="users:list")])
    elif has_user_section:
        rows.append([InlineKeyboardButton(text=t(norm, "btn_users"), callback_data="my_users:list")])
    rows.append([InlineKeyboardButton(text=t(norm, "btn_settings"), callback_data="menu:settings")])
    if not is_admin:
        rows.append([InlineKeyboardButton(text=t(norm, "btn_info"), callback_data="info:main")])
    if webapp_url:
        rows.append([InlineKeyboardButton(text=t(norm, "btn_open_webapp"), web_app=WebAppInfo(url=webapp_url))])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def notifications_section_kb(lang: str = DEFAULT_LANG) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=t(lang, "btn_home"), callback_data="menu:home")]])


def info_menu_kb(lang: str = DEFAULT_LANG) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t(lang, "info_btn_reminders"), callback_data="info:reminders")],
            [InlineKeyboardButton(text=t(lang, "info_btn_notifications"), callback_data="info:notifications")],
            [InlineKeyboardButton(text=t(lang, "info_btn_settings"), callback_data="info:settings")],
            [InlineKeyboardButton(text=t(lang, "info_btn_add_user"), callback_data="info:add_user")],
            [InlineKeyboardButton(text=t(lang, "info_btn_app_mode"), callback_data="info:app_mode")],
            [InlineKeyboardButton(text=t(lang, "info_btn_general"), callback_data="info:general")],
            [InlineKeyboardButton(text=t(lang, "btn_home"), callback_data="menu:home")],
        ]
    )


def info_card_kb(lang: str = DEFAULT_LANG) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t(lang, "btn_back_plain"), callback_data="info:main")],
            [InlineKeyboardButton(text=t(lang, "btn_home"), callback_data="menu:home")],
        ]
    )


def admin_ok_kb(lang: str = DEFAULT_LANG) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=t(lang, "btn_ok"), callback_data="ack_alert")]])


def settings_menu_kb(lang: str = DEFAULT_LANG) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t(lang, "btn_set_time"), callback_data="menu:tz")],
            [InlineKeyboardButton(text=t(lang, "btn_set_lang"), callback_data="menu:lang")],
            [InlineKeyboardButton(text=t(lang, "btn_add_user"), callback_data="settings:add_user")],
            [InlineKeyboardButton(text=t(lang, "btn_home"), callback_data="menu:home")],
        ]
    )


def language_selection_kb(current_lang: str = DEFAULT_LANG) -> InlineKeyboardMarkup:
    norm = normalize_lang(current_lang)
    ru_label = "✅ 🇷🇺 Русский" if norm == "ru" else "🇷🇺 Русский"
    en_label = "✅ 🇬🇧 English" if norm == "en" else "🇬🇧 English"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=ru_label, callback_data="lang:ru"),
                InlineKeyboardButton(text=en_label, callback_data="lang:en"),
            ],
            [InlineKeyboardButton(text=t(norm, "btn_back_to_settings"), callback_data="menu:settings")],
            [InlineKeyboardButton(text=t(norm, "btn_home"), callback_data="menu:home")],
        ]
    )


def users_section_kb(has_users: bool, has_removable_users: bool, lang: str = DEFAULT_LANG) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(text=t(lang, "btn_my_users"), callback_data="users:my_list")],
        [InlineKeyboardButton(text=t(lang, "btn_all_users"), callback_data="users:all_list")],
        [InlineKeyboardButton(text=t(lang, "btn_add_user"), callback_data="users:add")],
    ]
    if has_users:
        rows.append([InlineKeyboardButton(text=t(lang, "btn_edit_user"), callback_data="users:edit_menu")])
    if has_removable_users:
        rows.append([InlineKeyboardButton(text=t(lang, "btn_del_user"), callback_data="users:del_menu")])
    rows.append([InlineKeyboardButton(text=t(lang, "btn_home"), callback_data="menu:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def users_sublist_kb(lang: str = DEFAULT_LANG) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t(lang, "btn_back_plain"), callback_data="users:list")],
            [InlineKeyboardButton(text=t(lang, "btn_home"), callback_data="menu:home")],
        ]
    )


def add_user_cancel_kb(origin: str = "settings", lang: str = DEFAULT_LANG) -> InlineKeyboardMarkup:
    if origin == "users":
        back_btn = InlineKeyboardButton(text=t(lang, "btn_back"), callback_data="users:list")
    elif origin == "my_users":
        back_btn = InlineKeyboardButton(text=t(lang, "btn_back"), callback_data="my_users:list")
    else:
        back_btn = InlineKeyboardButton(text=t(lang, "btn_back_to_settings"), callback_data="menu:settings")
    return InlineKeyboardMarkup(
        inline_keyboard=[[back_btn], [InlineKeyboardButton(text=t(lang, "btn_home"), callback_data="menu:home")]]
    )


def users_cancel_kb(lang: str = DEFAULT_LANG) -> InlineKeyboardMarkup:
    return add_user_cancel_kb(origin="users", lang=lang)


def users_edit_select_kb(items: list[tuple[int, int]], page: int = 0, lang: str = DEFAULT_LANG) -> InlineKeyboardMarkup:
    rows = _build_numbered_grid_rows(items=items, page=page, item_prefix="users:edit_open", page_prefix="users:edit_page", include_idx_in_callback=False)
    rows.append([InlineKeyboardButton(text=t(lang, "btn_back"), callback_data="users:list")])
    rows.append([InlineKeyboardButton(text=t(lang, "btn_home"), callback_data="menu:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def user_edit_card_kb(user_id: int, is_admin: bool, lang: str = DEFAULT_LANG) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(text=t(lang, "btn_edit_user_name"), callback_data=f"users:edit_name:{user_id}")],
    ]
    if not is_admin:
        rows.append([InlineKeyboardButton(text=t(lang, "btn_del_user"), callback_data=f"users:del_ask:{user_id}:card")])
    rows.append([InlineKeyboardButton(text=t(lang, "btn_back_to_user_select"), callback_data="users:edit_menu")])
    rows.append([InlineKeyboardButton(text=t(lang, "btn_to_users_section"), callback_data="users:list")])
    rows.append([InlineKeyboardButton(text=t(lang, "btn_home"), callback_data="menu:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def user_edit_name_cancel_kb(user_id: int, lang: str = DEFAULT_LANG) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t(lang, "btn_back_to_user"), callback_data=f"users:edit_open:{user_id}")],
            [InlineKeyboardButton(text=t(lang, "btn_to_users_section"), callback_data="users:list")],
            [InlineKeyboardButton(text=t(lang, "btn_home"), callback_data="menu:home")],
        ]
    )


def users_delete_kb(items: list[tuple[int, int]], page: int = 0, lang: str = DEFAULT_LANG) -> InlineKeyboardMarkup:
    rows = _build_numbered_grid_rows(items=items, page=page, item_prefix="users:del_ask", page_prefix="users:del_page", include_idx_in_callback=False)
    rows.append([InlineKeyboardButton(text=t(lang, "btn_back"), callback_data="users:list")])
    rows.append([InlineKeyboardButton(text=t(lang, "btn_home"), callback_data="menu:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def user_delete_confirm_kb(user_id: int, back_callback: str = "users:list", lang: str = DEFAULT_LANG) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t(lang, "btn_yes_delete"), callback_data=f"users:del_confirm:{user_id}")],
            [InlineKeyboardButton(text=t(lang, "btn_back"), callback_data=back_callback)],
            [InlineKeyboardButton(text=t(lang, "btn_home"), callback_data="menu:home")],
        ]
    )


def my_users_section_kb(has_users: bool = True, lang: str = DEFAULT_LANG) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [[InlineKeyboardButton(text=t(lang, "btn_add_user"), callback_data="my_users:add")]]
    if has_users:
        rows.append([InlineKeyboardButton(text=t(lang, "btn_edit_user"), callback_data="my_users:edit_menu")])
        rows.append([InlineKeyboardButton(text=t(lang, "btn_del_user"), callback_data="my_users:del_menu")])
    rows.append([InlineKeyboardButton(text=t(lang, "btn_home"), callback_data="menu:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def my_users_edit_select_kb(items: list[tuple[int, int]], page: int = 0, lang: str = DEFAULT_LANG) -> InlineKeyboardMarkup:
    rows = _build_numbered_grid_rows(items=items, page=page, item_prefix="my_users:edit_open", page_prefix="my_users:edit_page", include_idx_in_callback=False)
    rows.append([InlineKeyboardButton(text=t(lang, "btn_back"), callback_data="my_users:list")])
    rows.append([InlineKeyboardButton(text=t(lang, "btn_home"), callback_data="menu:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def my_user_edit_card_kb(user_id: int, lang: str = DEFAULT_LANG) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t(lang, "btn_edit_user_name"), callback_data=f"my_users:edit_name:{user_id}")],
            [InlineKeyboardButton(text=t(lang, "btn_del_user"), callback_data=f"my_users:del_ask:{user_id}:card")],
            [InlineKeyboardButton(text=t(lang, "btn_back_to_user_select"), callback_data="my_users:edit_menu")],
            [InlineKeyboardButton(text=t(lang, "btn_back"), callback_data="my_users:list")],
            [InlineKeyboardButton(text=t(lang, "btn_home"), callback_data="menu:home")],
        ]
    )


def my_user_edit_name_cancel_kb(user_id: int, lang: str = DEFAULT_LANG) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t(lang, "btn_back_to_user"), callback_data=f"my_users:edit_open:{user_id}")],
            [InlineKeyboardButton(text=t(lang, "btn_back"), callback_data="my_users:list")],
            [InlineKeyboardButton(text=t(lang, "btn_home"), callback_data="menu:home")],
        ]
    )


def my_users_delete_kb(items: list[tuple[int, int]], page: int = 0, lang: str = DEFAULT_LANG) -> InlineKeyboardMarkup:
    rows = _build_numbered_grid_rows(items=items, page=page, item_prefix="my_users:del_ask", page_prefix="my_users:del_page", include_idx_in_callback=False)
    rows.append([InlineKeyboardButton(text=t(lang, "btn_back"), callback_data="my_users:list")])
    rows.append([InlineKeyboardButton(text=t(lang, "btn_home"), callback_data="menu:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def my_user_delete_confirm_kb(user_id: int, back_callback: str = "my_users:list", lang: str = DEFAULT_LANG) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t(lang, "btn_yes_delete"), callback_data=f"my_users:del_confirm:{user_id}")],
            [InlineKeyboardButton(text=t(lang, "btn_back"), callback_data=back_callback)],
            [InlineKeyboardButton(text=t(lang, "btn_home"), callback_data="menu:home")],
        ]
    )


def reminders_section_kb(has_reminders: bool, can_undo_delete: bool = False, lang: str = DEFAULT_LANG) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if can_undo_delete:
        rows.append([InlineKeyboardButton(text=t(lang, "btn_undo_delete"), callback_data="rem:undo_delete")])
    if has_reminders:
        rows.append([InlineKeyboardButton(text=t(lang, "btn_edit_rems"), callback_data="rem:edit_prompt")])
        rows.append([InlineKeyboardButton(text=t(lang, "btn_del_rem"), callback_data="rem:del_prompt")])
    rows.append([InlineKeyboardButton(text=t(lang, "btn_create_rem"), callback_data="menu:create")])
    rows.append([InlineKeyboardButton(text=t(lang, "btn_home"), callback_data="menu:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def reminders_edit_select_kb(
    items: list[tuple[int, int]], total_count: int | None = None, page: int = 0,
    item_prefix: str = "rem:open", page_prefix: str = "rem:edit_page", lang: str = DEFAULT_LANG,
) -> InlineKeyboardMarkup:
    rows = _build_numbered_grid_rows(items=items, page=page, item_prefix=item_prefix, page_prefix=page_prefix, include_idx_in_callback=True)
    rows.append([InlineKeyboardButton(text=t(lang, "btn_back"), callback_data="rem:back_panel")])
    rows.append([InlineKeyboardButton(text=t(lang, "btn_home"), callback_data="menu:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def reminder_number_prompt_kb(lang: str = DEFAULT_LANG) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t(lang, "btn_back"), callback_data="rem:back_panel")],
            [InlineKeyboardButton(text=t(lang, "btn_home"), callback_data="menu:home")],
        ]
    )


def reminder_edit_menu_kb(reminder_id: int, number_label: str = "", back_text: str | None = None, lang: str = DEFAULT_LANG) -> InlineKeyboardMarkup:
    del_cb = f"del:ask:{reminder_id}:{number_label}" if number_label else f"del:ask:{reminder_id}"
    resolved_back = back_text or t(lang, "btn_back")
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t(lang, "btn_edit_text"), callback_data=f"edit:text:{reminder_id}")],
            [InlineKeyboardButton(text=t(lang, "btn_edit_date"), callback_data=f"edit:date:{reminder_id}")],
            [InlineKeyboardButton(text=t(lang, "btn_edit_time"), callback_data=f"edit:time:{reminder_id}")],
            [InlineKeyboardButton(text=t(lang, "btn_edit_rec"), callback_data=f"edit:rec:{reminder_id}")],
            [InlineKeyboardButton(text=t(lang, "btn_del_rem"), callback_data=del_cb)],
            [InlineKeyboardButton(text=resolved_back, callback_data="rem:back_panel")],
            [InlineKeyboardButton(text=t(lang, "btn_home"), callback_data="menu:home")],
        ]
    )


def reminder_delete_confirm_kb(reminder_id: int, back_callback: str, number_label: str = "", lang: str = DEFAULT_LANG) -> InlineKeyboardMarkup:
    confirm_cb = f"del:confirm:{reminder_id}:{number_label}" if number_label else f"del:confirm:{reminder_id}"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t(lang, "btn_yes_delete"), callback_data=confirm_cb)],
            [InlineKeyboardButton(text=t(lang, "btn_back"), callback_data=back_callback)],
            [InlineKeyboardButton(text=t(lang, "btn_home"), callback_data="menu:home")],
        ]
    )


def edit_text_cancel_kb(reminder_id: int, lang: str = DEFAULT_LANG) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t(lang, "btn_back_to_rem"), callback_data=f"rem:open:{reminder_id}")],
            [InlineKeyboardButton(text=f"📋 {t(lang, 'btn_back_plain')}", callback_data="rem:back_panel")],
            [InlineKeyboardButton(text=t(lang, "btn_home"), callback_data="menu:home")],
        ]
    )


def edit_date_selection_kb(reminder_id: int, lang: str = DEFAULT_LANG) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t(lang, "btn_today"), callback_data=f"edate:today:{reminder_id}")],
            [InlineKeyboardButton(text=t(lang, "btn_tomorrow"), callback_data=f"edate:1d:{reminder_id}")],
            [InlineKeyboardButton(text=t(lang, "btn_in_week"), callback_data=f"edate:1w:{reminder_id}")],
            [InlineKeyboardButton(text=t(lang, "btn_in_month"), callback_data=f"edate:1m:{reminder_id}")],
            [InlineKeyboardButton(text=t(lang, "btn_in_year"), callback_data=f"edate:1y:{reminder_id}")],
            [InlineKeyboardButton(text=t(lang, "btn_calendar"), callback_data=f"edate:custom:{reminder_id}")],
            [InlineKeyboardButton(text=t(lang, "btn_back_to_rem"), callback_data=f"rem:open:{reminder_id}")],
            [InlineKeyboardButton(text=t(lang, "btn_home"), callback_data="menu:home")],
        ]
    )


def edit_time_selection_kb(reminder_id: int, lang: str = DEFAULT_LANG) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t(lang, "btn_set_1500"), callback_data=f"etime:skip:{reminder_id}")],
            [InlineKeyboardButton(text=t(lang, "btn_back_to_rem"), callback_data=f"rem:open:{reminder_id}")],
            [InlineKeyboardButton(text=t(lang, "btn_home"), callback_data="menu:home")],
        ]
    )


def edit_recurrence_type_kb(reminder_id: int, lang: str = DEFAULT_LANG) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t(lang, "btn_once_ico"), callback_data=f"erec:once:{reminder_id}")],
            [InlineKeyboardButton(text=t(lang, "btn_recurring"), callback_data=f"erec:menu:{reminder_id}")],
            [InlineKeyboardButton(text=t(lang, "btn_back_to_rem"), callback_data=f"rem:open:{reminder_id}")],
            [InlineKeyboardButton(text=t(lang, "btn_home"), callback_data="menu:home")],
        ]
    )


def edit_recurrence_period_kb(reminder_id: int, lang: str = DEFAULT_LANG) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t(lang, "btn_rec_daily_ico"), callback_data=f"erec_set:daily:{reminder_id}")],
            [InlineKeyboardButton(text=t(lang, "btn_rec_weekly_ico"), callback_data=f"erec_set:weekly:{reminder_id}")],
            [InlineKeyboardButton(text=t(lang, "btn_rec_biweekly_ico"), callback_data=f"erec_set:biweekly:{reminder_id}")],
            [InlineKeyboardButton(text=t(lang, "btn_rec_monthly_ico"), callback_data=f"erec_set:monthly:{reminder_id}")],
            [InlineKeyboardButton(text=t(lang, "btn_rec_yearly_ico"), callback_data=f"erec_set:yearly:{reminder_id}")],
            [InlineKeyboardButton(text=t(lang, "btn_back"), callback_data=f"edit:rec:{reminder_id}")],
            [InlineKeyboardButton(text=t(lang, "btn_home"), callback_data="menu:home")],
        ]
    )


def cancel_to_menu_kb(lang: str = DEFAULT_LANG) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t(lang, "btn_back_plain"), callback_data="menu:list")],
            [InlineKeyboardButton(text=t(lang, "btn_home"), callback_data="menu:home")],
        ]
    )


def date_selection_kb(lang: str = DEFAULT_LANG) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t(lang, "btn_today"), callback_data="date:today")],
            [InlineKeyboardButton(text=t(lang, "btn_tomorrow"), callback_data="date:1d")],
            [InlineKeyboardButton(text=t(lang, "btn_in_week"), callback_data="date:1w")],
            [InlineKeyboardButton(text=t(lang, "btn_in_month"), callback_data="date:1m")],
            [InlineKeyboardButton(text=t(lang, "btn_in_year"), callback_data="date:1y")],
            [InlineKeyboardButton(text=t(lang, "btn_calendar"), callback_data="date:custom")],
            [InlineKeyboardButton(text=t(lang, "btn_back_plain"), callback_data="menu:list")],
            [InlineKeyboardButton(text=t(lang, "btn_home"), callback_data="menu:home")],
        ]
    )


def time_selection_kb(skip_btn_text: str | None = None, lang: str = DEFAULT_LANG) -> InlineKeyboardMarkup:
    resolved_skip = skip_btn_text or t(lang, "skip_today_15")
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=resolved_skip, callback_data="time:skip")],
            [InlineKeyboardButton(text=t(lang, "btn_change_date_short"), callback_data="time:back_to_date")],
            [InlineKeyboardButton(text=t(lang, "btn_back_plain"), callback_data="menu:list")],
            [InlineKeyboardButton(text=t(lang, "btn_home"), callback_data="menu:home")],
        ]
    )


def recurrence_type_kb(lang: str = DEFAULT_LANG) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t(lang, "btn_once"), callback_data="rec:once")],
            [InlineKeyboardButton(text=t(lang, "btn_recurring"), callback_data="rec:menu")],
            [InlineKeyboardButton(text=t(lang, "btn_change_time_short"), callback_data="rec:back_to_time")],
            [InlineKeyboardButton(text=t(lang, "btn_back_plain"), callback_data="menu:list")],
            [InlineKeyboardButton(text=t(lang, "btn_home"), callback_data="menu:home")],
        ]
    )


def recurrence_period_kb(lang: str = DEFAULT_LANG) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t(lang, "btn_rec_daily"), callback_data="rec_set:daily")],
            [InlineKeyboardButton(text=t(lang, "btn_rec_weekly"), callback_data="rec_set:weekly")],
            [InlineKeyboardButton(text=t(lang, "btn_rec_biweekly"), callback_data="rec_set:biweekly")],
            [InlineKeyboardButton(text=t(lang, "btn_rec_monthly"), callback_data="rec_set:monthly")],
            [InlineKeyboardButton(text=t(lang, "btn_rec_yearly"), callback_data="rec_set:yearly")],
            [InlineKeyboardButton(text=t(lang, "btn_back"), callback_data="rec:back_to_type")],
            [InlineKeyboardButton(text=t(lang, "btn_back_plain"), callback_data="menu:list")],
            [InlineKeyboardButton(text=t(lang, "btn_home"), callback_data="menu:home")],
        ]
    )


def tz_selection_kb(lang: str = DEFAULT_LANG) -> InlineKeyboardMarkup:
    norm = normalize_lang(lang)
    rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(text=label, callback_data=f"tz:{mins}")]
        for mins, label in sorted(TZ_ABBR_MAPS[norm].items())
    ]
    rows.append([InlineKeyboardButton(text=t(norm, "btn_back_to_settings"), callback_data="menu:settings")])
    rows.append([InlineKeyboardButton(text=t(norm, "btn_home"), callback_data="menu:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def notification_ack_kb(notif_id: int, lang: str = DEFAULT_LANG) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=t(lang, "btn_notif_repeat"), callback_data=f"notif:repeat:{notif_id}"),
                InlineKeyboardButton(text=t(lang, "btn_notif_snooze"), callback_data=f"notif:snooze_menu:{notif_id}"),
                InlineKeyboardButton(text=t(lang, "btn_notif_ack"), callback_data=f"notif:ack:{notif_id}"),
            ],
        ]
    )


def notification_snooze_kb(notif_id: int, lang: str = DEFAULT_LANG) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=get_snooze_label("5m", lang), callback_data=f"notif:snooze:5m:{notif_id}")],
            [InlineKeyboardButton(text=get_snooze_label("30m", lang), callback_data=f"notif:snooze:30m:{notif_id}")],
            [InlineKeyboardButton(text=get_snooze_label("1h", lang), callback_data=f"notif:snooze:1h:{notif_id}")],
            [InlineKeyboardButton(text=get_snooze_label("1d", lang), callback_data=f"notif:snooze:1d:{notif_id}")],
            [InlineKeyboardButton(text=t(lang, "btn_back"), callback_data=f"notif:back:{notif_id}")],
        ]
    )
