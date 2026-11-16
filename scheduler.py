import asyncio
import logging
from datetime import datetime, timezone, timedelta
from aiogram import Bot

from database import (
    get_due_reminders,
    process_triggered_reminder,
    get_user_offset_minutes,
)
from handlers.notifications import send_reminder_notification

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
                    await send_reminder_notification(
                        bot=bot,
                        user_id=item.user_id,
                        reminder_id=item.id,
                        text=item.text,
                        recurrence=item.recurrence,
                    )
                except Exception as send_err:
                    logger.error(f"Ошибка отправки напоминания ID={item.id}: {send_err}")
                finally:
                    await process_triggered_reminder(item.id, offset_mins)

        except Exception as loop_err:
            logger.error(f"Ошибка в цикле планировщика: {loop_err}")

        await asyncio.sleep(5)
