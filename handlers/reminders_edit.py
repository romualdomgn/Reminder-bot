import asyncio
import html
from datetime import datetime, date, time, timedelta
from aiogram import Router, Bot, F
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery

from config import (
    set_last_deleted_reminder,
    pop_last_deleted_reminder,
    get_rendered_reminders_state,
    set_rendered_reminders_state,
    clear_rendered_reminders_state,
)
from database import (
    get_panel_message_id,
    set_panel_message_id,
    add_tracked_messages_batch,
    remove_tracked_message,
    has_tracked_messages,
    pop_all_window_messages,
    create_reminder,
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
    build_calendar_kb,
    build_calendar_ym_kb,
    build_hours_picker_kb,
    build_minutes_drum_kb,
    reminders_section_kb,
    reminders_edit_select_kb,
    get_reminder_grid_page_count,
    reminder_edit_menu_kb,
    edit_text_cancel_kb,
    edit_date_selection_kb,
    edit_recurrence_type_kb,
    edit_recurrence_period_kb,
)
from .states import ReminderFSM
from .common import (
    RU_MONTHS_GENITIVE,
    RU_WEEKDAYS,
    add_months,
    add_one_month,
    add_one_year,
    step_year_month,
    format_date_with_weekday,
    parse_user_date,
    parse_user_time,
    extract_message_text,
    safe_delete_message,
    safe_delete_messages_batch,
    safe_answer_callback,
    render_panel,
)
from .reminders_create import compute_skip_time_button, default_minute_for_hour

router = Router()


def _reminders_signature(reminders: list) -> tuple:
    return tuple((r.id, r.remind_at, r.recurrence, r.text) for r in reminders)


def _mark_panel_not_last_reminder(user_id: int) -> None:
    state_info = get_rendered_reminders_state(user_id)
    if state_info is not None:
        state_info["panel_is_last_reminder"] = False


def _is_reply_to_reminder_card(message: Message) -> bool:
    if not message.from_user or not message.reply_to_message:
        return False
    state_info = get_rendered_reminders_state(message.from_user.id)
    if not state_info:
        return False
    replied_id = message.reply_to_message.message_id
    msg_map = state_info.get("msg_map") or {}
    if replied_id not in msg_map:
        return False
    if replied_id == state_info.get("panel_id") and not state_info.get("panel_is_last_reminder", True):
        return False
    return True


def _format_header_day_ru(target_date: date) -> str:
    return (
        f"{RU_WEEKDAYS[target_date.weekday()]}, "
        f"{target_date.day} {RU_MONTHS_GENITIVE[target_date.month]}"
    )


def _is_short_date_interval(target_date: date, today: date) -> bool:
    days_diff = (target_date - today).days
    return 0 <= days_diff <= 2


def _format_reminder_item_text(
    reminder: object,
    local_dt: datetime,
    today: date,
    idx: int | None = None,
) -> str:
    time_str = local_dt.strftime("%H:%M")
    rec_str = format_recurrence_label(reminder.recurrence)
    rec_line = f"\n{rec_str}" if rec_str and reminder.recurrence != "once" else ""

    if _is_short_date_interval(local_dt.date(), today):
        dt_part = f"В {time_str}"
    else:
        day_str = format_date_with_weekday(local_dt.date())
        dt_part = f"{day_str}, в {time_str}"

    prefix = f"№{idx} - " if idx is not None else ""
    return f"{prefix}{dt_part}{rec_line}\n{reminder.text}"


