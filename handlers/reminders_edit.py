import html
from datetime import datetime, date, time, timedelta
from aiogram import Router, Bot, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery

from database import (
    set_panel_message_id,
    add_tracked_messages_batch,
    pop_all_window_messages,
    get_active_reminders,
    get_reminder_by_id,
    update_reminder_text,
    update_reminder_datetime,
    update_reminder_recurrence,
    delete_reminder_by_id,
    get_user_now,
    format_tz_label,
    format_tz_cet,
    format_recurrence_label,
)
from keyboards import (
    build_calendar_kb,
    build_calendar_ym_kb,
    build_hours_picker_kb,
    build_minutes_drum_kb,
    reminders_section_kb,
    reminder_number_prompt_kb,
    reminder_edit_menu_kb,
    edit_text_cancel_kb,
    edit_date_selection_kb,
    edit_recurrence_type_kb,
    edit_recurrence_period_kb,
)
from .states import ReminderFSM
from .common import (
    add_one_month,
    step_year_month,
    format_date_text_ru,
    parse_user_date,
    parse_user_time,
    extract_message_text,
    safe_delete_message,
    safe_delete_messages_batch,
    render_panel,
)
from .reminders_create import compute_skip_time_button, default_minute_for_hour

router = Router()


async def show_reminders_screen(
    bot: Bot,
    user_id: int,
    state: FSMContext,
    notice: str = "",
    extra_delete_ids: list[int] | None = None,
) -> None:
    old_ids = await pop_all_window_messages(user_id)
    if extra_delete_ids:
        old_ids.extend(extra_delete_ids)

    reminders = await get_active_reminders(user_id)
    _, offset_mins = await get_user_now(user_id)
    delta = timedelta(minutes=offset_mins)
    tz_cet_str = format_tz_cet(offset_mins)

    reminder_map: dict[str, int] = {}
    new_tracked_ids: list[int] = []

    for idx, r in enumerate(reminders, start=1):
        local_dt = r.remind_at + delta
        day_str = local_dt.strftime("%d.%m.%Y")
        time_str = local_dt.strftime("%H:%M")
        
        rec_str = format_recurrence_label(r.recurrence)
        rec_line = f"\n{rec_str}" if rec_str and r.recurrence != "once" else ""
        
        # Оборачиваем текст напоминания в теги <code>...</code> для моноширинного шрифта
        safe_text = f"<code>{html.escape(r.text)}</code>"

        item_text = (
            f"№{idx} - {day_str} в {time_str}"
            f"{rec_line}\n\n"
            f"{safe_text}"
        )
        sent_item = await bot.send_message(
            chat_id=user_id,
            text=item_text,
            disable_notification=True,
        )
        new_tracked_ids.append(sent_item.message_id)
        reminder_map[str(idx)] = r.id

    if new_tracked_ids:
        await add_tracked_messages_batch(user_id, new_tracked_ids)

    await state.update_data(reminder_map=reminder_map)

    lines = [f"Раздел «Напоминания»\nЧасовой пояс {tz_cet_str}"]
    if notice:
        lines.append(notice)

    if not reminders:
        lines.append("У вас пока нет активных напоминаний.")
    else:
        lines.append(
            f"Всего активных напоминаний: {len(reminders)}\n"
            "Для изменения или удаления нажмите «Редактировать напоминания»."
        )

    sent_panel = await bot.send_message(
        chat_id=user_id,
        text="\n\n".join(lines),
        reply_markup=reminders_section_kb(has_reminders=bool(reminders)),
        disable_notification=True,
    )
    await set_panel_message_id(user_id, sent_panel.message_id)

    if old_ids:
        await safe_delete_messages_batch(bot, user_id, old_ids)


@router.message(Command("reminders", ignore_case=True))
async def cmd_reminders(message: Message, state: FSMContext, bot: Bot) -> None:
    await state.clear()
    await show_reminders_screen(
        bot,
        message.from_user.id,
        state,
        extra_delete_ids=[message.message_id],
    )


