from datetime import datetime, date, time, timedelta
from aiogram import Router, Bot, F
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery

from database import (
    add_tracked_messages_batch,
    create_reminder,
    get_user_now,
    format_tz_label,
    format_recurrence_label,
    set_panel_message_id,
    pop_all_window_messages,
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

RU_WEEKDAYS_ON_DAY: dict[int, str] = {
    0: "в понедельник",
    1: "во вторник",
    2: "в среду",
    3: "в четверг",
    4: "в пятницу",
    5: "в субботу",
    6: "в воскресенье",
}


async def _handle_expired_create_session(
    bot: Bot,
    user_id: int,
    state: FSMContext,
    callback: CallbackQuery | None = None,
) -> None:
    await state.clear()
    if callback is not None:
        await safe_answer_callback(
            callback,
            "Сессия создания устарела. Начните заново.",
            show_alert=False,
        )
    home_text = await build_home_text(
        user_id,
        notice="ℹ️ <b>Сессия создания напоминания устарела.</b> Нажмите «➕ Создать напоминание» или отправьте текст заново.",
    )
    kb = await get_user_main_menu_kb(user_id)
    await render_panel(
        bot=bot,
        user_id=user_id,
        text=home_text,
        reply_markup=kb,
    )


async def _ensure_create_date_session(
    bot: Bot,
    callback: CallbackQuery,
    state: FSMContext,
) -> bool:
    current_state = await state.get_state()
    data = await state.get_data()
    reminder_text = (data.get("reminder_text") or "").strip()

    if not reminder_text:
        await _handle_expired_create_session(bot, callback.from_user.id, state, callback)
        return False

    if current_state not in (
        ReminderFSM.waiting_for_date.state,
        ReminderFSM.waiting_for_custom_date.state,
    ):
        await safe_answer_callback(callback)
        return False

    return True


def format_created_reminder_dt(local_dt: datetime, today: date) -> str:
    target_date = local_dt.date()
    time_str = local_dt.strftime("%H:%M")
    if target_date == today:
        return f"Сегодня, {RU_WEEKDAYS_ON_DAY[target_date.weekday()]}, {time_str}"
    if target_date == today + timedelta(days=1):
        return f"Завтра, {RU_WEEKDAYS_ON_DAY[target_date.weekday()]}, {time_str}"
    return f"{format_date_with_weekday(target_date)}, {time_str}"


def compute_skip_time_button(
    user_now: datetime,
    target_date: date,
    date_choice_type: str,
) -> tuple[date, time, str]:
    today = user_now.date()
    now_naive = user_now.replace(tzinfo=None)

    if date_choice_type == "today":
        if (now_naive.hour, now_naive.minute) <= (14, 30):
            return target_date, time(15, 0), "Сегодня в 15:00"
        rounded_dt = now_naive.replace(minute=0, second=0, microsecond=0) + timedelta(hours=2)
        if rounded_dt.date() == today:
            return rounded_dt.date(), rounded_dt.time(), f"Сегодня в {rounded_dt.strftime('%H:%M')}"
        return rounded_dt.date(), rounded_dt.time(), f"Завтра в {rounded_dt.strftime('%H:%M')}"

    if date_choice_type == "1d":
        return target_date, time(15, 0), "Завтра в 15:00"

    if date_choice_type == "1w":
        return target_date, time(15, 0), "Через неделю в 15:00"

    if date_choice_type == "1m":
        return target_date, time(15, 0), "Через месяц в 15:00"

    if date_choice_type == "1y":
        return target_date, time(15, 0), "Через год в 15:00"

    if target_date == today and (now_naive.hour, now_naive.minute) > (14, 30):
        rounded_dt = now_naive.replace(minute=0, second=0, microsecond=0) + timedelta(hours=2)
        date_text = format_date_text_ru(rounded_dt.date(), today.year)
        return rounded_dt.date(), rounded_dt.time(), f"{date_text} в {rounded_dt.strftime('%H:%M')}"

    date_text = format_date_text_ru(target_date, today.year)
    return target_date, time(15, 0), f"{date_text} в 15:00"


def default_minute_for_hour(user_now: datetime, target_date: date, hour: int) -> int:
    today = user_now.date()
    now_naive = user_now.replace(tzinfo=None)
    if target_date == today and hour == now_naive.hour:
        next_5 = ((now_naive.minute // 5) + 1) * 5
        return min(next_5, 59)
    return 0


@router.callback_query(F.data == "cal:ignore")
async def cb_calendar_ignore(callback: CallbackQuery) -> None:
    await safe_answer_callback(callback)


@router.callback_query(F.data == "cal:past")
async def cb_calendar_past(callback: CallbackQuery) -> None:
    await safe_answer_callback(callback, "Эта дата уже в прошлом", show_alert=False)


@router.callback_query(F.data == "cal:past_month")
async def cb_calendar_past_month(callback: CallbackQuery) -> None:
    await safe_answer_callback(callback, "Нельзя выбрать прошедший месяц", show_alert=False)


@router.callback_query(F.data == "cal:past_year")
async def cb_calendar_past_year(callback: CallbackQuery) -> None:
    await safe_answer_callback(callback, "Нельзя выбрать прошедший год", show_alert=False)


@router.callback_query(F.data == "cal:past_time")
async def cb_calendar_past_time(callback: CallbackQuery) -> None:
    await safe_answer_callback(callback, "Это время сегодня уже прошло", show_alert=False)


@router.message(F.forward_origin | F.forward_date)
async def handle_forwarded_message(message: Message, state: FSMContext, bot: Bot) -> None:
    await safe_delete_message(bot, message.chat.id, message.message_id)
    reminder_text = extract_message_text(message)
    if not reminder_text:
        return
    await state.clear()
    await start_date_selection(
        bot=bot,
        user_id=message.from_user.id,
        state=state,
        reminder_text=reminder_text,
    )


@router.callback_query(F.data == "menu:create")
async def cb_menu_create(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await safe_answer_callback(callback)
    await state.clear()
    await state.set_state(ReminderFSM.waiting_for_text)
    uid = callback.from_user.id

    old_ids = await pop_all_window_messages(uid)
    new_tracked_ids: list[int] = []
    sent_ok = False
    try:
        msg1 = await bot.send_message(
            chat_id=uid,
            text="✍️ <b>Создание напоминания – Шаг 1 из 4</b>",
            disable_notification=True,
        )
        new_tracked_ids.append(msg1.message_id)
        msg2 = await bot.send_message(
            chat_id=uid,
            text="Введите текст сообщения или перешлите в бот сообщение из любого чата",
            reply_markup=cancel_to_menu_kb(),
            disable_notification=True,
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
    reminder_text = extract_message_text(message)
    if not reminder_text:
        return
    await start_date_selection(
        bot=bot,
        user_id=message.from_user.id,
        state=state,
        reminder_text=reminder_text,
    )


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

    date_choice_type = data.get("date_choice_type", "custom")

    user_now, _ = await get_user_now(user_id)
    _, _, skip_btn_text = compute_skip_time_button(user_now, target_date, date_choice_type)
    date_formatted = format_date_with_weekday(target_date)

    err_block = f"⚠️ <b>{error_msg}</b>\n\n" if error_msg else ""
    text = (
        "⏰ <b>Создание напоминания — Выбор часа</b>\n\n"
        f"💬 <b>Сообщение:</b>\n{reminder_text}\n\n"
        f"📅 <b>Дата:</b> <code>{date_formatted}</code>\n\n"
        f"{err_block}"
        f"Нажмите <b>«{skip_btn_text}»</b>, выберите <b>час</b> в сетке ниже "
        "или напишите время в чат (например, <code>09:30</code>):"
    )
    kb = build_hours_picker_kb(
        target_date=target_date,
        user_now=user_now,
        skip_btn_text=skip_btn_text,
        skip_callback="time:skip",
        hour_prefix="time:hour",
        change_date_callback="time:back_to_date",
        back_callback="menu:list",
        plain_style=False,
    )
    await render_panel(
        bot=bot,
        user_id=user_id,
        text=text,
        reply_markup=kb,
    )


async def prompt_for_minutes_drum(
    bot: Bot,
    user_id: int,
    state: FSMContext,
    hour: int,
    minute: int,
    error_msg: str = "",
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

    user_now, _ = await get_user_now(user_id)

    err_block = f"⚠️ <b>{error_msg}</b>\n\n" if error_msg else ""
    text = (
        "⏰ <b>Создание напоминания — Выбор минут</b>\n\n"
        f"💬 <b>Сообщение:</b>\n{reminder_text}\n\n"
        f"📅 <b>Дата:</b> <code>{format_date_with_weekday(target_date)}</code>\n"
        f"🕒 <b>Выбранное время:</b> <code>{hour:02d}:{minute:02d}</code>\n\n"
        f"{err_block}"
        "Нажмите на готовое время в сетке ниже или подкрутите <b>барабан</b> (▲/▼) до нужной минуты:"
    )
    kb = build_minutes_drum_kb(
        hour=hour,
        minute=minute,
        target_date=target_date,
        user_now=user_now,
        drum_prefix="time:drum",
        pick_prefix="time:pick",
        back_to_hours_callback="time:back_to_hours",
        back_callback="menu:list",
        plain_style=False,
    )
    await render_panel(
        bot=bot,
        user_id=user_id,
        text=text,
        reply_markup=kb,
    )


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

    start_min = default_minute_for_hour(user_now, target_date, hour)
    await prompt_for_minutes_drum(bot, callback.from_user.id, state, hour, start_min)


@router.callback_query(ReminderFSM.waiting_for_time, F.data.startswith("time:drum:"))
async def cb_time_drum_spin(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    parts = callback.data.split(":")
    if len(parts) < 4 or not parts[2].isdigit() or not parts[3].isdigit():
        await safe_answer_callback(callback)
        return
    hour = int(parts[2])
    minute = int(parts[3])
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
    hour = int(parts[2])
    minute = int(parts[3])
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

    if action == "today":
        target_date = today
    elif action == "1d":
        target_date = today + timedelta(days=1)
    elif action == "1w":
        target_date = today + timedelta(days=7)
    elif action == "1m":
        target_date = add_one_month(today)
    else:
        target_date = add_one_year(today)

    await state.update_data(
        target_date=target_date.isoformat(),
        date_choice_type=action,
    )
    await state.set_state(ReminderFSM.waiting_for_time)
    await prompt_for_time(bot, callback.from_user.id, state)


async def show_create_calendar(
    bot: Bot,
    user_id: int,
    state: FSMContext,
    year: int,
    month: int,
    error_msg: str = "",
) -> None:
    data = await state.get_data()
    reminder_text = (data.get("reminder_text") or "").strip()
    if not reminder_text:
        await _handle_expired_create_session(bot, user_id, state)
        return

    user_now, _ = await get_user_now(user_id)
    today = user_now.date()

    err_block = f"⚠️ <b>{error_msg}</b>\n\n" if error_msg else ""
    text = (
        "📅 <b>Календарь — Выбор даты</b>\n\n"
        f"💬 <b>Сообщение:</b>\n{reminder_text}\n\n"
        f"{err_block}"
        "Выберите день в календаре, нажмите на <b>месяц и год</b> в шапке для быстрого переключения года "
        "или отправьте дату в чат (<code>ДД.ММ.ГГГГ</code>):"
    )
    kb = build_calendar_kb(
        year=year,
        month=month,
        today=today,
        nav_prefix="cal:cnav",
        ym_prefix="cal:cym",
        pick_prefix="cal:cpick",
        back_callback="time:back_to_date",
        plain_home=False,
    )
    await render_panel(
        bot=bot,
        user_id=user_id,
        text=text,
        reply_markup=kb,
    )


async def show_create_ym_picker(
    bot: Bot,
    user_id: int,
    state: FSMContext,
    year: int,
    current_month: int,
) -> None:
    data = await state.get_data()
    reminder_text = (data.get("reminder_text") or "").strip()
    if not reminder_text:
        await _handle_expired_create_session(bot, user_id, state)
        return

    user_now, _ = await get_user_now(user_id)
    today = user_now.date()

    text = (
        "📅 <b>Быстрый выбор года и месяца</b>\n\n"
        f"💬 <b>Сообщение:</b>\n{reminder_text}\n\n"
        "Нажмите <b>«На год вперёд»</b>, переключите год стрелками <code>&lt;</code> <code>&gt;</code> "
        "или выберите нужный месяц:"
    )
    kb = build_calendar_ym_kb(
        year=year,
        current_month=current_month,
        today=today,
        year_nav_prefix="cal:cynav",
        month_pick_prefix="cal:cmpick",
        plain_home=False,
    )
    await render_panel(
        bot=bot,
        user_id=user_id,
        text=text,
        reply_markup=kb,
    )


@router.callback_query(F.data == "date:custom")
async def cb_custom_date(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    if not await _ensure_create_date_session(bot, callback, state):
        return

    await safe_answer_callback(callback)
    await state.set_state(ReminderFSM.waiting_for_custom_date)
    user_now, _ = await get_user_now(callback.from_user.id)
    today = user_now.date()
    await show_create_calendar(
        bot=bot,
        user_id=callback.from_user.id,
        state=state,
        year=today.year,
        month=today.month,
    )


@router.callback_query(F.data.startswith("cal:cnav:"))
async def cb_create_calendar_nav(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    if not await _ensure_create_date_session(bot, callback, state):
        return

    parts = callback.data.split(":")
    if len(parts) < 5 or not parts[2].isdigit() or not parts[3].isdigit():
        await safe_answer_callback(callback)
        return

    year = int(parts[2])
    month = int(parts[3])
    direction = parts[4]
    if not (1 <= month <= 12) or direction not in ("prev", "next"):
        await safe_answer_callback(callback)
        return

    new_year, new_month = step_year_month(year, month, direction)
    user_now, _ = await get_user_now(callback.from_user.id)
    today = user_now.date()
    if (new_year, new_month) < (today.year, today.month):
        await safe_answer_callback(callback, "Нельзя выбрать прошедший месяц", show_alert=False)
        return

    await safe_answer_callback(callback)
    await show_create_calendar(
        bot=bot,
        user_id=callback.from_user.id,
        state=state,
        year=new_year,
        month=new_month,
    )


@router.callback_query(F.data.startswith("cal:cym:"))
async def cb_create_calendar_ym_open(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    if not await _ensure_create_date_session(bot, callback, state):
        return

    parts = callback.data.split(":")
    if len(parts) < 4 or not parts[2].isdigit() or not parts[3].isdigit():
        await safe_answer_callback(callback)
        return

    year = int(parts[2])
    month = int(parts[3])
    if not (1 <= month <= 12):
        await safe_answer_callback(callback)
        return

    await safe_answer_callback(callback)
    await show_create_ym_picker(
        bot=bot,
        user_id=callback.from_user.id,
        state=state,
        year=year,
        current_month=month,
    )


@router.callback_query(F.data.startswith("cal:cynav:"))
async def cb_create_calendar_year_nav(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    if not await _ensure_create_date_session(bot, callback, state):
        return

    parts = callback.data.split(":")
    if len(parts) < 5 or not parts[2].isdigit() or not parts[3].isdigit():
        await safe_answer_callback(callback)
        return

    year = int(parts[2])
    month = int(parts[3])
    direction = parts[4]
    if not (1 <= month <= 12) or direction not in ("prev", "next"):
        await safe_answer_callback(callback)
        return

    new_year = year + 1 if direction == "next" else year - 1
    user_now, _ = await get_user_now(callback.from_user.id)
    today = user_now.date()
    if new_year < today.year:
        await safe_answer_callback(callback, "Нельзя выбрать прошедший год", show_alert=False)
        return

    await safe_answer_callback(callback)
    await show_create_ym_picker(
        bot=bot,
        user_id=callback.from_user.id,
        state=state,
        year=new_year,
        current_month=month,
    )


@router.callback_query(F.data.startswith("cal:cmpick:"))
async def cb_create_calendar_month_pick(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    if not await _ensure_create_date_session(bot, callback, state):
        return

    parts = callback.data.split(":")
    if len(parts) < 4 or not parts[2].isdigit() or not parts[3].isdigit():
        await safe_answer_callback(callback)
        return

    year = int(parts[2])
    month = int(parts[3])
    if not (1 <= month <= 12):
        await safe_answer_callback(callback)
        return

    user_now, _ = await get_user_now(callback.from_user.id)
    today = user_now.date()
    if (year, month) < (today.year, today.month):
        await safe_answer_callback(callback, "Нельзя выбрать прошедший месяц", show_alert=False)
        return

    await safe_answer_callback(callback)
    await show_create_calendar(
        bot=bot,
        user_id=callback.from_user.id,
        state=state,
        year=year,
        month=month,
    )


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

    user_now, _ = await get_user_now(callback.from_user.id)
    today = user_now.date()
    if picked_date < today:
        await safe_answer_callback(callback, "Эта дата уже в прошлом", show_alert=False)
        return

    await safe_answer_callback(callback)
    await state.update_data(
        target_date=picked_date.isoformat(),
        date_choice_type="custom",
    )
    await state.set_state(ReminderFSM.waiting_for_time)
    await prompt_for_time(bot, callback.from_user.id, state)


@router.callback_query(F.data == "time:back_to_date")
async def cb_back_to_date(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    data = await state.get_data()
    reminder_text = (data.get("reminder_text") or "").strip()
    if not reminder_text:
        await _handle_expired_create_session(bot, callback.from_user.id, state, callback)
        return

    await safe_answer_callback(callback)
    await start_date_selection(
        bot=bot,
        user_id=callback.from_user.id,
        state=state,
        reminder_text=reminder_text,
    )


@router.message(ReminderFSM.waiting_for_date, F.text)
@router.message(ReminderFSM.waiting_for_custom_date, F.text)
async def process_custom_date_input(message: Message, state: FSMContext, bot: Bot) -> None:
    await safe_delete_message(bot, message.chat.id, message.message_id)
    data = await state.get_data()
    if not (data.get("reminder_text") or "").strip():
        await _handle_expired_create_session(bot, message.from_user.id, state)
        return

    user_now, _ = await get_user_now(message.from_user.id)
    today = user_now.date()
    parsed_date = parse_user_date(message.text, today)

    if not parsed_date:
        await show_create_calendar(
            bot=bot,
            user_id=message.from_user.id,
            state=state,
            year=today.year,
            month=today.month,
            error_msg="Неверный формат даты! Выберите день в календаре или введите ДД.ММ.ГГГГ.",
        )
        return

    if parsed_date < today:
        await show_create_calendar(
            bot=bot,
            user_id=message.from_user.id,
            state=state,
            year=today.year,
            month=today.month,
            error_msg="Указанная дата уже в прошлом! Выберите актуальную дату.",
        )
        return

    await state.update_data(
        target_date=parsed_date.isoformat(),
        date_choice_type="custom",
    )
    await state.set_state(ReminderFSM.waiting_for_time)
    await prompt_for_time(bot, message.from_user.id, state)


async def prompt_for_recurrence_type(bot: Bot, user_id: int, state: FSMContext) -> None:
    data = await state.get_data()
    reminder_text = (data.get("reminder_text") or "").strip()
    target_date_iso = data.get("target_date")
    target_time_iso = data.get("target_time")
    if not reminder_text or not target_date_iso or not target_time_iso:
        await _handle_expired_create_session(bot, user_id, state)
        return

    target_date = date.fromisoformat(target_date_iso)
    target_time = time.fromisoformat(target_time_iso)

    text = (
        "🔁 <b>Создание напоминания — Периодичность</b>\n\n"
        f"💬 <b>Сообщение:</b>\n{reminder_text}\n\n"
        f"📅 <b>Дата:</b> <code>{format_date_with_weekday(target_date)}</code>\n"
        f"⏰ <b>Время:</b> <code>{target_time.strftime('%H:%M')}</code>\n\n"
        "Выберите тип напоминания:"
    )
    await render_panel(
        bot=bot,
        user_id=user_id,
        text=text,
        reply_markup=recurrence_type_kb(),
    )


async def validate_time_and_ask_recurrence(
    bot: Bot,
    user_id: int,
    state: FSMContext,
    chosen_time: time,
) -> None:
    data = await state.get_data()
    reminder_text = (data.get("reminder_text") or "").strip()
    target_date_iso = data.get("target_date")
    if not reminder_text or not target_date_iso:
        await _handle_expired_create_session(bot, user_id, state)
        return

    target_date = date.fromisoformat(target_date_iso)

    user_now, _ = await get_user_now(user_id)
    local_remind_dt = datetime.combine(target_date, chosen_time)
    current_local_dt = user_now.replace(tzinfo=None)

    if local_remind_dt <= current_local_dt:
        await prompt_for_time(
            bot,
            user_id,
            state,
            error_msg="Выбранное время уже прошло. Укажите более позднее время",
        )
        return

    await state.update_data(target_time=chosen_time.isoformat())
    await state.set_state(ReminderFSM.waiting_for_recurrence)
    await prompt_for_recurrence_type(bot, user_id, state)


@router.callback_query(ReminderFSM.waiting_for_time, F.data == "time:skip")
async def cb_skip_time(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    data = await state.get_data()
    target_date_iso = data.get("target_date")
    if not (data.get("reminder_text") or "").strip() or not target_date_iso:
        await _handle_expired_create_session(bot, callback.from_user.id, state, callback)
        return

    await safe_answer_callback(callback)
    target_date = date.fromisoformat(target_date_iso)
    date_choice_type = data.get("date_choice_type", "custom")

    user_now, _ = await get_user_now(callback.from_user.id)
    resolved_date, resolved_time, _ = compute_skip_time_button(
        user_now, target_date, date_choice_type
    )
    if resolved_date != target_date:
        await state.update_data(target_date=resolved_date.isoformat())

    await validate_time_and_ask_recurrence(bot, callback.from_user.id, state, resolved_time)


@router.message(ReminderFSM.waiting_for_time, F.text)
async def process_time_input(message: Message, state: FSMContext, bot: Bot) -> None:
    await safe_delete_message(bot, message.chat.id, message.message_id)
    parsed_time = parse_user_time(message.text)

    if not parsed_time:
        await prompt_for_time(
            bot,
            message.from_user.id,
            state,
            error_msg="Неверный формат времени! Выберите час кнопкой или введите ЧЧ:ММ.",
        )
        return

    await validate_time_and_ask_recurrence(bot, message.from_user.id, state, parsed_time)


async def save_reminder_with_recurrence(
    bot: Bot,
    user_id: int,
    state: FSMContext,
    recurrence: str,
) -> None:
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

    user_now, offset_mins = await get_user_now(user_id)
    local_remind_dt = datetime.combine(target_date, target_time)
    if local_remind_dt <= user_now.replace(tzinfo=None):
        await state.set_state(ReminderFSM.waiting_for_time)
        await prompt_for_time(
            bot,
            user_id,
            state,
            error_msg="Выбранное время уже прошло. Укажите более позднее время",
        )
        return
    remind_utc_dt = local_remind_dt - timedelta(minutes=offset_mins)

    await create_reminder(
        user_id=user_id,
        text=reminder_text,
        remind_at_utc=remind_utc_dt,
        recurrence=recurrence,
    )
    await state.clear()

    dt_line = format_created_reminder_dt(local_remind_dt, user_now.date())
    tz_label = format_tz_label(offset_mins)
    rec_label = format_recurrence_label(recurrence)
    rec_line = f"\n{rec_label}" if rec_label and recurrence != "once" else ""

    card_text = (
        f"{dt_line}\n"
        f"{tz_label}"
        f"{rec_line}\n\n"
        f"{reminder_text}"
    )
    kb = await get_user_main_menu_kb(user_id, create_btn_text="➕ Создать ещё напоминание")
    await render_panel(
        bot=bot,
        user_id=user_id,
        text=card_text,
        reply_markup=kb,
    )


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
    data = await state.get_data()
    reminder_text = (data.get("reminder_text") or "").strip()
    target_date_iso = data.get("target_date")
    target_time_iso = data.get("target_time")
    if not reminder_text or not target_date_iso or not target_time_iso:
        await _handle_expired_create_session(bot, callback.from_user.id, state, callback)
        return

    await safe_answer_callback(callback)
    target_date = date.fromisoformat(target_date_iso)
    target_time = time.fromisoformat(target_time_iso)

    text = (
        "🔁 <b>Выбор периодичности напоминания</b>\n\n"
        f"💬 <b>Сообщение:</b>\n{reminder_text}\n\n"
        f"📅 <b>Первый запуск:</b> <code>{format_date_with_weekday(target_date)} в {target_time.strftime('%H:%M')}</code>\n\n"
        "С какой периодичностью присылать напоминание?"
    )
    await render_panel(
        bot=bot,
        user_id=callback.from_user.id,
        text=text,
        reply_markup=recurrence_period_kb(),
    )


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
    await safe_answer_callback(
        callback,
        "Кнопка устарела. Начните заново или откройте главное меню.",
        show_alert=False,
    )


@router.message()
async def handle_direct_message(message: Message, state: FSMContext, bot: Bot) -> None:
    await safe_delete_message(bot, message.chat.id, message.message_id)
    reminder_text = extract_message_text(message)
    if not reminder_text:
        return
    await state.clear()
    await start_date_selection(
        bot=bot,
        user_id=message.from_user.id,
        state=state,
        reminder_text=reminder_text,
    )