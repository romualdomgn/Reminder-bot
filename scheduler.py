import asyncio
import html
import logging
from datetime import datetime, timezone, timedelta
from aiogram import Bot

from database import (
    get_due_reminders,
    process_triggered_reminder,
    add_tracked_message,
    get_user_offset_minutes,
    format_tz_label,
    format_recurrence_label,
)
from keyboards import notification_ack_kb

logger = logging.getLogger(__name__)


async def reminder_scheduler_loop(bot: Bot) -> None:
    logger.info("Фоновый планировщик напоминаний запущен.")
    while True:
        try:
            now_utc_naive = datetime.now(timezone.utc).replace(tzinfo=None)
            due_list = await get_due_reminders(now_utc_naive)

            for item in due_list:
                offset_mins = await get_user_offset_minutes(item.user_id)
                try:
                    local_dt = item.remind_at + timedelta(minutes=offset_mins)
                    tz_label = format_tz_label(offset_mins)
                    rec_label = format_recurrence_label(item.recurrence)

                    alert_text = (
                        "🔔 <b>НАПОМИНАНИЕ!</b>\n"
                        f"🗓 <code>{local_dt.strftime('%d.%m.%Y %H:%M')} ({tz_label})</code>\n"
                        f"🔁 <code>{rec_label}</code>\n\n"
                        f"💬 {html.escape(item.text)}"
                    )
                    sent_msg = await bot.send_message(
                        chat_id=item.user_id,
                        text=alert_text,
                        reply_markup=notification_ack_kb(item.id),
                    )
                    await add_tracked_message(item.user_id, sent_msg.message_id)
                except Exception as send_err:
                    logger.error(f"Ошибка отправки напоминания ID={item.id}: {send_err}")
                finally:
                    await process_triggered_reminder(item.id, offset_mins)

        except Exception as loop_err:
            logger.error(f"Ошибка в цикле планировщика: {loop_err}")

        await asyncio.sleep(5)
