import asyncio
import logging
import time
from datetime import datetime, timezone
from aiogram import Bot
from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramRetryAfter,
)

from config import trim_memory
from database import (
    get_due_reminders,
    process_triggered_reminder,
    get_user_offset_minutes,
)
from handlers.notifications import send_reminder_notification

logger = logging.getLogger(__name__)

TRIM_INTERVAL_SECONDS = 3 * 3600
BASE_POLL_INTERVAL_SECONDS = 5
MAX_BACKOFF_SECONDS = 60


async def reminder_scheduler_loop(bot: Bot) -> None:
    logger.info("Фоновый планировщик напоминаний запущен.")
    last_trim = time.monotonic()
    backoff_seconds = BASE_POLL_INTERVAL_SECONDS

    while True:
        sleep_seconds = BASE_POLL_INTERVAL_SECONDS
        try:
            now_utc_naive = datetime.now(timezone.utc).replace(tzinfo=None)
            due_list = await get_due_reminders(now_utc_naive)
            had_transient_error = False

            for item in due_list:
                try:
                    offset_mins = await get_user_offset_minutes(item.user_id)
                except Exception:
                    logger.exception(
                        "Ошибка чтения часового пояса для напоминания ID=%s (user_id=%s)",
                        item.id,
                        item.user_id,
                    )
                    had_transient_error = True
                    continue

                delivered = False
                permanent_failure = False

                try:
                    await send_reminder_notification(
                        bot=bot,
                        user_id=item.user_id,
                        reminder_id=item.id,
                        text=item.text,
                        recurrence=item.recurrence,
                    )
                    delivered = True
                except TelegramForbiddenError as send_err:
                    logger.warning(
                        "Пользователь %s заблокировал бота, напоминание ID=%s помечено обработанным: %s",
                        item.user_id,
                        item.id,
                        send_err,
                    )
                    permanent_failure = True
                except TelegramBadRequest as send_err:
                    err_text = str(send_err).lower()
                    if "chat not found" in err_text or "user is deactivated" in err_text:
                        logger.warning(
                            "Чат пользователя %s недоступен, напоминание ID=%s помечено обработанным: %s",
                            item.user_id,
                            item.id,
                            send_err,
                        )
                        permanent_failure = True
                    else:
                        logger.exception(
                            "Ошибка TelegramBadRequest при отправке напоминания ID=%s (user_id=%s)",
                            item.id,
                            item.user_id,
                        )
                        had_transient_error = True
                except TelegramRetryAfter as retry_err:
                    logger.warning(
                        "Telegram rate limit (retry_after=%s) при отправке напоминания ID=%s",
                        retry_err.retry_after,
                        item.id,
                    )
                    sleep_seconds = max(
                        sleep_seconds,
                        min(int(retry_err.retry_after) + 1, MAX_BACKOFF_SECONDS),
                    )
                    had_transient_error = True
                    break
                except Exception:
                    logger.exception(
                        "Временная ошибка отправки напоминания ID=%s (user_id=%s), повтор в следующем цикле",
                        item.id,
                        item.user_id,
                    )
                    had_transient_error = True

                if delivered or permanent_failure:
                    try:
                        await process_triggered_reminder(
                            item.id,
                            offset_mins,
                            expected_remind_at=item.remind_at,
                        )
                    except Exception:
                        logger.exception(
                            "Ошибка фиксации срабатывания напоминания ID=%s",
                            item.id,
                        )
                        had_transient_error = True

            if had_transient_error:
                backoff_seconds = min(backoff_seconds * 2, MAX_BACKOFF_SECONDS)
                sleep_seconds = max(sleep_seconds, backoff_seconds)
            else:
                backoff_seconds = BASE_POLL_INTERVAL_SECONDS

            now_mono = time.monotonic()
            if now_mono - last_trim >= TRIM_INTERVAL_SECONDS:
                trim_memory()
                last_trim = now_mono

        except Exception:
            logger.exception("Ошибка в цикле планировщика")
            backoff_seconds = min(backoff_seconds * 2, MAX_BACKOFF_SECONDS)
            sleep_seconds = backoff_seconds

        await asyncio.sleep(sleep_seconds)
