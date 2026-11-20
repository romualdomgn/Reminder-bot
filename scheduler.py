import asyncio
import logging
import time
from datetime import datetime, timezone
from aiogram import Bot

from config import trim_memory
from database import (
    get_due_reminders,
    process_triggered_reminder,
    get_user_offset_minutes,
)
from handlers.notifications import send_reminder_notification

logger = logging.getLogger(__name__)

TRIM_INTERVAL_SECONDS = 3 * 3600


async def reminder_scheduler_loop(bot: Bot) -> None:
    logger.info("Фоновый планировщик напоминаний запущен.")
    last_trim = time.monotonic()

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

            now_mono = time.monotonic()
            if now_mono - last_trim >= TRIM_INTERVAL_SECONDS:
                trim_memory()
                last_trim = now_mono

        except Exception as loop_err:
            logger.error(f"Ошибка в цикле планировщика: {loop_err}")

        await asyncio.sleep(5)