def _get_reminder_group_header(
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


async def _sync_non_panel_cards_numbers(
    bot: Bot,
    user_id: int,
    state_info: dict,
    show_numbers: bool,
) -> bool:
    if bool(state_info.get("numbers_visible")) == show_numbers:
        return True

    panel_id = state_info.get("panel_id")
    targets = [
        it for it in (state_info.get("items") or [])
        if it["msg_id"] != panel_id
    ]
    if not targets:
        state_info["numbers_visible"] = show_numbers
        return True

    sem = asyncio.Semaphore(5)
    all_ok = True

    async def _edit_one(item: dict) -> None:
        nonlocal all_ok
        target_text = item["numbered_text"] if show_numbers else item["plain_text"]
        async with sem:
            try:
                await bot.edit_message_text(
                    chat_id=user_id,
                    message_id=item["msg_id"],
                    text=target_text,
                )
            except TelegramBadRequest as e:
                if "message is not modified" not in str(e).lower():
                    all_ok = False
            except Exception:
                all_ok = False

    await asyncio.gather(*(_edit_one(it) for it in targets))
    state_info["numbers_visible"] = show_numbers
    return all_ok


async def show_reminders_screen(
    bot: Bot,
    user_id: int,
    state: FSMContext,
    notice: str = "",
    extra_delete_ids: list[int] | None = None,
    can_undo_delete: bool = False,
) -> None:
    old_ids = await pop_all_window_messages(user_id)
    if extra_delete_ids:
        old_ids.extend(extra_delete_ids)

    reminders = await get_active_reminders(user_id)
    user_now, offset_mins = await get_user_now(user_id)
    today = user_now.date()
    d_1m = add_months(today, 1)
    d_3m = add_months(today, 3)
    d_6m = add_months(today, 6)
    d_12m = add_months(today, 12)
    delta = timedelta(minutes=offset_mins)

    prepared: list[tuple[int, object, datetime]] = []
    has_named_groups = False
    for idx, r in enumerate(reminders, start=1):
        local_dt = r.remind_at + delta
        target_date = local_dt.date()
        days_diff = (target_date - today).days
        if (
            0 <= days_diff < 14
            or (d_1m <= target_date < d_3m)
            or target_date >= d_6m
        ):
            has_named_groups = True
        prepared.append((idx, r, local_dt))

    new_tracked_ids: list[int] = []
    msg_map: dict[int, tuple[int, int]] = {}
    rendered_items: list[dict] = []
    header_ids: set[int] = set()
    last_header: str | None = None
    current_header_msg_id: int | None = None

    try:
        if not prepared:
            empty_lines: list[str] = []
            if notice:
                empty_lines.append(notice)
            empty_lines.append("У вас пока нет активных напоминаний.")
            sent_panel = await bot.send_message(
                chat_id=user_id,
                text="\n\n".join(empty_lines),
                reply_markup=reminders_section_kb(
                    has_reminders=False,
                    can_undo_delete=can_undo_delete,
                ),
                disable_notification=True,
            )
            await set_panel_message_id(user_id, sent_panel.message_id)
            clear_rendered_reminders_state(user_id)
            return

        total_items = len(prepared)
        for pos, (idx, r, local_dt) in enumerate(prepared):
            header = _get_reminder_group_header(
                target_date=local_dt.date(),
                today=today,
                d_1m=d_1m,
                d_3m=d_3m,
                d_6m=d_6m,
                d_12m=d_12m,
                has_named_groups=has_named_groups,
            )
            if header is None:
                current_header_msg_id = None
                last_header = None
            elif header != last_header:
                sent_header = await bot.send_message(
                    chat_id=user_id,
                    text=header,
                    disable_notification=True,
                )
                new_tracked_ids.append(sent_header.message_id)
                header_ids.add(sent_header.message_id)
                current_header_msg_id = sent_header.message_id
                last_header = header

            plain_text = _format_reminder_item_text(r, local_dt, today, idx=None)
            numbered_text = _format_reminder_item_text(r, local_dt, today, idx=idx)
            is_last = pos == total_items - 1
            if is_last:
                sent_panel = await bot.send_message(
                    chat_id=user_id,
                    text=plain_text,
                    reply_markup=reminders_section_kb(
                        has_reminders=True,
                        can_undo_delete=can_undo_delete,
                    ),
                    disable_notification=True,
                )
                msg_map[sent_panel.message_id] = (r.id, idx)
                rendered_items.append(
                    {
                        "msg_id": sent_panel.message_id,
                        "reminder_id": r.id,
                        "idx": idx,
                        "plain_text": plain_text,
                        "numbered_text": numbered_text,
                        "header_msg_id": current_header_msg_id,
                    }
                )
                await set_panel_message_id(user_id, sent_panel.message_id)
                set_rendered_reminders_state(
                    user_id,
                    {
                        "panel_id": sent_panel.message_id,
                        "sig": _reminders_signature(reminders),
                        "last_text": plain_text,
                        "last_numbered_text": numbered_text,
                        "had_tracked": bool(new_tracked_ids),
                        "msg_map": msg_map,
                        "items": rendered_items,
                        "header_ids": header_ids,
                        "panel_is_last_reminder": True,
                        "numbers_visible": False,
                    },
                )
            else:
                sent_item = await bot.send_message(
                    chat_id=user_id,
                    text=plain_text,
                    disable_notification=True,
                )
                new_tracked_ids.append(sent_item.message_id)
                msg_map[sent_item.message_id] = (r.id, idx)
                rendered_items.append(
                    {
                        "msg_id": sent_item.message_id,
                        "reminder_id": r.id,
                        "idx": idx,
                        "plain_text": plain_text,
                        "numbered_text": numbered_text,
                        "header_msg_id": current_header_msg_id,
                    }
                )
    finally:
        if new_tracked_ids:
            await add_tracked_messages_batch(user_id, new_tracked_ids)
        if old_ids:
            await safe_delete_messages_batch(bot, user_id, old_ids)


async def show_reminders_panel_only(
    bot: Bot,
    user_id: int,
    state: FSMContext,
) -> None:
    reminders = await get_active_reminders(user_id)
    state_info = get_rendered_reminders_state(user_id)
    current_panel_id = await get_panel_message_id(user_id)
    if (
        reminders
        and state_info
        and current_panel_id == state_info["panel_id"]
        and state_info["sig"] == _reminders_signature(reminders)
        and (not state_info["had_tracked"] or await has_tracked_messages(user_id))
    ):
        await _sync_non_panel_cards_numbers(bot, user_id, state_info, show_numbers=False)
        state_info["panel_is_last_reminder"] = True
        await render_panel(
            bot=bot,
            user_id=user_id,
            text=state_info["last_text"],
            reply_markup=reminders_section_kb(
                has_reminders=True,
                can_undo_delete=False,
            ),
            cleanup=False,
        )
        return

    await show_reminders_screen(bot, user_id, state)


@router.message(Command("reminders", ignore_case=True))
async def cmd_reminders(message: Message, state: FSMContext, bot: Bot) -> None:
    await state.clear()
    await show_reminders_screen(
        bot,
        message.from_user.id,
        state,
        extra_delete_ids=[message.message_id],
    )


@router.message(
    StateFilter(None, ReminderFSM.waiting_for_reminder_number),
    _is_reply_to_reminder_card,
)
async def handle_reply_edit_reminder(message: Message, state: FSMContext, bot: Bot) -> None:
    uid = message.from_user.id
    replied_id = message.reply_to_message.message_id
    state_info = get_rendered_reminders_state(uid)
    if not state_info:
        return

    entry = (state_info.get("msg_map") or {}).get(replied_id)
    if not entry:
        return

    reminder_id, idx = entry
    new_text = extract_message_text(message)
    await safe_delete_message(bot, message.chat.id, message.message_id)
    if not new_text:
        return

    updated = await update_reminder_text(uid, reminder_id, new_text)
    if not updated:
        await state.clear()
        await show_reminders_screen(bot, uid, state, notice="Напоминание уже не активно.")
        return

    user_now, offset_mins = await get_user_now(uid)
    today = user_now.date()
    local_dt = updated.remind_at + timedelta(minutes=offset_mins)
    updated_plain_text = _format_reminder_item_text(updated, local_dt, today, idx=None)
    updated_numbered_text = _format_reminder_item_text(updated, local_dt, today, idx=idx)

    is_panel = replied_id == state_info.get("panel_id")
    reply_markup = None
    if is_panel:
        await state.clear()
        await _sync_non_panel_cards_numbers(bot, uid, state_info, show_numbers=False)
        reply_markup = reminders_section_kb(has_reminders=True, can_undo_delete=False)
        display_text = updated_plain_text
    else:
        display_text = (
            updated_numbered_text
            if state_info.get("numbers_visible")
            else updated_plain_text
        )

    try:
        await bot.edit_message_text(
            chat_id=uid,
            message_id=replied_id,
            text=display_text,
            reply_markup=reply_markup,
        )
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e).lower():
            await state.clear()
            await show_reminders_screen(bot, uid, state)
            return
    except Exception:
        await state.clear()
        await show_reminders_screen(bot, uid, state)
        return

    reminders = await get_active_reminders(uid)
    state_info["sig"] = _reminders_signature(reminders)
    for rendered in state_info.get("items") or []:
        if rendered["msg_id"] == replied_id:
            rendered["plain_text"] = updated_plain_text
            rendered["numbered_text"] = updated_numbered_text
            break
    if is_panel:
        state_info["last_text"] = updated_plain_text
        state_info["last_numbered_text"] = updated_numbered_text
        state_info["panel_is_last_reminder"] = True


