from datetime import datetime, date, time, timedelta
from aiogram import Router, Bot, F
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery

from database import (
    add_tracked_messages_batch,
    create_reminder,
    get_user_language,
    get_user_now,
    format_tz_label,
    format_recurrence_label,
    set_panel_message_id,
    pop_all_window_messages,
)
from i18n import (
    DEFAULT_LANG,
    format_created_reminder_dt as _i18n_format_created_reminder_dt,
    t,
)
from keyboards import (
    build_calendar_kb,
    build_calendar_ym_kb,
    build_hours_picker_kb,
    build_minutes_drum_kb,
    cancel_to_menu_kb,
    recurrence_type_kb,
    recurrence_period_kb,
)
from .states import ReminderFSM
from .common import (
    add_one_month,
    add_one_year,
    step_year_month,
    format_date_text_ru,
    format_date_with_weekday,
    parse_user_date,
    parse_user_time,
    extract_message_text,
    safe_delete_message,
    safe_delete_messages_batch,
    safe_answer_callback,
    render_panel,
    build_home_text,
    start_date_selection,
    get_user_main_menu_kb,
)

router = Router()

VALID_RECURRING_PERIODS = {"daily", "weekly", "biweekly", "monthly", "yearly"}


async def _handle_expired_create_session(
    bot: Bot, user_id: int, state: FSMContext, callback: CallbackQuery | None = None,
) -> None:
    lang = await get_user_language(user_id)
    await state.clear()
    if callback is not None:
        await safe_answer_callback(callback, t(lang, "create_expired_cb"), show_alert=False)
    home_text = await build_home_text(user_id, notice=t(lang, "create_expired_notice"), lang=lang)
    await render_panel(bot=bot, user_id=user_id, text=home_text, reply_markup=await get_user_main_menu_kb(user_id, lang=lang))


async def _ensure_create_date_session(bot: Bot, callback: CallbackQuery, state: FSMContext) -> bool:
    current_state = await state.get_state()
    data = await state.get_data()
    if not (data.get("reminder_text") or "").strip():
        await _handle_expired_create_session(bot, callback.from_user.id, state, callback)
        return False
    if current_state not in (ReminderFSM.waiting_for_date.state, ReminderFSM.waiting_for_custom_date.state):
        await safe_answer_callback(callback)
        return False
    return True


def format_created_reminder_dt(local_dt: datetime, today: date, lang: str = DEFAULT_LANG) -> str:
    return _i18n_format_created_reminder_dt(local_dt, today, lang=lang)


def compute_skip_time_button(
    user_now: datetime, target_date: date, date_choice_type: str, lang: str = DEFAULT_LANG,
) -> tuple[date, time, str]:
    today = user_now.date()
    now_naive = user_now.replace(tzinfo=None)

    if date_choice_type == "today":
        if (now_naive.hour, now_naive.minute) <= (14, 30):
            return target_date, time(15, 0), t(lang, "skip_today_15")
        rounded_dt = now_naive.replace(minute=0, second=0, microsecond=0) + timedelta(hours=2)
        if rounded_dt.date() == today:
            return rounded_dt.date(), rounded_dt.time(), t(lang, "skip_today_at", time=rounded_dt.strftime("%H:%M"))
        return rounded_dt.date(), rounded_dt.time(), t(lang, "skip_tomorrow_at", time=rounded_dt.strftime("%H:%M"))
    if date_choice_type == "1d":
        return target_date, time(15, 0), t(lang, "skip_tomorrow_15")
    if date_choice_type == "1w":
        return target_date, time(15, 0), t(lang, "skip_week_15")
    if date_choice_type == "1m":
        return target_date, time(15, 0), t(lang, "skip_month_15")
    if date_choice_type == "1y":
        return target_date, time(15, 0), t(lang, "skip_year_15")

    if target_date == today and (now_naive.hour, now_naive.minute) > (14, 30):
        rounded_dt = now_naive.replace(minute=0, second=0, microsecond=0) + timedelta(hours=2)
        date_text = format_date_text_ru(rounded_dt.date(), today.year, lang=lang)
        return rounded_dt.date(), rounded_dt.time(), t(lang, "skip_date_at", date=date_text, time=rounded_dt.strftime("%H:%M"))

    date_text = format_date_text_ru(target_date, today.year, lang=lang)
    return target_date, time(15, 0), t(lang, "skip_date_at", date=date_text, time="15:00")


