import html
from datetime import datetime, date, time, timedelta
from aiogram import Router, Bot, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery

from database import (
    set_panel_message_id,
    add_tracked_messages_batch,
    get_active_reminders,
    get_reminder_by_id,
    update_reminder_text,
    update_reminder_datetime,
    update_reminder_recurrence,
    delete_reminder_by_id,
    get_user_now,
    format_tz_label,
    format_recurrence_label,
)
from keyboards import (
    reminders_section_kb,
    reminder_number_prompt_kb,
    reminder_edit_menu_kb,
    edit_text_cancel_kb,
    edit_date_selection_kb,
    edit_time_selection_kb,
    edit_recurrence_type_kb,
    edit_recurrence_period_kb,
)
from .states import ReminderFSM
from .common import (
    add_one_month,
    parse_user_date,
    parse_user_time,
    extract_message_text,
    safe_delete_message,
    clear_chat_window,
    render_panel,
)

router = Router()


async def show_reminders_screen(
    bot: Bot, user_id: int, state: FSMContext, notice: str = ""
) -> None:
    # Полное мгновенное пакетное очищение текущего окна (/clear) одним вызовом
    await clear_chat_window(bot, user_id)

    reminders = await get_active_reminders(user_id)
    _, offset_mins = await get_user_now(user_id)
    delta = timedelta(minutes=offset_mins)
    tz_label = format_tz_label(offset_mins)

    reminder_map: dict[str, int] = {}
    new_tracked_ids: list[int] = []

    for idx, r in enumerate(reminders, start=1):
        local_dt = r.remind_at + delta
        day_str = local_dt.strftime("%d.%m.%Y")
        time_str = local_dt.strftime("%H:%M")
        rec_str = format_recurrence_label(r.recurrence)
        safe_text = html.escape(r.text)

        item_text = (
            f"Напоминание №{idx}\n"
            f"Дата: {day_str}\n"
            f"Время: {time_str} ({tz_label})\n"
            f"Повтор: {rec_str}\n"
            f"{safe_text}"
        )
        sent_item = await bot.send_message(chat_id=user_id, text=item_text)
        new_tracked_ids.append(sent_item.message_id)
        reminder_map[str(idx)] = r.id

    if new_tracked_ids:
        await add_tracked_messages_batch(user_id, new_tracked_ids)

    await state.update_data(reminder_map=reminder_map)

    lines = [f"Раздел «Напоминания» ({tz_label})"]
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
    )
    await set_panel_message_id(user_id, sent_panel.message_id)


@router.message(Command("reminders", ignore_case=True))
async def cmd_reminders(message: Message, state: FSMContext, bot: Bot) -> None:
    await state.clear()
    await clear_chat_window(bot, message.from_user.id, extra_ids=[message.message_id])
    await show_reminders_screen(bot, message.from_user.id, state)