@router.callback_query(F.data == "menu:list")
async def cb_menu_list(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await safe_answer_callback(callback)
    await state.clear()
    await show_reminders_screen(bot, callback.from_user.id, state)


@router.callback_query(F.data == "rem:back_panel")
async def cb_reminders_back_panel(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await safe_answer_callback(callback)
    await state.clear()
    await show_reminders_panel_only(bot, callback.from_user.id, state)


async def show_reminders_select(
    bot: Bot,
    user_id: int,
    state: FSMContext,
    mode: str = "edit",
    page: int = 0,
    error_msg: str = "",
) -> None:
    reminders = await get_active_reminders(user_id)
    if not reminders:
        await state.clear()
        await show_reminders_screen(bot, user_id, state)
        return

    state_info = get_rendered_reminders_state(user_id)
    current_panel_id = await get_panel_message_id(user_id)
    current_sig = _reminders_signature(reminders)
    rendered_items = (state_info or {}).get("items") or []
    can_use_rendered = (
        state_info is not None
        and current_panel_id == state_info.get("panel_id")
        and state_info.get("sig") == current_sig
        and len(rendered_items) == len(reminders)
        and (not state_info.get("had_tracked") or await has_tracked_messages(user_id))
    )

    reminder_map: dict[str, int] = {}
    items: list[tuple[int, int]] = []
    if can_use_rendered:
        for rendered in rendered_items:
            idx = rendered["idx"]
            rid = rendered["reminder_id"]
            reminder_map[str(idx)] = rid
            items.append((idx, rid))
    else:
        for idx, r in enumerate(reminders, start=1):
            reminder_map[str(idx)] = r.id
            items.append((idx, r.id))

    total = len(items)
    max_page = max(0, get_reminder_grid_page_count(total) - 1)
    page = max(0, min(page, max_page))

    await state.update_data(
        reminder_map=reminder_map,
        edit_select_page=page,
        select_mode=mode,
    )
    await state.set_state(ReminderFSM.waiting_for_reminder_number)

    if mode == "delete":
        item_prefix = "rem:del_pick"
        page_prefix = "rem:del_page"
    else:
        item_prefix = "rem:open"
        page_prefix = "rem:edit_page"

    if can_use_rendered:
        await _sync_non_panel_cards_numbers(bot, user_id, state_info, show_numbers=True)
        base_text = state_info["last_numbered_text"]
        state_info["panel_is_last_reminder"] = True
    else:
        user_now, offset_mins = await get_user_now(user_id)
        last_rem = reminders[-1]
        base_text = _format_reminder_item_text(
            last_rem,
            last_rem.remind_at + timedelta(minutes=offset_mins),
            user_now.date(),
            idx=total,
        )

    text = f"{base_text}\n\n⚠️ {error_msg}" if error_msg else base_text
    await render_panel(
        bot=bot,
        user_id=user_id,
        text=text,
        reply_markup=reminders_edit_select_kb(
            items=items,
            total_count=total,
            page=page,
            item_prefix=item_prefix,
            page_prefix=page_prefix,
        ),
        cleanup=False,
    )


async def _execute_reminder_delete(
    bot: Bot,
    user_id: int,
    state: FSMContext,
    reminder_id: int,
    number_label: str = "",
    callback: CallbackQuery | None = None,
    extra_delete_ids: list[int] | None = None,
) -> None:
    await state.clear()

    reminder = await get_reminder_by_id(user_id, reminder_id)
    if not reminder:
        if callback:
            await safe_answer_callback(callback, "Напоминание уже не активно.")
        await show_reminders_screen(
            bot,
            user_id,
            state,
            notice="Напоминание уже не активно.",
            extra_delete_ids=extra_delete_ids,
        )
        return

    deleted = await delete_reminder_by_id(user_id, reminder_id)
    if not deleted:
        if callback:
            await safe_answer_callback(callback, "Напоминание уже не активно.")
        await show_reminders_screen(
            bot,
            user_id,
            state,
            notice="Напоминание уже не активно.",
            extra_delete_ids=extra_delete_ids,
        )
        return

    set_last_deleted_reminder(
        user_id,
        {
            "text": reminder.text,
            "remind_at": reminder.remind_at,
            "recurrence": reminder.recurrence,
            "number_label": number_label,
        },
    )
    notice = f"Напоминание №{number_label} удалено." if number_label else "Напоминание удалено."
    if callback:
        await safe_answer_callback(callback, notice)

    reminders = await get_active_reminders(user_id)
    if not reminders:
        await show_reminders_screen(
            bot,
            user_id,
            state,
            notice=notice,
            extra_delete_ids=extra_delete_ids,
            can_undo_delete=True,
        )
        return

    state_info = get_rendered_reminders_state(user_id)
    current_panel_id = await get_panel_message_id(user_id)
    rendered_items = (state_info or {}).get("items") or []
    target_pos = next(
        (i for i, it in enumerate(rendered_items) if it["reminder_id"] == reminder_id),
        None,
    )

    can_delete_in_place = (
        state_info is not None
        and current_panel_id == state_info.get("panel_id")
        and target_pos is not None
        and (not state_info.get("had_tracked") or await has_tracked_messages(user_id))
    )

    if can_delete_in_place:
        remaining_items = [it for i, it in enumerate(rendered_items) if i != target_pos]
        if [it["reminder_id"] for it in remaining_items] != [r.id for r in reminders]:
            can_delete_in_place = False

    if not can_delete_in_place:
        await show_reminders_screen(
            bot,
            user_id,
            state,
            notice=notice,
            extra_delete_ids=extra_delete_ids,
            can_undo_delete=True,
        )
        return

    target_item = rendered_items[target_pos]
    target_msg_id = target_item["msg_id"]
    target_header_id = target_item.get("header_msg_id")
    orphaned_header_id = (
        target_header_id
        if target_header_id
        and not any(it.get("header_msg_id") == target_header_id for it in remaining_items)
        else None
    )

    ids_to_delete: list[int] = [target_msg_id]
    if orphaned_header_id:
        ids_to_delete.append(orphaned_header_id)
    if extra_delete_ids:
        ids_to_delete.extend(extra_delete_ids)

    was_numbered = bool(state_info.get("numbers_visible"))
    new_last_item = remaining_items[-1]
    kb = reminders_section_kb(has_reminders=True, can_undo_delete=True)

    if target_msg_id == current_panel_id:
        new_panel_id = new_last_item["msg_id"]
        try:
            if was_numbered:
                await bot.edit_message_text(
                    chat_id=user_id,
                    message_id=new_panel_id,
                    text=new_last_item["plain_text"],
                    reply_markup=kb,
                )
            else:
                await bot.edit_message_reply_markup(
                    chat_id=user_id,
                    message_id=new_panel_id,
                    reply_markup=kb,
                )
        except TelegramBadRequest as e:
            if "message is not modified" not in str(e).lower():
                await show_reminders_screen(
                    bot,
                    user_id,
                    state,
                    notice=notice,
                    extra_delete_ids=extra_delete_ids,
                    can_undo_delete=True,
                )
                return
        except Exception:
            await show_reminders_screen(
                bot,
                user_id,
                state,
                notice=notice,
                extra_delete_ids=extra_delete_ids,
                can_undo_delete=True,
            )
            return

        await remove_tracked_message(user_id, new_panel_id)
        if orphaned_header_id:
            await remove_tracked_message(user_id, orphaned_header_id)
        await set_panel_message_id(user_id, new_panel_id)
        await safe_delete_messages_batch(bot, user_id, ids_to_delete)

        state_info["panel_id"] = new_panel_id
    else:
        try:
            await bot.edit_message_text(
                chat_id=user_id,
                message_id=current_panel_id,
                text=new_last_item["plain_text"],
                reply_markup=kb,
            )
        except TelegramBadRequest as e:
            if "message is not modified" not in str(e).lower():
                await show_reminders_screen(
                    bot,
                    user_id,
                    state,
                    notice=notice,
                    extra_delete_ids=extra_delete_ids,
                    can_undo_delete=True,
                )
                return
        except Exception:
            await show_reminders_screen(
                bot,
                user_id,
                state,
                notice=notice,
                extra_delete_ids=extra_delete_ids,
                can_undo_delete=True,
            )
            return

        await remove_tracked_message(user_id, target_msg_id)
        if orphaned_header_id:
            await remove_tracked_message(user_id, orphaned_header_id)
        await safe_delete_messages_batch(bot, user_id, ids_to_delete)

    new_msg_map: dict[int, tuple[int, int]] = {}
    for new_idx, item in enumerate(remaining_items, start=1):
        item["idx"] = new_idx
        item["numbered_text"] = f"№{new_idx} - {item['plain_text']}"
        new_msg_map[item["msg_id"]] = (item["reminder_id"], new_idx)

    header_ids = state_info.get("header_ids") or set()
    if orphaned_header_id:
        header_ids.discard(orphaned_header_id)

    state_info["items"] = remaining_items
    state_info["msg_map"] = new_msg_map
    state_info["last_text"] = new_last_item["plain_text"]
    state_info["last_numbered_text"] = new_last_item["numbered_text"]
    state_info["sig"] = _reminders_signature(reminders)
    state_info["panel_is_last_reminder"] = True
    state_info["had_tracked"] = bool(len(remaining_items) > 1 or header_ids)

    if was_numbered:
        await _sync_non_panel_cards_numbers(bot, user_id, state_info, show_numbers=False)


@router.callback_query(F.data == "rem:edit_prompt")
async def cb_edit_reminders_prompt(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await safe_answer_callback(callback, "Выберите номер для редактирования")
    await show_reminders_select(bot, callback.from_user.id, state, mode="edit", page=0)


@router.callback_query(F.data.startswith("rem:edit_page:"))
async def cb_edit_reminders_page(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await safe_answer_callback(callback)
    page = int(callback.data.split(":")[2])
    await show_reminders_select(bot, callback.from_user.id, state, mode="edit", page=page)


@router.callback_query(F.data == "rem:del_prompt")
async def cb_del_reminders_prompt(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await safe_answer_callback(callback, "Выберите номер для удаления")
    await show_reminders_select(bot, callback.from_user.id, state, mode="delete", page=0)


@router.callback_query(F.data.startswith("rem:del_page:"))
async def cb_del_reminders_page(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await safe_answer_callback(callback)
    page = int(callback.data.split(":")[2])
    await show_reminders_select(bot, callback.from_user.id, state, mode="delete", page=page)


@router.callback_query(F.data.startswith("rem:del_pick:"))
async def cb_del_reminder_pick(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    parts = callback.data.split(":")
    reminder_id = int(parts[2])
    number_label = parts[3] if len(parts) > 3 else ""
    await _execute_reminder_delete(
        bot=bot,
        user_id=callback.from_user.id,
        state=state,
        reminder_id=reminder_id,
        number_label=number_label,
        callback=callback,
    )


@router.callback_query(F.data == "rem:undo_delete")
async def cb_undo_delete_reminder(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    uid = callback.from_user.id
    await state.clear()
    saved = pop_last_deleted_reminder(uid)
    if not saved:
        await safe_answer_callback(callback, "Отмена удаления больше недоступна", show_alert=True)
        await show_reminders_screen(bot, uid, state)
        return

    await safe_answer_callback(callback, "Удаление отменено")
    await create_reminder(
        user_id=uid,
        text=saved["text"],
        remind_at_utc=saved["remind_at"],
        recurrence=saved["recurrence"],
    )
    await show_reminders_screen(
        bot,
        uid,
        state,
        notice="",
        can_undo_delete=False,
    )


@router.message(ReminderFSM.waiting_for_reminder_number, F.text)
async def process_reminder_number_input(message: Message, state: FSMContext, bot: Bot) -> None:
    raw_num = message.text.strip()

    data = await state.get_data()
    reminder_map: dict[str, int] = data.get("reminder_map") or {}
    page: int = data.get("edit_select_page", 0)
    mode: str = data.get("select_mode", "edit")

    if not reminder_map:
        reminders = await get_active_reminders(message.from_user.id)
        reminder_map = {str(idx): r.id for idx, r in enumerate(reminders, start=1)}

    if not raw_num.isdigit() or raw_num not in reminder_map:
        await safe_delete_message(bot, message.chat.id, message.message_id)
        await show_reminders_select(
            bot,
            message.from_user.id,
            state,
            mode=mode,
            page=page,
            error_msg=f"Напоминание с номером «{html.escape(raw_num)}» не найдено.",
        )
        return

    reminder_id = reminder_map[raw_num]

    if mode == "delete":
        await _execute_reminder_delete(
            bot=bot,
            user_id=message.from_user.id,
            state=state,
            reminder_id=reminder_id,
            number_label=raw_num,
            extra_delete_ids=[message.message_id],
        )
        return

    await state.clear()
    await show_reminder_edit_card(
        bot,
        message.from_user.id,
        state,
        reminder_id,
        number_label=raw_num,
        extra_delete_ids=[message.message_id],
        cleanup=False,
    )


async def show_reminder_edit_card(
    bot: Bot,
    user_id: int,
    state: FSMContext,
    reminder_id: int,
    notice: str = "",
    number_label: str = "",
    extra_delete_ids: list[int] | None = None,
    cleanup: bool = False,
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

    text = (
        f"Управление напоминанием{title_num}\n"
        f"{notice_block}"
        f"{format_date_with_weekday(local_dt.date())}, в {local_dt.strftime('%H:%M')}"
        f"{rec_line}\n"
        f"{reminder.text}\n\n"
        "Выберите нужное действие:"
    )
    if cleanup:
        clear_rendered_reminders_state(user_id)
    else:
        state_info = get_rendered_reminders_state(user_id)
        if state_info and state_info.get("numbers_visible"):
            await _sync_non_panel_cards_numbers(bot, user_id, state_info, show_numbers=False)
        _mark_panel_not_last_reminder(user_id)

    back_text = "⬅️ Назад к напоминаниям" if notice else "⬅️ Назад"

    await render_panel(
        bot=bot,
        user_id=user_id,
        text=text,
        reply_markup=reminder_edit_menu_kb(
            reminder.id,
            number_label=number_label,
            back_text=back_text,
        ),
        cleanup=cleanup,
        extra_delete_ids=extra_delete_ids,
    )


@router.callback_query(F.data.startswith("rem:open:"))
async def cb_open_reminder_edit(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await safe_answer_callback(callback)
    await state.clear()
    parts = callback.data.split(":")
    reminder_id = int(parts[2])
    number_label = parts[3] if len(parts) > 3 else ""
    await show_reminder_edit_card(
        bot,
        callback.from_user.id,
        state,
        reminder_id,
        number_label=number_label,
        cleanup=False,
    )


@router.callback_query(F.data.startswith("del:ask:"))
async def cb_delete_reminder_ask(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    parts = callback.data.split(":")
    reminder_id = int(parts[2])
    number_label = parts[3] if len(parts) > 3 else ""
    await _execute_reminder_delete(
        bot=bot,
        user_id=callback.from_user.id,
        state=state,
        reminder_id=reminder_id,
        number_label=number_label,
        callback=callback,
    )


@router.callback_query(F.data.startswith("del:confirm:"))
async def cb_delete_reminder_confirm(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    parts = callback.data.split(":")
    reminder_id = int(parts[2])
    number_label = parts[3] if len(parts) > 3 else ""
    await _execute_reminder_delete(
        bot=bot,
        user_id=callback.from_user.id,
        state=state,
        reminder_id=reminder_id,
        number_label=number_label,
        callback=callback,
    )


# --- Редактирование 1: Изменение текста напоминания ---

@router.callback_query(F.data.startswith("edit:text:"))
async def cb_edit_reminder_text(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await safe_answer_callback(callback)
    uid = callback.from_user.id
    reminder_id = int(callback.data.split(":")[2])
    reminder = await get_reminder_by_id(uid, reminder_id)
    if not reminder:
        await show_reminders_screen(
            bot, uid, state, notice="Напоминание уже не активно."
        )
        return

    await state.set_state(ReminderFSM.editing_text)
    await state.update_data(edit_reminder_id=reminder_id)
    clear_rendered_reminders_state(uid)

    await render_panel(
        bot=bot,
        user_id=uid,
        text=reminder.text,
        reply_markup=edit_text_cancel_kb(reminder_id),
        force_new=True,
        cleanup=True,
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
        cleanup=True,
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
        f"{reminder_text}\n\n"
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
        plain_home=False,
    )
    _mark_panel_not_last_reminder(user_id)
    await render_panel(
        bot=bot,
        user_id=user_id,
        text=text,
        reply_markup=kb,
        cleanup=False,
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
        f"{reminder_text}\n\n"
        "Нажмите «На год вперёд», переключите год стрелками < > или выберите нужный месяц:"
    )
    kb = build_calendar_ym_kb(
        year=year,
        current_month=current_month,
        today=today,
        year_nav_prefix=f"cal:eynav:{reminder_id}",
        month_pick_prefix=f"cal:empick:{reminder_id}",
        plain_home=False,
    )
    _mark_panel_not_last_reminder(user_id)
    await render_panel(
        bot=bot,
        user_id=user_id,
        text=text,
        reply_markup=kb,
        cleanup=False,
    )


@router.callback_query(F.data.startswith("edit:date:"))
async def cb_edit_reminder_date(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await safe_answer_callback(callback)
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
        f"{format_date_with_weekday(local_dt.date())}, в {local_dt.strftime('%H:%M')}\n"
        f"{reminder.text}\n\n"
        "Выберите новую дату кнопкой ниже или откройте Календарь:"
    )
    _mark_panel_not_last_reminder(callback.from_user.id)
    await render_panel(
        bot=bot,
        user_id=callback.from_user.id,
        text=text,
        reply_markup=edit_date_selection_kb(reminder_id),
        cleanup=False,
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
        await safe_answer_callback(callback)
        await show_reminders_screen(
            bot, callback.from_user.id, state, notice="Напоминание уже не активно."
        )
        return

    new_year, new_month = step_year_month(year, month, direction)
    user_now, _ = await get_user_now(callback.from_user.id)
    today = user_now.date()
    if (new_year, new_month) < (today.year, today.month):
        await safe_answer_callback(callback, "Нельзя выбрать прошедший месяц", show_alert=False)
        return

    await safe_answer_callback(callback)
    await show_edit_calendar(
        bot=bot,
        user_id=callback.from_user.id,
        reminder_id=reminder_id,
        reminder_text=reminder.text,
        year=new_year,
        month=new_month,
    )


@router.callback_query(F.data.startswith("cal:eym:"))
async def cb_edit_calendar_ym_open(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await safe_answer_callback(callback)
    parts = callback.data.split(":")
    reminder_id = int(parts[2])
    year = int(parts[3])
    month = int(parts[4])

    reminder = await get_reminder_by_id(callback.from_user.id, reminder_id)
    if not reminder:
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


@router.callback_query(F.data.startswith("cal:eynav:"))
async def cb_edit_calendar_year_nav(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    parts = callback.data.split(":")
    reminder_id = int(parts[2])
    year = int(parts[3])
    month = int(parts[4])
    direction = parts[5]

    reminder = await get_reminder_by_id(callback.from_user.id, reminder_id)
    if not reminder:
        await safe_answer_callback(callback)
        await show_reminders_screen(
            bot, callback.from_user.id, state, notice="Напоминание уже не активно."
        )
        return

    new_year = year + 1 if direction == "next" else year - 1
    user_now, _ = await get_user_now(callback.from_user.id)
    today = user_now.date()
    if new_year < today.year:
        await safe_answer_callback(callback, "Нельзя выбрать прошедший год", show_alert=False)
        return

    await safe_answer_callback(callback)
    await show_edit_ym_picker(
        bot=bot,
        user_id=callback.from_user.id,
        reminder_id=reminder_id,
        reminder_text=reminder.text,
        year=new_year,
        current_month=month,
    )


@router.callback_query(F.data.startswith("cal:empick:"))
async def cb_edit_calendar_month_pick(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    parts = callback.data.split(":")
    reminder_id = int(parts[2])
    year = int(parts[3])
    month = int(parts[4])

    reminder = await get_reminder_by_id(callback.from_user.id, reminder_id)
    if not reminder:
        await safe_answer_callback(callback)
        await show_reminders_screen(
            bot, callback.from_user.id, state, notice="Напоминание уже не активно."
        )
        return

    user_now, _ = await get_user_now(callback.from_user.id)
    today = user_now.date()
    if (year, month) < (today.year, today.month):
        await safe_answer_callback(callback, "Нельзя выбрать прошедший месяц", show_alert=False)
        return

    await safe_answer_callback(callback)
    await show_edit_calendar(
        bot=bot,
        user_id=callback.from_user.id,
        reminder_id=reminder_id,
        reminder_text=reminder.text,
        year=year,
        month=month,
    )


@router.callback_query(F.data.startswith("cal:epick:"))
async def cb_edit_calendar_pick(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    parts = callback.data.split(":", 3)
    reminder_id = int(parts[2])
    picked_date = date.fromisoformat(parts[3])

    user_now, _ = await get_user_now(callback.from_user.id)
    today = user_now.date()
    if picked_date < today:
        await safe_answer_callback(callback, "Эта дата уже в прошлом", show_alert=False)
        return

    await safe_answer_callback(callback)
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
        f"Дата: {format_date_with_weekday(target_date)}\n"
        f"{reminder.text}\n\n"
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
        plain_style=False,
    )
    _mark_panel_not_last_reminder(user_id)
    await render_panel(
        bot=bot,
        user_id=user_id,
        text=text,
        reply_markup=kb,
        cleanup=False,
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
        f"Дата: {format_date_with_weekday(target_date)}\n"
        f"Выбранное время: {hour:02d}:{minute:02d}\n"
        f"{reminder.text}\n\n"
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
        plain_style=False,
    )
    _mark_panel_not_last_reminder(user_id)
    await render_panel(
        bot=bot,
        user_id=user_id,
        text=text,
        reply_markup=kb,
        cleanup=False,
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
        notice=f"Дата изменена на {format_date_with_weekday(new_date)}.",
        extra_delete_ids=extra_delete_ids,
        cleanup=True,
    )


@router.callback_query(F.data.startswith("edate:"))
async def cb_edit_date_buttons(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await safe_answer_callback(callback)
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
    elif action == "1m":
        target_date = add_one_month(today)
    else:
        target_date = add_one_year(today)

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
    await safe_answer_callback(callback)
    reminder_id = int(callback.data.split(":")[2])
    await state.set_state(ReminderFSM.editing_time)
    await state.update_data(edit_reminder_id=reminder_id, pending_edit_date=None)
    await show_edit_hours_picker(bot, callback.from_user.id, state, reminder_id)


@router.callback_query(F.data.startswith("etime:back_hours:"))
async def cb_edit_time_back_hours(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await safe_answer_callback(callback)
    reminder_id = int(callback.data.split(":")[2])
    await show_edit_hours_picker(bot, callback.from_user.id, state, reminder_id)


@router.callback_query(F.data.startswith("etime:hour:"))
async def cb_edit_time_pick_hour(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await safe_answer_callback(callback)
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
    await safe_answer_callback(callback)
    parts = callback.data.split(":")
    reminder_id = int(parts[2])
    hour = int(parts[3])
    minute = int(parts[4])
    await show_edit_minutes_drum(bot, callback.from_user.id, state, reminder_id, hour, minute)


@router.callback_query(F.data.startswith("etime:pick:"))
async def cb_edit_time_pick_confirm(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await safe_answer_callback(callback)
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
        notice=f"Время напоминания изменено на {format_date_with_weekday(new_local_dt.date())}, в {new_local_dt.strftime('%H:%M')} ({tz_label}).",
        extra_delete_ids=extra_delete_ids,
        cleanup=True,
    )


@router.callback_query(F.data.startswith("etime:skip:"))
async def cb_edit_time_skip(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await safe_answer_callback(callback)
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
    await safe_answer_callback(callback)
    await state.clear()
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
        f"{reminder.text}\n\n"
        "Выберите режим срабатывания:"
    )
    _mark_panel_not_last_reminder(callback.from_user.id)
    await render_panel(
        bot=bot,
        user_id=callback.from_user.id,
        text=text,
        reply_markup=edit_recurrence_type_kb(reminder_id),
        cleanup=False,
    )


@router.callback_query(F.data.startswith("erec:menu:"))
async def cb_edit_reminder_rec_menu(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await safe_answer_callback(callback)
    await state.clear()
    reminder_id = int(callback.data.split(":")[2])
    reminder = await get_reminder_by_id(callback.from_user.id, reminder_id)
    if not reminder:
        await show_reminders_screen(
            bot, callback.from_user.id, state, notice="Напоминание уже не активно."
        )
        return

    text = (
        "Выбор периодичности повторения\n"
        f"{reminder.text}\n\n"
        "Выберите, с какой периодичностью присылать напоминание:"
    )
    _mark_panel_not_last_reminder(callback.from_user.id)
    await render_panel(
        bot=bot,
        user_id=callback.from_user.id,
        text=text,
        reply_markup=edit_recurrence_period_kb(reminder_id),
        cleanup=False,
    )


@router.callback_query(F.data.startswith("erec:once:"))
async def cb_edit_reminder_rec_once(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await safe_answer_callback(callback)
    await state.clear()
    reminder_id = int(callback.data.split(":")[2])
    await update_reminder_recurrence(callback.from_user.id, reminder_id, "once")
    await show_reminder_edit_card(
        bot,
        callback.from_user.id,
        state,
        reminder_id,
        notice="Установлен режим: Один раз.",
        cleanup=True,
    )


@router.callback_query(F.data.startswith("erec_set:"))
async def cb_edit_reminder_rec_set(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await safe_answer_callback(callback)
    await state.clear()
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
        cleanup=True,
    )