def default_minute_for_hour(user_now: datetime, target_date: date, hour: int) -> int:
    today = user_now.date()
    now_naive = user_now.replace(tzinfo=None)
    if target_date == today and hour == now_naive.hour:
        return min(((now_naive.minute // 5) + 1) * 5, 59)
    return 0


@router.callback_query(F.data == "cal:ignore")
async def cb_calendar_ignore(callback: CallbackQuery) -> None:
    await safe_answer_callback(callback)


@router.callback_query(F.data == "cal:past")
async def cb_calendar_past(callback: CallbackQuery) -> None:
    await safe_answer_callback(callback, t(await get_user_language(callback.from_user.id), "cal_past_date"), show_alert=False)


@router.callback_query(F.data == "cal:past_month")
async def cb_calendar_past_month(callback: CallbackQuery) -> None:
    await safe_answer_callback(callback, t(await get_user_language(callback.from_user.id), "cal_past_month"), show_alert=False)


@router.callback_query(F.data == "cal:past_year")
async def cb_calendar_past_year(callback: CallbackQuery) -> None:
    await safe_answer_callback(callback, t(await get_user_language(callback.from_user.id), "cal_past_year"), show_alert=False)


@router.callback_query(F.data == "cal:past_time")
async def cb_calendar_past_time(callback: CallbackQuery) -> None:
    await safe_answer_callback(callback, t(await get_user_language(callback.from_user.id), "cal_past_time"), show_alert=False)


@router.message(F.forward_origin | F.forward_date)
async def handle_forwarded_message(message: Message, state: FSMContext, bot: Bot) -> None:
    await safe_delete_message(bot, message.chat.id, message.message_id)
    uid = message.from_user.id
    lang = await get_user_language(uid)
    reminder_text = extract_message_text(message, lang=lang)
    if not reminder_text:
        return
    await state.clear()
    await start_date_selection(bot=bot, user_id=uid, state=state, reminder_text=reminder_text, lang=lang)


@router.callback_query(F.data == "menu:create")
async def cb_menu_create(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await safe_answer_callback(callback)
    await state.clear()
    await state.set_state(ReminderFSM.waiting_for_text)
    uid = callback.from_user.id
    lang = await get_user_language(uid)

    old_ids = await pop_all_window_messages(uid)
    new_tracked_ids: list[int] = []
    sent_ok = False
    try:
        msg1 = await bot.send_message(chat_id=uid, text=t(lang, "create_step1_title"), disable_notification=True)
        new_tracked_ids.append(msg1.message_id)
        msg2 = await bot.send_message(
            chat_id=uid, text=t(lang, "create_step1_prompt"), reply_markup=cancel_to_menu_kb(lang=lang), disable_notification=True,
        )
        await set_panel_message_id(uid, msg2.message_id)
        sent_ok = True
    finally:
        if new_tracked_ids:
            await add_tracked_messages_batch(uid, new_tracked_ids)
        if old_ids:
            if sent_ok:
                await safe_delete_messages_batch(bot, uid, old_ids)
            else:
                await add_tracked_messages_batch(uid, old_ids)


@router.message(ReminderFSM.waiting_for_text)
async def process_reminder_text(message: Message, state: FSMContext, bot: Bot) -> None:
    await safe_delete_message(bot, message.chat.id, message.message_id)
    uid = message.from_user.id
    lang = await get_user_language(uid)
    reminder_text = extract_message_text(message, lang=lang)
    if not reminder_text:
        return
    await start_date_selection(bot=bot, user_id=uid, state=state, reminder_text=reminder_text, lang=lang)


async def prompt_for_time(bot: Bot, user_id: int, state: FSMContext, error_msg: str = "") -> None:
    data = await state.get_data()
    reminder_text = (data.get("reminder_text") or "").strip()
    target_date_iso = data.get("target_date")
    if not reminder_text or not target_date_iso:
        await _handle_expired_create_session(bot, user_id, state)
        return
    try:
        target_date = date.fromisoformat(target_date_iso)
    except ValueError:
        await _handle_expired_create_session(bot, user_id, state)
        return

    lang = await get_user_language(user_id)
    user_now, _ = await get_user_now(user_id)
    _, _, skip_btn_text = compute_skip_time_button(user_now, target_date, data.get("date_choice_type", "custom"), lang=lang)
    err_block = f"⚠️ <b>{error_msg}</b>\n\n" if error_msg else ""
    text = t(lang, "create_hour_prompt", text=reminder_text, date=format_date_with_weekday(target_date, lang=lang), err_block=err_block, skip=skip_btn_text)
    kb = build_hours_picker_kb(
        target_date=target_date, user_now=user_now, skip_btn_text=skip_btn_text, skip_callback="time:skip",
        hour_prefix="time:hour", change_date_callback="time:back_to_date", back_callback="menu:list", lang=lang,
    )
    await render_panel(bot=bot, user_id=user_id, text=text, reply_markup=kb)


async def prompt_for_minutes_drum(
    bot: Bot, user_id: int, state: FSMContext, hour: int, minute: int, error_msg: str = "",
) -> None:
    data = await state.get_data()
    reminder_text = (data.get("reminder_text") or "").strip()
    target_date_iso = data.get("target_date")
    if not reminder_text or not target_date_iso:
        await _handle_expired_create_session(bot, user_id, state)
        return
    try:
        target_date = date.fromisoformat(target_date_iso)
    except ValueError:
        await _handle_expired_create_session(bot, user_id, state)
        return

    lang = await get_user_language(user_id)
    user_now, _ = await get_user_now(user_id)
    err_block = f"⚠️ <b>{error_msg}</b>\n\n" if error_msg else ""
    text = t(lang, "create_min_prompt", text=reminder_text, date=format_date_with_weekday(target_date, lang=lang), h=hour, m=minute, err_block=err_block)
    kb = build_minutes_drum_kb(
        hour=hour, minute=minute, target_date=target_date, user_now=user_now, drum_prefix="time:drum",
        pick_prefix="time:pick", back_to_hours_callback="time:back_to_hours", back_callback="menu:list", lang=lang,
    )
    await render_panel(bot=bot, user_id=user_id, text=text, reply_markup=kb)


@router.callback_query(ReminderFSM.waiting_for_time, F.data.startswith("time:hour:"))
async def cb_time_pick_hour(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    parts = callback.data.split(":")
    if len(parts) < 3 or not parts[2].isdigit():
        await safe_answer_callback(callback)
        return
    hour = int(parts[2])
    if not (0 <= hour <= 23):
        await safe_answer_callback(callback)
        return
    data = await state.get_data()
    target_date_iso = data.get("target_date")
    if not (data.get("reminder_text") or "").strip() or not target_date_iso:
        await _handle_expired_create_session(bot, callback.from_user.id, state, callback)
        return
    await safe_answer_callback(callback)
    target_date = date.fromisoformat(target_date_iso)
    user_now, _ = await get_user_now(callback.from_user.id)
    await prompt_for_minutes_drum(bot, callback.from_user.id, state, hour, default_minute_for_hour(user_now, target_date, hour))


@router.callback_query(ReminderFSM.waiting_for_time, F.data.startswith("time:drum:"))
async def cb_time_drum_spin(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    parts = callback.data.split(":")
    if len(parts) < 4 or not parts[2].isdigit() or not parts[3].isdigit():
        await safe_answer_callback(callback)
        return
    hour, minute = int(parts[2]), int(parts[3])
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        await safe_answer_callback(callback)
        return
    await safe_answer_callback(callback)
    await prompt_for_minutes_drum(bot, callback.from_user.id, state, hour, minute)


@router.callback_query(ReminderFSM.waiting_for_time, F.data == "time:back_to_hours")
async def cb_time_back_to_hours(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await safe_answer_callback(callback)
    await prompt_for_time(bot, callback.from_user.id, state)


@router.callback_query(ReminderFSM.waiting_for_time, F.data.startswith("time:pick:"))
async def cb_time_pick_confirm(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    parts = callback.data.split(":")
    if len(parts) < 4 or not parts[2].isdigit() or not parts[3].isdigit():
        await safe_answer_callback(callback)
        return
    hour, minute = int(parts[2]), int(parts[3])
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        await safe_answer_callback(callback)
        return
    await safe_answer_callback(callback)
    await validate_time_and_ask_recurrence(bot, callback.from_user.id, state, time(hour, minute))


@router.callback_query(F.data.in_({"date:today", "date:1d", "date:1w", "date:1m", "date:1y"}))
async def cb_quick_date(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    if not await _ensure_create_date_session(bot, callback, state):
        return
    await safe_answer_callback(callback)
    user_now, _ = await get_user_now(callback.from_user.id)
    today = user_now.date()
    action = callback.data.split(":")[1]
    target_date = (
        today if action == "today"
        else today + timedelta(days=1) if action == "1d"
        else today + timedelta(days=7) if action == "1w"
        else add_one_month(today) if action == "1m"
        else add_one_year(today)
    )
    await state.update_data(target_date=target_date.isoformat(), date_choice_type=action)
    await state.set_state(ReminderFSM.waiting_for_time)
    await prompt_for_time(bot, callback.from_user.id, state)


async def show_create_calendar(bot: Bot, user_id: int, state: FSMContext, year: int, month: int, error_msg: str = "") -> None:
    data = await state.get_data()
    reminder_text = (data.get("reminder_text") or "").strip()
    if not reminder_text:
        await _handle_expired_create_session(bot, user_id, state)
        return
    lang = await get_user_language(user_id)
    user_now, _ = await get_user_now(user_id)
    err_block = f"⚠️ <b>{error_msg}</b>\n\n" if error_msg else ""
    kb = build_calendar_kb(
        year=year, month=month, today=user_now.date(), nav_prefix="cal:cnav", ym_prefix="cal:cym",
        pick_prefix="cal:cpick", back_callback="time:back_to_date", lang=lang,
    )
    await render_panel(bot=bot, user_id=user_id, text=t(lang, "create_cal_prompt", text=reminder_text, err_block=err_block), reply_markup=kb)


async def show_create_ym_picker(bot: Bot, user_id: int, state: FSMContext, year: int, current_month: int) -> None:
    data = await state.get_data()
    reminder_text = (data.get("reminder_text") or "").strip()
    if not reminder_text:
        await _handle_expired_create_session(bot, user_id, state)
        return
    lang = await get_user_language(user_id)
    user_now, _ = await get_user_now(user_id)
    kb = build_calendar_ym_kb(
        year=year, current_month=current_month, today=user_now.date(),
        year_nav_prefix="cal:cynav", month_pick_prefix="cal:cmpick", lang=lang,
    )
    await render_panel(bot=bot, user_id=user_id, text=t(lang, "create_ym_prompt", text=reminder_text), reply_markup=kb)


@router.callback_query(F.data == "date:custom")
async def cb_custom_date(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    if not await _ensure_create_date_session(bot, callback, state):
        return
    await safe_answer_callback(callback)
    await state.set_state(ReminderFSM.waiting_for_custom_date)
    user_now, _ = await get_user_now(callback.from_user.id)
    today = user_now.date()
    await show_create_calendar(bot, callback.from_user.id, state, today.year, today.month)


@router.callback_query(F.data.startswith("cal:cnav:"))
async def cb_create_calendar_nav(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    if not await _ensure_create_date_session(bot, callback, state):
        return
    parts = callback.data.split(":")
    if len(parts) < 5 or not parts[2].isdigit() or not parts[3].isdigit():
        await safe_answer_callback(callback)
        return
    year, month, direction = int(parts[2]), int(parts[3]), parts[4]
    if not (1 <= month <= 12) or direction not in ("prev", "next"):
        await safe_answer_callback(callback)
        return
    new_year, new_month = step_year_month(year, month, direction)
    uid = callback.from_user.id
    user_now, _ = await get_user_now(uid)
    today = user_now.date()
    if (new_year, new_month) < (today.year, today.month):
        await safe_answer_callback(callback, t(await get_user_language(uid), "cal_past_month"), show_alert=False)
        return
    await safe_answer_callback(callback)
    await show_create_calendar(bot, uid, state, new_year, new_month)


@router.callback_query(F.data.startswith("cal:cym:"))
async def cb_create_calendar_ym_open(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    if not await _ensure_create_date_session(bot, callback, state):
        return
    parts = callback.data.split(":")
    if len(parts) < 4 or not parts[2].isdigit() or not parts[3].isdigit():
        await safe_answer_callback(callback)
        return
    year, month = int(parts[2]), int(parts[3])
    if not (1 <= month <= 12):
        await safe_answer_callback(callback)
        return
    await safe_answer_callback(callback)
    await show_create_ym_picker(bot, callback.from_user.id, state, year, month)


@router.callback_query(F.data.startswith("cal:cynav:"))
async def cb_create_calendar_year_nav(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    if not await _ensure_create_date_session(bot, callback, state):
        return
    parts = callback.data.split(":")
    if len(parts) < 5 or not parts[2].isdigit() or not parts[3].isdigit():
        await safe_answer_callback(callback)
        return
    year, month, direction = int(parts[2]), int(parts[3]), parts[4]
    if not (1 <= month <= 12) or direction not in ("prev", "next"):
        await safe_answer_callback(callback)
        return
    new_year = year + 1 if direction == "next" else year - 1
    uid = callback.from_user.id
    user_now, _ = await get_user_now(uid)
    if new_year < user_now.date().year:
        await safe_answer_callback(callback, t(await get_user_language(uid), "cal_past_year"), show_alert=False)
        return
    await safe_answer_callback(callback)
    await show_create_ym_picker(bot, uid, state, new_year, month)


@router.callback_query(F.data.startswith("cal:cmpick:"))
async def cb_create_calendar_month_pick(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    if not await _ensure_create_date_session(bot, callback, state):
        return
    parts = callback.data.split(":")
    if len(parts) < 4 or not parts[2].isdigit() or not parts[3].isdigit():
        await safe_answer_callback(callback)
        return
    year, month = int(parts[2]), int(parts[3])
    if not (1 <= month <= 12):
        await safe_answer_callback(callback)
        return
    uid = callback.from_user.id
    user_now, _ = await get_user_now(uid)
    today = user_now.date()
    if (year, month) < (today.year, today.month):
        await safe_answer_callback(callback, t(await get_user_language(uid), "cal_past_month"), show_alert=False)
        return
    await safe_answer_callback(callback)
    await show_create_calendar(bot, uid, state, year, month)


@router.callback_query(F.data.startswith("cal:cpick:"))
async def cb_create_calendar_pick(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    if not await _ensure_create_date_session(bot, callback, state):
        return
    parts = callback.data.split(":", 2)
    if len(parts) < 3:
        await safe_answer_callback(callback)
        return
    try:
        picked_date = date.fromisoformat(parts[2])
    except ValueError:
        await safe_answer_callback(callback)
        return
    uid = callback.from_user.id
    user_now, _ = await get_user_now(uid)
    if picked_date < user_now.date():
        await safe_answer_callback(callback, t(await get_user_language(uid), "cal_past_date"), show_alert=False)
        return
    await safe_answer_callback(callback)
    await state.update_data(target_date=picked_date.isoformat(), date_choice_type="custom")
    await state.set_state(ReminderFSM.waiting_for_time)
    await prompt_for_time(bot, uid, state)


@router.callback_query(F.data == "time:back_to_date")
async def cb_back_to_date(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    reminder_text = ((await state.get_data()).get("reminder_text") or "").strip()
    if not reminder_text:
        await _handle_expired_create_session(bot, callback.from_user.id, state, callback)
        return
    await safe_answer_callback(callback)
    await start_date_selection(bot=bot, user_id=callback.from_user.id, state=state, reminder_text=reminder_text)


@router.message(ReminderFSM.waiting_for_date, F.text)
@router.message(ReminderFSM.waiting_for_custom_date, F.text)
async def process_custom_date_input(message: Message, state: FSMContext, bot: Bot) -> None:
    await safe_delete_message(bot, message.chat.id, message.message_id)
    uid = message.from_user.id
    if not ((await state.get_data()).get("reminder_text") or "").strip():
        await _handle_expired_create_session(bot, uid, state)
        return
    lang = await get_user_language(uid)
    user_now, _ = await get_user_now(uid)
    today = user_now.date()
    parsed_date = parse_user_date(message.text, today)
    if not parsed_date:
        await show_create_calendar(bot, uid, state, today.year, today.month, error_msg=t(lang, "err_bad_date_create"))
        return
    if parsed_date < today:
        await show_create_calendar(bot, uid, state, today.year, today.month, error_msg=t(lang, "err_past_date_create"))
        return
    await state.update_data(target_date=parsed_date.isoformat(), date_choice_type="custom")
    await state.set_state(ReminderFSM.waiting_for_time)
    await prompt_for_time(bot, uid, state)


async def prompt_for_recurrence_type(bot: Bot, user_id: int, state: FSMContext) -> None:
    data = await state.get_data()
    reminder_text = (data.get("reminder_text") or "").strip()
    target_date_iso = data.get("target_date")
    target_time_iso = data.get("target_time")
    if not reminder_text or not target_date_iso or not target_time_iso:
        await _handle_expired_create_session(bot, user_id, state)
        return
    lang = await get_user_language(user_id)
    target_date = date.fromisoformat(target_date_iso)
    target_time = time.fromisoformat(target_time_iso)
    text = t(lang, "create_rec_type_prompt", text=reminder_text, date=format_date_with_weekday(target_date, lang=lang), time=target_time.strftime("%H:%M"))
    await render_panel(bot=bot, user_id=user_id, text=text, reply_markup=recurrence_type_kb(lang=lang))


async def validate_time_and_ask_recurrence(bot: Bot, user_id: int, state: FSMContext, chosen_time: time) -> None:
    data = await state.get_data()
    reminder_text = (data.get("reminder_text") or "").strip()
    target_date_iso = data.get("target_date")
    if not reminder_text or not target_date_iso:
        await _handle_expired_create_session(bot, user_id, state)
        return
    lang = await get_user_language(user_id)
    target_date = date.fromisoformat(target_date_iso)
    user_now, _ = await get_user_now(user_id)
    if datetime.combine(target_date, chosen_time) <= user_now.replace(tzinfo=None):
        await prompt_for_time(bot, user_id, state, error_msg=t(lang, "err_past_time"))
        return
    await state.update_data(target_time=chosen_time.isoformat())
    await state.set_state(ReminderFSM.waiting_for_recurrence)
    await prompt_for_recurrence_type(bot, user_id, state)


@router.callback_query(ReminderFSM.waiting_for_time, F.data == "time:skip")
async def cb_skip_time(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    uid = callback.from_user.id
    data = await state.get_data()
    target_date_iso = data.get("target_date")
    if not (data.get("reminder_text") or "").strip() or not target_date_iso:
        await _handle_expired_create_session(bot, uid, state, callback)
        return
    await safe_answer_callback(callback)
    lang = await get_user_language(uid)
    target_date = date.fromisoformat(target_date_iso)
    user_now, _ = await get_user_now(uid)
    resolved_date, resolved_time, _ = compute_skip_time_button(user_now, target_date, data.get("date_choice_type", "custom"), lang=lang)
    if resolved_date != target_date:
        await state.update_data(target_date=resolved_date.isoformat())
    await validate_time_and_ask_recurrence(bot, uid, state, resolved_time)


@router.message(ReminderFSM.waiting_for_time, F.text)
async def process_time_input(message: Message, state: FSMContext, bot: Bot) -> None:
    await safe_delete_message(bot, message.chat.id, message.message_id)
    uid = message.from_user.id
    lang = await get_user_language(uid)
    parsed_time = parse_user_time(message.text)
    if not parsed_time:
        await prompt_for_time(bot, uid, state, error_msg=t(lang, "err_bad_time_create"))
        return
    await validate_time_and_ask_recurrence(bot, uid, state, parsed_time)


async def save_reminder_with_recurrence(bot: Bot, user_id: int, state: FSMContext, recurrence: str) -> None:
    data = await state.get_data()
    reminder_text = (data.get("reminder_text") or "").strip()
    target_date_iso = data.get("target_date")
    target_time_iso = data.get("target_time")
    if not reminder_text or not target_date_iso or not target_time_iso:
        await _handle_expired_create_session(bot, user_id, state)
        return
    try:
        target_date = date.fromisoformat(target_date_iso)
        target_time = time.fromisoformat(target_time_iso)
    except ValueError:
        await _handle_expired_create_session(bot, user_id, state)
        return

    lang = await get_user_language(user_id)
    user_now, offset_mins = await get_user_now(user_id)
    local_remind_dt = datetime.combine(target_date, target_time)
    if local_remind_dt <= user_now.replace(tzinfo=None):
        await state.set_state(ReminderFSM.waiting_for_time)
        await prompt_for_time(bot, user_id, state, error_msg=t(lang, "err_past_time"))
        return

    await create_reminder(user_id=user_id, text=reminder_text, remind_at_utc=local_remind_dt - timedelta(minutes=offset_mins), recurrence=recurrence)
    await state.clear()

    dt_line = format_created_reminder_dt(local_remind_dt, user_now.date(), lang=lang)
    tz_label = format_tz_label(offset_mins, lang=lang)
    rec_label = format_recurrence_label(recurrence, lang=lang)
    rec_line = f"\n{rec_label}" if rec_label and recurrence != "once" else ""
    card_text = f"{dt_line}\n{tz_label}{rec_line}\n\n{reminder_text}"
    kb = await get_user_main_menu_kb(user_id, create_btn_text=t(lang, "btn_create_more_rem"), lang=lang)
    await render_panel(bot=bot, user_id=user_id, text=card_text, reply_markup=kb)


@router.callback_query(ReminderFSM.waiting_for_recurrence, F.data == "rec:back_to_time")
async def cb_rec_back_to_time(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await safe_answer_callback(callback)
    await state.set_state(ReminderFSM.waiting_for_time)
    await prompt_for_time(bot, callback.from_user.id, state)


@router.callback_query(ReminderFSM.waiting_for_recurrence, F.data == "rec:back_to_type")
async def cb_rec_back_to_type(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await safe_answer_callback(callback)
    await prompt_for_recurrence_type(bot, callback.from_user.id, state)


@router.callback_query(ReminderFSM.waiting_for_recurrence, F.data == "rec:once")
async def cb_rec_once(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await safe_answer_callback(callback)
    await save_reminder_with_recurrence(bot, callback.from_user.id, state, "once")


@router.callback_query(ReminderFSM.waiting_for_recurrence, F.data == "rec:menu")
async def cb_rec_menu(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    uid = callback.from_user.id
    data = await state.get_data()
    reminder_text = (data.get("reminder_text") or "").strip()
    target_date_iso = data.get("target_date")
    target_time_iso = data.get("target_time")
    if not reminder_text or not target_date_iso or not target_time_iso:
        await _handle_expired_create_session(bot, uid, state, callback)
        return
    await safe_answer_callback(callback)
    lang = await get_user_language(uid)
    text = t(
        lang, "create_rec_period_prompt", text=reminder_text,
        date=format_date_with_weekday(date.fromisoformat(target_date_iso), lang=lang),
        time=time.fromisoformat(target_time_iso).strftime("%H:%M"),
    )
    await render_panel(bot=bot, user_id=uid, text=text, reply_markup=recurrence_period_kb(lang=lang))


@router.callback_query(ReminderFSM.waiting_for_recurrence, F.data.startswith("rec_set:"))
async def cb_rec_set_period(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    parts = callback.data.split(":")
    recurrence = parts[1] if len(parts) > 1 else ""
    if recurrence not in VALID_RECURRING_PERIODS:
        await safe_answer_callback(callback)
        return
    await safe_answer_callback(callback)
    await save_reminder_with_recurrence(bot, callback.from_user.id, state, recurrence)


@router.callback_query(F.data.startswith(("time:", "rec:", "rec_set:")))
async def cb_stale_create_button(callback: CallbackQuery) -> None:
    await safe_answer_callback(callback, t(await get_user_language(callback.from_user.id), "create_stale_btn"), show_alert=False)


@router.message()
async def handle_direct_message(message: Message, state: FSMContext, bot: Bot) -> None:
    await safe_delete_message(bot, message.chat.id, message.message_id)
    uid = message.from_user.id
    lang = await get_user_language(uid)
    reminder_text = extract_message_text(message, lang=lang)
    if not reminder_text:
        return
    await state.clear()
    await start_date_selection(bot=bot, user_id=uid, state=state, reminder_text=reminder_text, lang=lang)