@router.callback_query(F.data == "menu:list")
async def cb_menu_list(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await callback.answer()
    await state.clear()
    await show_reminders_screen(bot, callback.from_user.id, state)


# --- Нажатие «Редактировать напоминания» -> Ввод номера напоминания ---

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
    # Мгновенно очищаем всё окно (включая введённый номер и карточки) одним пакетным запросом
    await clear_chat_window(bot, message.from_user.id, extra_ids=[message.message_id])
    await show_reminder_edit_card(bot, message.from_user.id, state, reminder_id, number_label=raw_num)


# --- Карточка выбранного напоминания ---

async def show_reminder_edit_card(
    bot: Bot,
    user_id: int,
    state: FSMContext,
    reminder_id: int,
    notice: str = "",
    number_label: str = "",
) -> None:
    reminder = await get_reminder_by_id(user_id, reminder_id)
    if not reminder:
        await show_reminders_screen(
            bot, user_id, state, notice="Напоминание не найдено или уже отправлено."
        )
        return

    _, offset_mins = await get_user_now(user_id)
    local_dt = reminder.remind_at + timedelta(minutes=offset_mins)
    tz_label = format_tz_label(offset_mins)
    rec_label = format_recurrence_label(reminder.recurrence)

    title_num = f" №{number_label}" if number_label else ""
    notice_block = f"{notice}\n\n" if notice else ""
    text = (
        f"Управление напоминанием{title_num}\n"
        f"{notice_block}"
        f"Дата: {local_dt.strftime('%d.%m.%Y')}\n"
        f"Время: {local_dt.strftime('%H:%M')} ({tz_label})\n"
        f"Повтор: {rec_label}\n"
        f"{html.escape(reminder.text)}\n\n"
        "Выберите нужное действие:"
    )
    await render_panel(
        bot=bot,
        user_id=user_id,
        text=text,
        reply_markup=reminder_edit_menu_kb(reminder.id),
        cleanup=True,
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
        f"{html.escape(reminder.text)}\n\n"
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
    await safe_delete_message(bot, message.chat.id, message.message_id)
    new_text = extract_message_text(message)
    if not new_text:
        return

    data = await state.get_data()
    reminder_id = data.get("edit_reminder_id")
    await state.clear()

    if not reminder_id:
        await show_reminders_screen(bot, message.from_user.id, state)
        return

    updated = await update_reminder_text(message.from_user.id, reminder_id, new_text)
    if not updated:
        await show_reminders_screen(
            bot, message.from_user.id, state, notice="Напоминание уже не активно."
        )
        return

    await show_reminder_edit_card(
        bot,
        message.from_user.id,
        state,
        reminder_id,
        notice="Текст напоминания обновлён.",
    )


# --- Редактирование 2: Изменение даты напоминания ---

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
    tz_label = format_tz_label(offset_mins)

    await state.set_state(ReminderFSM.editing_date)
    await state.update_data(edit_reminder_id=reminder_id)

    text = (
        "Изменение даты напоминания\n"
        f"Дата: {local_dt.strftime('%d.%m.%Y')}\n"
        f"Время: {local_dt.strftime('%H:%M')} ({tz_label})\n"
        f"{html.escape(reminder.text)}\n\n"
        "Выберите новую дату кнопкой ниже или отправьте дату в чат (ДД.ММ.ГГГГ или ДД.ММ):"
    )
    await render_panel(
        bot=bot,
        user_id=callback.from_user.id,
        text=text,
        reply_markup=edit_date_selection_kb(reminder_id),
    )


async def apply_edited_date(
    bot: Bot, user_id: int, state: FSMContext, reminder_id: int, new_date: date
) -> None:
    reminder = await get_reminder_by_id(user_id, reminder_id)
    if not reminder:
        await state.clear()
        await show_reminders_screen(bot, user_id, state, notice="Напоминание уже не активно.")
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
        text = (
            "Укажите новое время напоминания\n"
            f"Новая дата: {new_date.strftime('%d.%m.%Y')}\n"
            f"{html.escape(reminder.text)}\n\n"
            f"Прежнее время ({existing_time.strftime('%H:%M')}) сегодня уже прошло.\n"
            "Введите новое время в формате ЧЧ:ММ (или нажмите «Установить 15:00»):"
        )
        await render_panel(bot, user_id, text, edit_time_selection_kb(reminder_id))
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
        example_date = (today + timedelta(days=3)).strftime("%d.%m.%Y")
        text = (
            "Ввод новой даты напоминания\n"
            f"{html.escape(reminder.text)}\n\n"
            f"Отправьте новую дату в формате ДД.ММ.ГГГГ или ДД.ММ (например: {example_date}):"
        )
        await render_panel(bot, callback.from_user.id, text, edit_date_selection_kb(reminder_id))
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
    await safe_delete_message(bot, message.chat.id, message.message_id)
    data = await state.get_data()
    reminder_id = data.get("edit_reminder_id")
    if not reminder_id:
        await state.clear()
        await show_reminders_screen(bot, message.from_user.id, state)
        return

    reminder = await get_reminder_by_id(message.from_user.id, reminder_id)
    if not reminder:
        await state.clear()
        await show_reminders_screen(
            bot, message.from_user.id, state, notice="Напоминание уже не активно."
        )
        return

    user_now, _ = await get_user_now(message.from_user.id)
    today = user_now.date()
    parsed_date = parse_user_date(message.text, today)

    if not parsed_date:
        text = (
            "Изменение даты напоминания\n"
            f"{html.escape(reminder.text)}\n\n"
            "Неверный формат даты.\n"
            "Введите дату в формате ДД.ММ.ГГГГ (например, 25.12.2026) или выберите кнопку ниже:"
        )
        await render_panel(bot, message.from_user.id, text, edit_date_selection_kb(reminder_id))
        return

    if parsed_date < today:
        text = (
            "Изменение даты напоминания\n"
            f"{html.escape(reminder.text)}\n\n"
            "Указанная дата уже в прошлом.\n"
            "Введите актуальную дату или выберите кнопку ниже:"
        )
        await render_panel(bot, message.from_user.id, text, edit_date_selection_kb(reminder_id))
        return

    await apply_edited_date(bot, message.from_user.id, state, reminder_id, parsed_date)


# --- Редактирование 3: Изменение времени напоминания ---

@router.callback_query(F.data.startswith("edit:time:"))
async def cb_edit_reminder_time(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
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
    tz_label = format_tz_label(offset_mins)

    await state.set_state(ReminderFSM.editing_time)
    await state.update_data(edit_reminder_id=reminder_id, pending_edit_date=None)

    text = (
        "Изменение времени напоминания\n"
        f"Дата: {local_dt.strftime('%d.%m.%Y')}\n"
        f"Время: {local_dt.strftime('%H:%M')} ({tz_label})\n"
        f"{html.escape(reminder.text)}\n\n"
        "Введите новое время в формате ЧЧ:ММ (например, 09:30 или 18:45) "
        "или нажмите кнопку «Установить 15:00»:"
    )
    await render_panel(
        bot=bot,
        user_id=callback.from_user.id,
        text=text,
        reply_markup=edit_time_selection_kb(reminder_id),
    )


async def apply_edited_time(
    bot: Bot, user_id: int, state: FSMContext, reminder_id: int, chosen_time: time
) -> None:
    reminder = await get_reminder_by_id(user_id, reminder_id)
    if not reminder:
        await state.clear()
        await show_reminders_screen(bot, user_id, state, notice="Напоминание уже не активно.")
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
        text = (
            "Изменение времени напоминания\n"
            f"Дата: {target_date.strftime('%d.%m.%Y')}\n"
            f"{html.escape(reminder.text)}\n\n"
            "Выбранное время уже в прошлом.\n"
            "Пожалуйста, укажите более позднее время в формате ЧЧ:ММ:"
        )
        await render_panel(bot, user_id, text, edit_time_selection_kb(reminder_id))
        return

    new_utc_dt = new_local_dt - timedelta(minutes=offset_mins)
    await update_reminder_datetime(user_id, reminder_id, new_utc_dt)
    await state.clear()

    await show_reminder_edit_card(
        bot,
        user_id,
        state,
        reminder_id,
        notice=f"Время напоминания изменено на {new_local_dt.strftime('%d.%m.%Y %H:%M')} ({tz_label}).",
    )


@router.callback_query(F.data.startswith("etime:skip:"))
async def cb_edit_time_skip(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await callback.answer()
    reminder_id = int(callback.data.split(":")[2])
    await apply_edited_time(bot, callback.from_user.id, state, reminder_id, time(15, 0))


@router.message(ReminderFSM.editing_time, F.text)
async def process_edit_time_input(message: Message, state: FSMContext, bot: Bot) -> None:
    await safe_delete_message(bot, message.chat.id, message.message_id)
    data = await state.get_data()
    reminder_id = data.get("edit_reminder_id")
    if not reminder_id:
        await state.clear()
        await show_reminders_screen(bot, message.from_user.id, state)
        return

    parsed_time = parse_user_time(message.text)
    if not parsed_time:
        reminder = await get_reminder_by_id(message.from_user.id, reminder_id)
        if not reminder:
            await state.clear()
            await show_reminders_screen(
                bot, message.from_user.id, state, notice="Напоминание уже не активно."
            )
            return
        text = (
            "Изменение времени напоминания\n"
            f"{html.escape(reminder.text)}\n\n"
            "Неверный формат времени.\n"
            "Введите время в формате ЧЧ:ММ (например, 14:30):"
        )
        await render_panel(bot, message.from_user.id, text, edit_time_selection_kb(reminder_id))
        return

    await apply_edited_time(bot, message.from_user.id, state, reminder_id, parsed_time)


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
        f"{html.escape(reminder.text)}\n\n"
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
        f"{html.escape(reminder.text)}\n\n"
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
