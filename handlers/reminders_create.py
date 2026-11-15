import html
from datetime import datetime, date, time, timedelta
from aiogram import Router, Bot, F
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery

from database import (
    create_reminder,
    get_user_now,
    format_tz_label,
    format_recurrence_label,
)
from keyboards import (
    cancel_to_menu_kb,
    date_selection_kb,
    time_selection_kb,
    recurrence_type_kb,
    recurrence_period_kb,
)
from .states import ReminderFSM
from .common import (
    add_one_month,
    parse_user_date,
    parse_user_time,
    extract_message_text,
    safe_delete_message,
    render_panel,
    build_home_text,
    start_date_selection,
    get_user_main_menu_kb,
)

router = Router()


@router.message(F.forward_origin | F.forward_date)
async def handle_forwarded_message(message: Message, state: FSMContext, bot: Bot) -> None:
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


@router.callback_query(F.data == "menu:create")
async def cb_menu_create(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await state.clear()
    await state.set_state(ReminderFSM.waiting_for_text)
    text = (
        "✍️ <b>Создание напоминания — Шаг 1 из 4</b>\n\n"
        "Введите <b>текст сообщения</b> или перешлите сообщение из любого чата:"
    )
    await render_panel(
        bot=bot,
        user_id=callback.from_user.id,
        text=text,
        reply_markup=cancel_to_menu_kb(),
    )
    await callback.answer()


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
    reminder_text = html.escape(data.get("reminder_text", ""))
    target_date_iso = data.get("target_date")
    target_date = date.fromisoformat(target_date_iso)
    date_formatted = target_date.strftime("%d.%m.%Y")

    err_block = f"⚠️ <b>{error_msg}</b>\n\n" if error_msg else ""
    text = (
        "⏰ <b>Создание напоминания — Выбор времени</b>\n\n"
        f"💬 <b>Сообщение:</b> <i>{reminder_text}</i>\n"
        f"📅 <b>Дата:</b> <code>{date_formatted}</code>\n\n"
        f"{err_block}"
        "Введите <b>время напоминания</b> по вашим часам (например, <code>09:30</code>, <code>09.30</code> или <code>09-30</code>)\n"
        "или нажмите кнопку <b>«Сегодня в 15:00»</b>."
    )
    await render_panel(
        bot=bot,
        user_id=user_id,
        text=text,
        reply_markup=time_selection_kb(),
    )


@router.callback_query(F.data.in_({"date:today", "date:1d", "date:1w", "date:1m"}))
async def cb_quick_date(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    user_now, _ = await get_user_now(callback.from_user.id)
    today = user_now.date()
    action = callback.data.split(":")[1]

    if action == "today":
        target_date = today
    elif action == "1d":
        target_date = today + timedelta(days=1)
    elif action == "1w":
        target_date = today + timedelta(days=7)
    else:
        target_date = add_one_month(today)

    await state.update_data(target_date=target_date.isoformat())
    await state.set_state(ReminderFSM.waiting_for_time)
    await prompt_for_time(bot, callback.from_user.id, state)
    await callback.answer()


@router.callback_query(F.data == "date:custom")
async def cb_custom_date(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await state.set_state(ReminderFSM.waiting_for_custom_date)
    data = await state.get_data()
    safe_preview = html.escape(data.get("reminder_text", ""))
    user_now, _ = await get_user_now(callback.from_user.id)
    example_date = (user_now.date() + timedelta(days=3)).strftime("%d.%m.%Y")

    text = (
        "📅 <b>Ввод даты напоминания</b>\n\n"
        f"💬 <b>Сообщение:</b> <i>{safe_preview}</i>\n\n"
        f"Отправьте дату в формате <code>ДД.ММ.ГГГГ</code> или <code>ДД.ММ</code>\n"
        f"(например: <code>{example_date}</code>):"
    )
    await render_panel(
        bot=bot,
        user_id=callback.from_user.id,
        text=text,
        reply_markup=date_selection_kb(),
    )
    await callback.answer()


@router.callback_query(F.data == "time:back_to_date")
async def cb_back_to_date(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await state.set_state(ReminderFSM.waiting_for_date)
    data = await state.get_data()
    safe_preview = html.escape(data.get("reminder_text", ""))
    text = (
        "📅 <b>Создание напоминания — Выбор даты</b>\n\n"
        f"💬 <b>Сообщение:</b> <i>{safe_preview}</i>\n\n"
        "Выберите, <b>в какой день</b> прислать напоминание:"
    )
    await render_panel(
        bot=bot,
        user_id=callback.from_user.id,
        text=text,
        reply_markup=date_selection_kb(),
    )
    await callback.answer()


@router.message(ReminderFSM.waiting_for_date, F.text)
@router.message(ReminderFSM.waiting_for_custom_date, F.text)
async def process_custom_date_input(message: Message, state: FSMContext, bot: Bot) -> None:
    await safe_delete_message(bot, message.chat.id, message.message_id)
    user_now, _ = await get_user_now(message.from_user.id)
    today = user_now.date()
    parsed_date = parse_user_date(message.text, today)

    data = await state.get_data()
    safe_preview = html.escape(data.get("reminder_text", ""))

    if not parsed_date:
        text = (
            "📅 <b>Создание напоминания — Выбор даты</b>\n\n"
            f"💬 <b>Сообщение:</b> <i>{safe_preview}</i>\n\n"
            "⚠️ <b>Неверный формат даты!</b>\n"
            "Пожалуйста, введите дату в формате <code>ДД.ММ.ГГГГ</code> (например, <code>25.12.2026</code>) "
            "или выберите один из быстрых вариантов:"
        )
        await render_panel(bot, message.from_user.id, text, date_selection_kb())
        return

    if parsed_date < today:
        text = (
            "📅 <b>Создание напоминания — Выбор даты</b>\n\n"
            f"💬 <b>Сообщение:</b> <i>{safe_preview}</i>\n\n"
            "⚠️ <b>Указанная дата уже в прошлом!</b>\n"
            "Введите актуальную дату или воспользуйтесь кнопками ниже:"
        )
        await render_panel(bot, message.from_user.id, text, date_selection_kb())
        return

    await state.update_data(target_date=parsed_date.isoformat())
    await state.set_state(ReminderFSM.waiting_for_time)
    await prompt_for_time(bot, message.from_user.id, state)


async def prompt_for_recurrence_type(bot: Bot, user_id: int, state: FSMContext) -> None:
    data = await state.get_data()
    reminder_text = html.escape(data.get("reminder_text", ""))
    target_date = date.fromisoformat(data["target_date"])
    target_time = time.fromisoformat(data["target_time"])

    text = (
        "🔁 <b>Создание напоминания — Периодичность</b>\n\n"
        f"💬 <b>Сообщение:</b> <i>{reminder_text}</i>\n"
        f"📅 <b>Дата:</b> <code>{target_date.strftime('%d.%m.%Y')}</code>\n"
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
    target_date = date.fromisoformat(data["target_date"])

    user_now, _ = await get_user_now(user_id)
    local_remind_dt = datetime.combine(target_date, chosen_time)
    current_local_dt = user_now.replace(tzinfo=None)

    if local_remind_dt <= current_local_dt:
        await prompt_for_time(
            bot,
            user_id,
            state,
            error_msg="Выбранное время сегодня уже прошло! Укажите более позднее время.",
        )
        return

    await state.update_data(target_time=chosen_time.isoformat())
    await state.set_state(ReminderFSM.waiting_for_recurrence)
    await prompt_for_recurrence_type(bot, user_id, state)


@router.callback_query(ReminderFSM.waiting_for_time, F.data == "time:skip")
async def cb_skip_time(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    default_time = time(15, 0)
    await validate_time_and_ask_recurrence(bot, callback.from_user.id, state, default_time)
    await callback.answer()


@router.message(ReminderFSM.waiting_for_time, F.text)
async def process_time_input(message: Message, state: FSMContext, bot: Bot) -> None:
    await safe_delete_message(bot, message.chat.id, message.message_id)
    parsed_time = parse_user_time(message.text)

    if not parsed_time:
        await prompt_for_time(
            bot,
            message.from_user.id,
            state,
            error_msg="Неверный формат времени! Введите часы и минуты (например, 14:30 или 14.30).",
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
    reminder_text = data.get("reminder_text", "")
    target_date = date.fromisoformat(data["target_date"])
    target_time = time.fromisoformat(data["target_time"])

    _, offset_mins = await get_user_now(user_id)
    local_remind_dt = datetime.combine(target_date, target_time)
    remind_utc_dt = local_remind_dt - timedelta(minutes=offset_mins)

    await create_reminder(
        user_id=user_id,
        text=reminder_text,
        remind_at_utc=remind_utc_dt,
        recurrence=recurrence,
    )
    await state.clear()

    tz_label = format_tz_label(offset_mins)
    rec_label = format_recurrence_label(recurrence)
    notice = (
        "✅ <b>Напоминание успешно создано!</b>\n"
        f"📅 Дата: <code>{local_remind_dt.strftime('%d.%m.%Y')}</code>\n"
        f"⏰ Время: <code>{local_remind_dt.strftime('%H:%M')} ({tz_label})</code>\n"
        f"🔁 Периодичность: <code>{rec_label}</code>\n"
        f"💬 Текст: <i>{html.escape(reminder_text)}</i>"
    )
    home_text = await build_home_text(user_id, notice=notice, show_footer=False)
    kb = await get_user_main_menu_kb(user_id, create_btn_text="➕ Создать ещё напоминание")
    await render_panel(
        bot=bot,
        user_id=user_id,
        text=home_text,
        reply_markup=kb,
    )


@router.callback_query(ReminderFSM.waiting_for_recurrence, F.data == "rec:back_to_time")
async def cb_rec_back_to_time(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await state.set_state(ReminderFSM.waiting_for_time)
    await prompt_for_time(bot, callback.from_user.id, state)
    await callback.answer()


@router.callback_query(ReminderFSM.waiting_for_recurrence, F.data == "rec:back_to_type")
async def cb_rec_back_to_type(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await prompt_for_recurrence_type(bot, callback.from_user.id, state)
    await callback.answer()


@router.callback_query(ReminderFSM.waiting_for_recurrence, F.data == "rec:once")
async def cb_rec_once(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await save_reminder_with_recurrence(bot, callback.from_user.id, state, "once")
    await callback.answer()


@router.callback_query(ReminderFSM.waiting_for_recurrence, F.data == "rec:menu")
async def cb_rec_menu(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    data = await state.get_data()
    reminder_text = html.escape(data.get("reminder_text", ""))
    target_date = date.fromisoformat(data["target_date"])
    target_time = time.fromisoformat(data["target_time"])

    text = (
        "🔁 <b>Выбор периодичности напоминания</b>\n\n"
        f"💬 <b>Сообщение:</b> <i>{reminder_text}</i>\n"
        f"📅 <b>Первый запуск:</b> <code>{target_date.strftime('%d.%m.%Y')} в {target_time.strftime('%H:%M')}</code>\n\n"
        "С какой периодичностью присылать напоминание?"
    )
    await render_panel(
        bot=bot,
        user_id=callback.from_user.id,
        text=text,
        reply_markup=recurrence_period_kb(),
    )
    await callback.answer()


@router.callback_query(ReminderFSM.waiting_for_recurrence, F.data.startswith("rec_set:"))
async def cb_rec_set_period(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    recurrence = callback.data.split(":")[1]
    await save_reminder_with_recurrence(bot, callback.from_user.id, state, recurrence)
    await callback.answer()


@router.message()
async def handle_direct_message(message: Message, state: FSMContext, bot: Bot) -> None:
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