@router.callback_query(F.data == "menu:list")
async def cb_menu_list(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await callback.answer()
    await state.clear()
    await show_reminders_screen(bot, callback.from_user.id, state)


@router.callback_query(F.data == "rem:edit_prompt")
async def cb_edit_reminders_prompt(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await callback.answer()
    reminders = await get_active_reminders(callback.from_user.id)
    if not reminders:
        await state.clear()
        await show_reminders_screen(bot, callback.from_user.id, state)
        return

    reminder_map = {str(idx): r.id for idx, r in enumerate(reminders, start=1)}
    await state.update_data(reminder_map=reminder_map)
    await state.set_state(ReminderFSM.waiting_for_reminder_number)

    text = (
        "Редактирование напоминаний\n\n"
        f"Введите номер напоминания (от 1 до {len(reminders)}), "
        "которое вы хотите отредактировать:"
    )
    await render_panel(
        bot=bot,
        user_id=callback.from_user.id,
        text=text,
        reply_markup=reminder_number_prompt_kb(),
        cleanup=False,
    )


@router.message(ReminderFSM.waiting_for_reminder_number, F.text)
async def process_reminder_number_input(message: Message, state: FSMContext, bot: Bot) -> None:
    raw_num = message.text.strip()

    data = await state.get_data()
    reminder_map: dict[str, int] = data.get("reminder_map") or {}

    if not reminder_map:
        reminders = await get_active_reminders(message.from_user.id)
        reminder_map = {str(idx): r.id for idx, r in enumerate(reminders, start=1)}

    total = len(reminder_map)
    if not raw_num.isdigit() or raw_num not in reminder_map:
        await safe_delete_message(bot, message.chat.id, message.message_id)
        text = (
            "Редактирование напоминаний\n\n"
            f"Напоминание с номером «{html.escape(raw_num)}» не найдено.\n"
            f"Пожалуйста, введите существующий номер от 1 до {total}:"
        )
        await render_panel(
            bot=bot,
            user_id=message.from_user.id,
            text=text,
            reply_markup=reminder_number_prompt_kb(),
            cleanup=False,
        )
        return

    reminder_id = reminder_map[raw_num]
    await state.clear()
    await show_reminder_edit_card(
        bot,
        message.from_user.id,
        state,
        reminder_id,
        number_label=raw_num,
        extra_delete_ids=[message.message_id],
    )


async def show_reminder_edit_card(
    bot: Bot,
    user_id: int,
    state: FSMContext,
    reminder_id: int,
    notice: str = "",
    number_label: str = "",
    extra_delete_ids: list[int] | None = None,
) -> None:
    reminder = await get_reminder_by_id(user_id, reminder_id)
    if not reminder:
        await show_reminders_screen(
            bot,
            user_id,
            state,
            notice="Напоминание не найдено или уже отправлено.",
            extra_delete_ids=extra_delete_ids,
        )
        return

    _, offset_mins = await get_user_now(user_id)
    local_dt = reminder.remind_at + timedelta(minutes=offset_mins)
    
    rec_label = format_recurrence_label(reminder.recurrence)
    rec_line = f"\n{rec_label}" if rec_label and reminder.recurrence != "once" else ""

    title_num = f" №{number_label}" if number_label else ""
    notice_block = f"{notice}\n\n" if notice else ""
    
    # Также делаем текст напоминания monospace в карточке управления
    safe_text = f"<code>{html.escape(reminder.text)}</code>"

    text = (
        f"Управление напоминанием{title_num}\n"
        f"{notice_block}"
        f"{local_dt.strftime('%d.%m.%Y')} в {local_dt.strftime('%H:%M')}"
        f"{rec_line}\n\n"
        f"{safe_text}\n\n"
        "Выберите нужное действие:"
    )
    await render_panel(
        bot=bot,
        user_id=user_id,
        text=text,
        reply_markup=reminder_edit_menu_kb(reminder.id),
        cleanup=True,
        extra_delete_ids=extra_delete_ids,
    )


@router.callback_query(F.data.startswith("rem:open:"))
async def cb_open_reminder_edit(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await callback.answer()
    await state.clear()
    reminder_id = int(callback.data.split(":")[2])
    await show_reminder_edit_card(bot, callback.from_user.id, state, reminder_id)


@router.callback_query(F.data.startswith("del:"))
async def cb_delete_reminder(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await callback.answer()
    await state.clear()
    reminder_id = int(callback.data.split(":")[1])
    deleted = await delete_reminder_by_id(callback.from_user.id, reminder_id)
    notice = "Напоминание удалено." if deleted else "Напоминание уже не активно."
    await show_reminders_screen(bot, callback.from_user.id, state, notice=notice)


# --- Редактирование 1: Изменение текста напоминания ---

@router.callback_query(F.data.startswith("edit:text:"))
async def cb_edit_reminder_text(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await callback.answer()
    reminder_id = int(callback.data.split(":")[2])
    reminder = await get_reminder_by_id(callback.from_user.id, reminder_id)
    if not reminder:
        await show_reminders_screen(
            bot, callback.from_user.id, state, notice="Напоминание уже не активно."
        )
        return

    await state.set_state(ReminderFSM.editing_text)
    await state.update_data(edit_reminder_id=reminder_id)

    text = (
        "Изменение текста напоминания\n\n"
        f"<code>{html.escape(reminder.text)}</code>\n\n"
        "Отправьте новый текст напоминания (или перешлите сообщение из другого чата):"
    )
    await render_panel(
        bot=bot,
        user_id=callback.from_user.id,
        text=text,
        reply_markup=edit_text_cancel_kb(reminder_id),
    )


@router.message(ReminderFSM.editing_text)
async def process_edit_reminder_text(message: Message, state: FSMContext, bot: Bot) -> None:
    new_text = extract_message_text(message)
    if not new_text:
        await safe_delete_message(bot, message.chat.id, message.message_id)
        return

    data = await state.get_data()
    reminder_id = data.get("edit_reminder_id")
    await state.clear()

    if not reminder_id:
        await show_reminders_screen(
            bot, message.from_user.id, state, extra_delete_ids=[message.message_id]
        )
        return

    updated = await update_reminder_text(message.from_user.id, reminder_id, new_text)
    if not updated:
        await show_reminders_screen(
            bot,
            message.from_user.id,
            state,
            notice="Напоминание уже не активно.",
            extra_delete_ids=[message.message_id],
        )
        return

    await show_reminder_edit_card(
        bot,
        message.from_user.id,
        state,
        reminder_id,
        notice="Текст напоминания обновлён.",
        extra_delete_ids=[message.message_id],
    )


# --- Редактирование 2: Изменение даты напоминания ---

async def show_edit_calendar(
    bot: Bot,
    user_id: int,
    reminder_id: int,
    reminder_text: str,
    year: int,
    month: int,
    error_msg: str = "",
    extra_delete_ids: list[int] | None = None,
) -> None:
    user_now, _ = await get_user_now(user_id)
    today = user_now.date()

    err_block = f"{error_msg}\n\n" if error_msg else ""
    text = (
        "Календарь — Выбор новой даты\n"
        f"<code>{html.escape(reminder_text)}</code>\n\n"
        f"{err_block}"
        "Выберите дату в календаре, нажмите на месяц и год в шапке для переключения года "
        "или отправьте дату в чат (ДД.ММ.ГГГГ):"
    )
    kb = build_calendar_kb(
        year=year,
        month=month,
        today=today,
        nav_prefix=f"cal:enav:{reminder_id}",
        ym_prefix=f"cal:eym:{reminder_id}",
        pick_prefix=f"cal:epick:{reminder_id}",
        back_callback=f"edit:date:{reminder_id}",
        plain_home=True,
    )
    await render_panel(
        bot=bot,
        user_id=user_id,
        text=text,
        reply_markup=kb,
        extra_delete_ids=extra_delete_ids,
    )


async def show_edit_ym_picker(
    bot: Bot,
    user_id: int,
    reminder_id: int,
    reminder_text: str,
    year: int,
    current_month: int,
) -> None:
    user_now, _ = await get_user_now(user_id)
    today = user_now.date()

    text = (
        "Быстрый выбор года и месяца\n"
        f"<code>{html.escape(reminder_text)}</code>\n\n"
        "Нажмите «На год вперёд», переключите год стрелками < > или выберите нужный месяц:"
    )
    kb = build_calendar_ym_kb(
        year=year,
        current_month=current_month,
        today=today,
        year_nav_prefix=f"cal:eynav:{reminder_id}",
        month_pick_prefix=f"cal:empick:{reminder_id}",
        plain_home=True,
    )
    await render_panel(
        bot=bot,
        user_id=user_id,
        text=text,
        reply_markup=kb,
    )


@router.callback_query(F.data.startswith("edit:date:"))
async def cb_edit_reminder_date(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await callback.answer()
    reminder_id = int(callback.data.split(":")[2])
    reminder = await get_reminder_by_id(callback.from_user.id, reminder_id)
    if not reminder:
        await show_reminders_screen(
            bot, callback.from_user.id, state, notice="Напоминание уже не активно."
        )
        return

    _, offset_mins = await get_user_now(callback.from_user.id)
    local_dt = reminder.remind_at + timedelta(minutes=offset_mins)

    await state.set_state(ReminderFSM.editing_date)
    await state.update_data(edit_reminder_id=reminder_id)

    text = (
        "Изменение даты напоминания\n"
        f"{local_dt.strftime('%d.%m.%Y')} в {local_dt.strftime('%H:%M')}\n"
        f"<code>{html.escape(reminder.text)}</code>\n\n"
        "Выберите новую дату кнопкой ниже или откройте Календарь:"
    )
    await render_panel(
        bot=bot,
        user_id=callback.from_user.id,
        text=text,
        reply_markup=edit_date_selection_kb(reminder_id),
    )


@router.callback_query(F.data.startswith("cal:enav:"))
async def cb_edit_calendar_nav(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    parts = callback.data.split(":")
    reminder_id = int(parts[2])
    year = int(parts[3])
    month = int(parts[4])
    direction = parts[5]

    reminder = await get_reminder_by_id(callback.from_user.id, reminder_id)
    if not reminder:
        await callback.answer()
        await show_reminders_screen(
            bot, callback.from_user.id, state, notice="Напоминание уже не активно."
        )
        return

    new_year, new_month = step_year_month(year, month, direction)
    user_now, _ = await get_user_now(callback.from_user.id)
    today = user_now.date()
    if (new_year, new_month) < (today.year, today.month):
        await callback.answer("Нельзя выбрать прошедший месяц", show_alert=False)
        return

    await show_edit_calendar(
        bot=bot,
        user_id=callback.from_user.id,
        reminder_id=reminder_id,
        reminder_text=reminder.text,
        year=new_year,
        month=new_month,
    )
    await callback.answer()


@router.callback_query(F.data.startswith("cal:eym:"))
async def cb_edit_calendar_ym_open(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    parts = callback.data.split(":")
    reminder_id = int(parts[2])
    year = int(parts[3])
    month = int(parts[4])

    reminder = await get_reminder_by_id(callback.from_user.id, reminder_id)
    if not reminder:
        await callback.answer()
        await show_reminders_screen(
            bot, callback.from_user.id, state, notice="Напоминание уже не активно."
        )
        return

    await show_edit_ym_picker(
        bot=bot,
        user_id=callback.from_user.id,
        reminder_id=reminder_id,
        reminder_text=reminder.text,
        year=year,
        current_month=month,
    )
    await callback.answer()


@router.callback_query(F.data.startswith("cal:eynav:"))
async def cb_edit_calendar_year_nav(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    parts = callback.data.split(":")
    reminder_id = int(parts[2])
    year = int(parts[3])
    month = int(parts[4])
    direction = parts[5]

    reminder = await get_reminder_by_id(callback.from_user.id, reminder_id)
    if not reminder:
        await callback.answer()
        await show_reminders_screen(
            bot, callback.from_user.id, state, notice="Напоминание уже не активно."
        )
        return

    new_year = year + 1 if direction == "next" else year - 1
    user_now, _ = await get_user_now(callback.from_user.id)
    today = user_now.date()
    if new_year < today.year:
        await callback.answer("Нельзя выбрать прошедший год", show_alert=False)
        return

    await show_edit_ym_picker(
        bot=bot,
        user_id=callback.from_user.id,
        reminder_id=reminder_id,
        reminder_text=reminder.text,
        year=new_year,
        current_month=month,
    )
    await callback.answer()


@router.callback_query(F.data.startswith("cal:empick:"))
async def cb_edit_calendar_month_pick(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    parts = callback.data.split(":")
    reminder_id = int(parts[2])
    year = int(parts[3])
    month = int(parts[4])

    reminder = await get_reminder_by_id(callback.from_user.id, reminder_id)
    if not reminder:
        await callback.answer()
        await show_reminders_screen(
            bot, callback.from_user.id, state, notice="Напоминание уже не активно."
        )
        return

    user_now, _ = await get_user_now(callback.from_user.id)
    today = user_now.date()
    if (year, month) < (today.year, today.month):
        await callback.answer("Нельзя выбрать прошедший месяц", show_alert=False)
        return

    await show_edit_calendar(
        bot=bot,
        user_id=callback.from_user.id,
        reminder_id=reminder_id,
        reminder_text=reminder.text,
        year=year,
        month=month,
    )
    await callback.answer()


@router.callback_query(F.data.startswith("cal:epick:"))
async def cb_edit_calendar_pick(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    parts = callback.data.split(":", 3)
    reminder_id = int(parts[2])
    picked_date = date.fromisoformat(parts[3])

    user_now, _ = await get_user_now(callback.from_user.id)
    today = user_now.date()
    if picked_date < today:
        await callback.answer("Эта дата уже в прошлом", show_alert=False)
        return

    await callback.answer()
    await apply_edited_date(bot, callback.from_user.id, state, reminder_id, picked_date)


async def show_edit_hours_picker(
    bot: Bot,
    user_id: int,
    state: FSMContext,
    reminder_id: int,
    error_msg: str = "",
    extra_delete_ids: list[int] | None = None,
) -> None:
    reminder = await get_reminder_by_id(user_id, reminder_id)
    if not reminder:
        await state.clear()
        await show_reminders_screen(
            bot,
            user_id,
            state,
            notice="Напоминание уже не активно.",
            extra_delete_ids=extra_delete_ids,
        )
        return

    data = await state.get_data()
    pending_date_iso = data.get("pending_edit_date")
    user_now, offset_mins = await get_user_now(user_id)
    old_local_dt = reminder.remind_at + timedelta(minutes=offset_mins)
    target_date = date.fromisoformat(pending_date_iso) if pending_date_iso else old_local_dt.date()

    choice_type = "today" if target_date == user_now.date() else "custom"
    _, _, skip_btn_text = compute_skip_time_button(user_now, target_date, choice_type)

    err_block = f"{error_msg}\n\n" if error_msg else ""
    text = (
        "Изменение времени напоминания — Выбор часа\n"
        f"Дата: {target_date.strftime('%d.%m.%Y')}\n"
        f"<code>{html.escape(reminder.text)}</code>\n\n"
        f"{err_block}"
        f"Нажмите «{skip_btn_text}», выберите час в сетке ниже или отправьте время в чат:"
    )
    kb = build_hours_picker_kb(
        target_date=target_date,
        user_now=user_now,
        skip_btn_text=skip_btn_text,
        skip_callback=f"etime:skip:{reminder_id}",
        hour_prefix=f"etime:hour:{reminder_id}",
        change_date_callback=f"edit:date:{reminder_id}",
        back_callback=f"rem:open:{reminder_id}",
        plain_style=True,
    )
    await render_panel(
        bot=bot,
        user_id=user_id,
        text=text,
        reply_markup=kb,
        extra_delete_ids=extra_delete_ids,
    )


async def show_edit_minutes_drum(
    bot: Bot,
    user_id: int,
    state: FSMContext,
    reminder_id: int,
    hour: int,
    minute: int,
) -> None:
    reminder = await get_reminder_by_id(user_id, reminder_id)
    if not reminder:
        await state.clear()
        await show_reminders_screen(bot, user_id, state, notice="Напоминание уже не активно.")
        return

    data = await state.get_data()
    pending_date_iso = data.get("pending_edit_date")
    user_now, offset_mins = await get_user_now(user_id)
    old_local_dt = reminder.remind_at + timedelta(minutes=offset_mins)
    target_date = date.fromisoformat(pending_date_iso) if pending_date_iso else old_local_dt.date()

    text = (
        "Изменение времени напоминания — Выбор минут\n"
        f"Дата: {target_date.strftime('%d.%m.%Y')}\n"
        f"Выбранное время: {hour:02d}:{minute:02d}\n"
        f"<code>{html.escape(reminder.text)}</code>\n\n"
        "Выберите время в сетке ниже или подкрутите барабан (▲/▼):"
    )
    kb = build_minutes_drum_kb(
        hour=hour,
        minute=minute,
        target_date=target_date,
        user_now=user_now,
        drum_prefix=f"etime:drum:{reminder_id}",
        pick_prefix=f"etime:pick:{reminder_id}",
        back_to_hours_callback=f"etime:back_hours:{reminder_id}",
        back_callback=f"rem:open:{reminder_id}",
        plain_style=True,
    )
    await render_panel(
        bot=bot,
        user_id=user_id,
        text=text,
        reply_markup=kb,
    )


async def apply_edited_date(
    bot: Bot,
    user_id: int,
    state: FSMContext,
    reminder_id: int,
    new_date: date,
    extra_delete_ids: list[int] | None = None,
) -> None:
    reminder = await get_reminder_by_id(user_id, reminder_id)
    if not reminder:
        await state.clear()
        await show_reminders_screen(
            bot,
            user_id,
            state,
            notice="Напоминание уже не активно.",
            extra_delete_ids=extra_delete_ids,
        )
        return

    user_now, offset_mins = await get_user_now(user_id)
    current_local_dt = user_now.replace(tzinfo=None)
    old_local_dt = reminder.remind_at + timedelta(minutes=offset_mins)
    existing_time = old_local_dt.time()

    new_local_dt = datetime.combine(new_date, existing_time)

    if new_local_dt <= current_local_dt:
        await state.set_state(ReminderFSM.editing_time)
        await state.update_data(
            edit_reminder_id=reminder_id,
            pending_edit_date=new_date.isoformat(),
        )
        await show_edit_hours_picker(
            bot,
            user_id,
            state,
            reminder_id,
            error_msg=f"Прежнее время ({existing_time.strftime('%H:%M')}) сегодня уже прошло.",
            extra_delete_ids=extra_delete_ids,
        )
        return

    new_utc_dt = new_local_dt - timedelta(minutes=offset_mins)
    await update_reminder_datetime(user_id, reminder_id, new_utc_dt)
    await state.clear()

    await show_reminder_edit_card(
        bot,
        user_id,
        state,
        reminder_id,
        notice=f"Дата изменена на {new_date.strftime('%d.%m.%Y')}.",
        extra_delete_ids=extra_delete_ids,
    )


@router.callback_query(F.data.startswith("edate:"))
async def cb_edit_date_buttons(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await callback.answer()
    parts = callback.data.split(":")
    action = parts[1]
    reminder_id = int(parts[2])

    user_now, _ = await get_user_now(callback.from_user.id)
    today = user_now.date()

    if action == "custom":
        reminder = await get_reminder_by_id(callback.from_user.id, reminder_id)
        if not reminder:
            await show_reminders_screen(
                bot, callback.from_user.id, state, notice="Напоминание уже не активно."
            )
            return

        await state.set_state(ReminderFSM.editing_date)
        await state.update_data(edit_reminder_id=reminder_id)
        await show_edit_calendar(
            bot=bot,
            user_id=callback.from_user.id,
            reminder_id=reminder_id,
            reminder_text=reminder.text,
            year=today.year,
            month=today.month,
        )
        return

    if action == "today":
        target_date = today
    elif action == "1d":
        target_date = today + timedelta(days=1)
    elif action == "1w":
        target_date = today + timedelta(days=7)
    else:
        target_date = add_one_month(today)

    await apply_edited_date(bot, callback.from_user.id, state, reminder_id, target_date)


@router.message(ReminderFSM.editing_date, F.text)
async def process_edit_date_input(message: Message, state: FSMContext, bot: Bot) -> None:
    data = await state.get_data()
    reminder_id = data.get("edit_reminder_id")
    if not reminder_id:
        await state.clear()
        await show_reminders_screen(
            bot, message.from_user.id, state, extra_delete_ids=[message.message_id]
        )
        return

    reminder = await get_reminder_by_id(message.from_user.id, reminder_id)
    if not reminder:
        await state.clear()
        await show_reminders_screen(
            bot,
            message.from_user.id,
            state,
            notice="Напоминание уже не активно.",
            extra_delete_ids=[message.message_id],
        )
        return

    user_now, _ = await get_user_now(message.from_user.id)
    today = user_now.date()
    parsed_date = parse_user_date(message.text, today)

    if not parsed_date:
        await show_edit_calendar(
            bot=bot,
            user_id=message.from_user.id,
            reminder_id=reminder_id,
            reminder_text=reminder.text,
            year=today.year,
            month=today.month,
            error_msg="Неверный формат даты. Выберите дату в календаре или введите ДД.ММ.ГГГГ.",
            extra_delete_ids=[message.message_id],
        )
        return

    if parsed_date < today:
        await show_edit_calendar(
            bot=bot,
            user_id=message.from_user.id,
            reminder_id=reminder_id,
            reminder_text=reminder.text,
            year=today.year,
            month=today.month,
            error_msg="Указанная дата уже в прошлом. Выберите актуальную дату.",
            extra_delete_ids=[message.message_id],
        )
        return

    await apply_edited_date(
        bot,
        message.from_user.id,
        state,
        reminder_id,
        parsed_date,
        extra_delete_ids=[message.message_id],
    )


@router.callback_query(F.data.startswith("edit:time:"))
async def cb_edit_reminder_time(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await callback.answer()
    reminder_id = int(callback.data.split(":")[2])
    await state.set_state(ReminderFSM.editing_time)
    await state.update_data(edit_reminder_id=reminder_id, pending_edit_date=None)
    await show_edit_hours_picker(bot, callback.from_user.id, state, reminder_id)


@router.callback_query(F.data.startswith("etime:back_hours:"))
async def cb_edit_time_back_hours(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await callback.answer()
    reminder_id = int(callback.data.split(":")[2])
    await show_edit_hours_picker(bot, callback.from_user.id, state, reminder_id)


@router.callback_query(F.data.startswith("etime:hour:"))
async def cb_edit_time_pick_hour(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await callback.answer()
    parts = callback.data.split(":")
    reminder_id = int(parts[2])
    hour = int(parts[3])

    reminder = await get_reminder_by_id(callback.from_user.id, reminder_id)
    if not reminder:
        await show_reminders_screen(
            bot, callback.from_user.id, state, notice="Напоминание уже не активно."
        )
        return

    data = await state.get_data()
    pending_date_iso = data.get("pending_edit_date")
    user_now, offset_mins = await get_user_now(callback.from_user.id)
    old_local_dt = reminder.remind_at + timedelta(minutes=offset_mins)
    target_date = date.fromisoformat(pending_date_iso) if pending_date_iso else old_local_dt.date()

    start_min = default_minute_for_hour(user_now, target_date, hour)
    await show_edit_minutes_drum(bot, callback.from_user.id, state, reminder_id, hour, start_min)


@router.callback_query(F.data.startswith("etime:drum:"))
async def cb_edit_time_drum_spin(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await callback.answer()
    parts = callback.data.split(":")
    reminder_id = int(parts[2])
    hour = int(parts[3])
    minute = int(parts[4])
    await show_edit_minutes_drum(bot, callback.from_user.id, state, reminder_id, hour, minute)


@router.callback_query(F.data.startswith("etime:pick:"))
async def cb_edit_time_pick_confirm(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await callback.answer()
    parts = callback.data.split(":")
    reminder_id = int(parts[2])
    hour = int(parts[3])
    minute = int(parts[4])
    await apply_edited_time(bot, callback.from_user.id, state, reminder_id, time(hour, minute))


async def apply_edited_time(
    bot: Bot,
    user_id: int,
    state: FSMContext,
    reminder_id: int,
    chosen_time: time,
    extra_delete_ids: list[int] | None = None,
) -> None:
    reminder = await get_reminder_by_id(user_id, reminder_id)
    if not reminder:
        await state.clear()
        await show_reminders_screen(
            bot,
            user_id,
            state,
            notice="Напоминание уже не активно.",
            extra_delete_ids=extra_delete_ids,
        )
        return

    data = await state.get_data()
    pending_date_iso = data.get("pending_edit_date")

    user_now, offset_mins = await get_user_now(user_id)
    current_local_dt = user_now.replace(tzinfo=None)
    old_local_dt = reminder.remind_at + timedelta(minutes=offset_mins)
    tz_label = format_tz_label(offset_mins)

    target_date = date.fromisoformat(pending_date_iso) if pending_date_iso else old_local_dt.date()
    new_local_dt = datetime.combine(target_date, chosen_time)

    if new_local_dt <= current_local_dt:
        await show_edit_hours_picker(
            bot,
            user_id,
            state,
            reminder_id,
            error_msg="Выбранное время уже прошло. Укажите более позднее время",
            extra_delete_ids=extra_delete_ids,
        )
        return

    new_utc_dt = new_local_dt - timedelta(minutes=offset_mins)
    await update_reminder_datetime(user_id, reminder_id, new_utc_dt)
    await state.clear()

    await show_reminder_edit_card(
        bot,
        user_id,
        state,
        reminder_id,
        notice=f"Время напоминания изменено на {new_local_dt.strftime('%d.%m.%Y в %H:%M')} ({tz_label}).",
        extra_delete_ids=extra_delete_ids,
    )


@router.callback_query(F.data.startswith("etime:skip:"))
async def cb_edit_time_skip(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await callback.answer()
    reminder_id = int(callback.data.split(":")[2])

    reminder = await get_reminder_by_id(callback.from_user.id, reminder_id)
    if not reminder:
        await show_reminders_screen(
            bot, callback.from_user.id, state, notice="Напоминание уже не активно."
        )
        return

    data = await state.get_data()
    pending_date_iso = data.get("pending_edit_date")
    user_now, offset_mins = await get_user_now(callback.from_user.id)
    old_local_dt = reminder.remind_at + timedelta(minutes=offset_mins)
    target_date = date.fromisoformat(pending_date_iso) if pending_date_iso else old_local_dt.date()

    choice_type = "today" if target_date == user_now.date() else "custom"
    resolved_date, resolved_time, _ = compute_skip_time_button(
        user_now, target_date, choice_type
    )
    if resolved_date != target_date:
        await state.update_data(pending_edit_date=resolved_date.isoformat())

    await apply_edited_time(bot, callback.from_user.id, state, reminder_id, resolved_time)


@router.message(ReminderFSM.editing_time, F.text)
async def process_edit_time_input(message: Message, state: FSMContext, bot: Bot) -> None:
    data = await state.get_data()
    reminder_id = data.get("edit_reminder_id")
    if not reminder_id:
        await state.clear()
        await show_reminders_screen(
            bot, message.from_user.id, state, extra_delete_ids=[message.message_id]
        )
        return

    parsed_time = parse_user_time(message.text)
    if not parsed_time:
        await show_edit_hours_picker(
            bot,
            message.from_user.id,
            state,
            reminder_id,
            error_msg="Неверный формат времени. Выберите час кнопкой или введите ЧЧ:ММ.",
            extra_delete_ids=[message.message_id],
        )
        return

    await apply_edited_time(
        bot,
        message.from_user.id,
        state,
        reminder_id,
        parsed_time,
        extra_delete_ids=[message.message_id],
    )


# --- Редактирование 4: Изменение периодичности напоминания ---

@router.callback_query(F.data.startswith("edit:rec:"))
async def cb_edit_reminder_rec(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await callback.answer()
    reminder_id = int(callback.data.split(":")[2])
    reminder = await get_reminder_by_id(callback.from_user.id, reminder_id)
    if not reminder:
        await show_reminders_screen(
            bot, callback.from_user.id, state, notice="Напоминание уже не активно."
        )
        return

    rec_label = format_recurrence_label(reminder.recurrence)
    text = (
        "Изменение периодичности напоминания\n"
        f"Повтор: {rec_label}\n"
        f"<code>{html.escape(reminder.text)}</code>\n\n"
        "Выберите режим срабатывания:"
    )
    await render_panel(
        bot=bot,
        user_id=callback.from_user.id,
        text=text,
        reply_markup=edit_recurrence_type_kb(reminder_id),
    )


@router.callback_query(F.data.startswith("erec:menu:"))
async def cb_edit_reminder_rec_menu(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await callback.answer()
    reminder_id = int(callback.data.split(":")[2])
    reminder = await get_reminder_by_id(callback.from_user.id, reminder_id)
    if not reminder:
        await show_reminders_screen(
            bot, callback.from_user.id, state, notice="Напоминание уже не активно."
        )
        return

    text = (
        "Выбор периодичности повторения\n"
        f"<code>{html.escape(reminder.text)}</code>\n\n"
        "Выберите, с какой периодичностью присылать напоминание:"
    )
    await render_panel(
        bot=bot,
        user_id=callback.from_user.id,
        text=text,
        reply_markup=edit_recurrence_period_kb(reminder_id),
    )


@router.callback_query(F.data.startswith("erec:once:"))
async def cb_edit_reminder_rec_once(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await callback.answer()
    reminder_id = int(callback.data.split(":")[2])
    await update_reminder_recurrence(callback.from_user.id, reminder_id, "once")
    await show_reminder_edit_card(
        bot,
        callback.from_user.id,
        state,
        reminder_id,
        notice="Установлен режим: Один раз.",
    )


@router.callback_query(F.data.startswith("erec_set:"))
async def cb_edit_reminder_rec_set(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await callback.answer()
    parts = callback.data.split(":")
    rec_code = parts[1]
    reminder_id = int(parts[2])
    await update_reminder_recurrence(callback.from_user.id, reminder_id, rec_code)
    rec_label = format_recurrence_label(rec_code)
    await show_reminder_edit_card(
        bot,
        callback.from_user.id,
        state,
        reminder_id,
        notice=f"Периодичность изменена: {rec_label}.",
    )
