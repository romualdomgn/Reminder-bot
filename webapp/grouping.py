import calendar
import html
import re
from datetime import date, datetime, time, timedelta

from database import format_recurrence_label

RU_MONTHS_GENITIVE: dict[int, str] = {
    1: "января", 2: "февраля", 3: "марта", 4: "апреля",
    5: "мая", 6: "июня", 7: "июля", 8: "августа",
    9: "сентября", 10: "октября", 11: "ноября", 12: "декабря",
}

RU_WEEKDAYS: dict[int, str] = {
    0: "понедельник", 1: "вторник", 2: "среда", 3: "четверг",
    4: "пятница", 5: "суббота", 6: "воскресенье",
}

_HTML_TAG_RE = re.compile(r"<[^>]+>")


def strip_html_for_ui(raw_text: str) -> str:
    return html.unescape(_HTML_TAG_RE.sub("", raw_text or "")).strip()


def escape_for_bot_html(plain_text: str) -> str:
    clean = plain_text.strip()
    if len(clean) > 1000:
        clean = clean[:997] + "..."
    return html.escape(clean)


def add_months(src_date: date, months: int) -> date:
    total = (src_date.year * 12 + (src_date.month - 1)) + months
    year, month_zero = divmod(total, 12)
    month = month_zero + 1
    max_day = calendar.monthrange(year, month)[1]
    return date(year, month, min(src_date.day, max_day))


def format_date_with_weekday(target_date: date) -> str:
    return f"{target_date.strftime('%d.%m.%Y')}, {RU_WEEKDAYS[target_date.weekday()]}"


def _format_header_day_ru(target_date: date) -> str:
    return (
        f"{RU_WEEKDAYS[target_date.weekday()]}, "
        f"{target_date.day} {RU_MONTHS_GENITIVE[target_date.month]}"
    )


def get_group_header(
    target_date: date,
    today: date,
    d_1m: date,
    d_3m: date,
    d_6m: date,
    d_12m: date,
    has_named_groups: bool,
) -> str | None:
    days_diff = (target_date - today).days
    if days_diff < 0:
        return None
    if days_diff == 0:
        return f"Сегодня, {_format_header_day_ru(target_date)} ⏰"
    if days_diff == 1:
        return f"Завтра, {_format_header_day_ru(target_date)} 🕰"
    if days_diff == 2:
        return f"Послезавтра, {_format_header_day_ru(target_date)} 🕑"
    if 3 <= days_diff < 7:
        return "Совсем скоро ⌛️"
    if 7 <= days_diff < 14:
        return "Через неделю 📅"
    if target_date >= d_12m:
        return "Через год"
    if target_date >= d_6m:
        return "Через полгода"
    if d_1m <= target_date < d_3m:
        return "Через месяц"
    if has_named_groups:
        return "В скором будущем ⏳"
    return None


def build_grouped_reminders(reminders: list, user_now: datetime, offset_mins: int) -> list[dict]:
    today = user_now.date()
    d_1m = add_months(today, 1)
    d_3m = add_months(today, 3)
    d_6m = add_months(today, 6)
    d_12m = add_months(today, 12)
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
        header = get_group_header(td, today, d_1m, d_3m, d_6m, d_12m, has_named)
        if current_group is None or current_group["title"] != header:
            current_group = {"title": header, "items": []}
            groups.append(current_group)

        days_diff = (td - today).days
        time_str = local_dt.strftime("%H:%M")
        dt_label = (
            f"В {time_str}"
            if 0 <= days_diff <= 2
            else f"{format_date_with_weekday(td)}, в {time_str}"
        )
        rec_label = format_recurrence_label(r.recurrence) if r.recurrence != "once" else ""

        current_group["items"].append({
            "id": r.id,
            "num": idx,
            "text": strip_html_for_ui(r.text),
            "date": td.isoformat(),
            "time": time_str,
            "dt_label": dt_label,
            "recurrence": r.recurrence,
            "recurrence_label": rec_label,
        })

    return groups


def compute_quick_time(user_now: datetime, target_date: date) -> tuple[str, str]:
    today = user_now.date()
    now_naive = user_now.replace(tzinfo=None)
    if target_date == today and (now_naive.hour, now_naive.minute) > (14, 30):
        rounded = now_naive.replace(minute=0, second=0, microsecond=0) + timedelta(hours=2)
        return rounded.date().isoformat(), rounded.strftime("%H:%M")
    return target_date.isoformat(), time(15, 0).strftime("%H:%M")
