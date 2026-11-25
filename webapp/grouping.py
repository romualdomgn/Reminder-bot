import calendar
from datetime import date, datetime, time, timedelta

from database import format_recurrence_label
from i18n import (
    DEFAULT_LANG,
    MONTHS_GENITIVE,
    WEEKDAYS,
    format_date_with_weekday as _i18n_format_date_with_weekday,
    format_header_day,
    t,
)
from .html_sanitizer import sanitize_telegram_html, strip_html_for_ui

RU_MONTHS_GENITIVE: dict[int, str] = MONTHS_GENITIVE["ru"]
RU_WEEKDAYS: dict[int, str] = WEEKDAYS["ru"]


def add_months(src_date: date, months: int) -> date:
    total = (src_date.year * 12 + (src_date.month - 1)) + months
    year, month_zero = divmod(total, 12)
    month = month_zero + 1
    max_day = calendar.monthrange(year, month)[1]
    return date(year, month, min(src_date.day, max_day))


def format_date_with_weekday(target_date: date, lang: str = DEFAULT_LANG) -> str:
    return _i18n_format_date_with_weekday(target_date, lang=lang)


def get_group_header(
    target_date: date, today: date, d_1m: date, d_3m: date, d_6m: date, d_12m: date,
    has_named_groups: bool, lang: str = DEFAULT_LANG,
) -> str | None:
    days_diff = (target_date - today).days
    if days_diff < 0:
        return None
    if days_diff == 0:
        return t(lang, "grp_today", day=format_header_day(target_date, lang))
    if days_diff == 1:
        return t(lang, "grp_tomorrow", day=format_header_day(target_date, lang))
    if days_diff == 2:
        return t(lang, "grp_day_after", day=format_header_day(target_date, lang))
    if 3 <= days_diff < 7:
        return t(lang, "grp_very_soon")
    if 7 <= days_diff < 14:
        return t(lang, "grp_in_week")
    if target_date >= d_12m:
        return t(lang, "grp_in_year")
    if target_date >= d_6m:
        return t(lang, "grp_in_half_year")
    if d_1m <= target_date < d_3m:
        return t(lang, "grp_in_month")
    if has_named_groups:
        return t(lang, "grp_near_future")
    return None


def build_grouped_reminders(reminders: list, user_now: datetime, offset_mins: int, lang: str = DEFAULT_LANG) -> list[dict]:
    today = user_now.date()
    d_1m, d_3m, d_6m, d_12m = add_months(today, 1), add_months(today, 3), add_months(today, 6), add_months(today, 12)
    delta = timedelta(minutes=offset_mins)
    prepared: list[tuple[int, object, datetime]] = []
    has_named = False
    for idx, r in enumerate(reminders, start=1):
        local_dt = r.remind_at + delta
        td = local_dt.date()
        days_diff = (td - today).days
        if 0 <= days_diff < 14 or (d_1m <= td < d_3m) or td >= d_6m:
            has_named = True
        prepared.append((idx, r, local_dt))

    groups: list[dict] = []
    current_group: dict | None = None
    for idx, r, local_dt in prepared:
        td = local_dt.date()
        header = get_group_header(td, today, d_1m, d_3m, d_6m, d_12m, has_named, lang=lang)
        if current_group is None or current_group["title"] != header:
            current_group = {"title": header, "items": []}
            groups.append(current_group)
        days_diff = (td - today).days
        time_str = local_dt.strftime("%H:%M")
        dt_label = t(lang, "rem_at_time", time=time_str) if 0 <= days_diff <= 2 else t(lang, "rem_date_at_time", date=format_date_with_weekday(td, lang=lang), time=time_str)
        rec_label = format_recurrence_label(r.recurrence, lang=lang) if r.recurrence != "once" else ""
        current_group["items"].append({
            "id": r.id, "num": idx, "text": strip_html_for_ui(r.text), "text_html": sanitize_telegram_html(r.text),
            "date": td.isoformat(), "time": time_str, "dt_label": dt_label, "recurrence": r.recurrence, "recurrence_label": rec_label,
        })
    return groups


def compute_quick_time(user_now: datetime, target_date: date) -> tuple[str, str]:
    today = user_now.date()
    now_naive = user_now.replace(tzinfo=None)
    if target_date == today and (now_naive.hour, now_naive.minute) > (14, 30):
        rounded = now_naive.replace(minute=0, second=0, microsecond=0) + timedelta(hours=2)
        return rounded.date().isoformat(), rounded.strftime("%H:%M")
    return target_date.isoformat(), time(15, 0).strftime("%H:%M")
