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
    claim_due_reminder,
    finalize_triggered_delivery,
    get_due_reminders,
    get_user_offset_minutes,
    release_reminder_claim,
    update_pending_notification_msg_id,
)
from handlers.common import sync_user_commands
from handlers.notifications import send_reminder_notification

logger = logging.getLogger(__name__)

TRIM_INTERVAL_SECONDS = 3 * 3600
BASE_POLL_INTERVAL_SECONDS = 5
MAX_BACKOFF_SECONDS = 60
CLAIM_LEASE_SECONDS = 60
FINALIZE_RETRY_DELAYS = (0.2, 0.5, 1.0)


async def _finalize_with_retries(
    notif_id: int | None,
    message_id: int | None,
    reminder_id: int,
    offset_mins: int,
    expected_remind_at: datetime,
) -> bool:
    for attempt in range(len(FINALIZE_RETRY_DELAYS) + 1):
        try:
            await finalize_triggered_delivery(
                notif_id=notif_id,
                message_id=message_id,
                reminder_id=reminder_id,
                offset_mins=offset_mins,
                expected_remind_at=expected_remind_at,
            )
            return True
        except Exception:
            if attempt < len(FINALIZE_RETRY_DELAYS):
                await asyncio.sleep(FINALIZE_RETRY_DELAYS[attempt])
            else:
                logger.exception(
                    "Ошибка фиксации срабатывания напоминания ID=%s после повторов",
                    reminder_id,
                )
    if notif_id and message_id:
        try:
            await update_pending_notification_msg_id(notif_id, message_id)
        except Exception:
            logger.exception(
                "Не удалось сохранить fallback message_id=%s для уведомления ID=%s",
                message_id,
                notif_id,
            )
    return False


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
                    claimed = await claim_due_reminder(
                        item.id,
                        expected_remind_at=item.remind_at,
                        now_utc=now_utc_naive,
                        lease_seconds=CLAIM_LEASE_SECONDS,
                    )
                except Exception:
                    logger.exception(
                        "Ошибка резервирования напоминания ID=%s", item.id
                    )
                    had_transient_error = True
                    continue

                if not claimed:
                    continue

                try:
                    offset_mins = await get_user_offset_minutes(item.user_id)
                except Exception:
                    logger.exception(
                        "Ошибка чтения часового пояса для напоминания ID=%s (user_id=%s)",
                        item.id,
                        item.user_id,
                    )
                    try:
                        await release_reminder_claim(item.id)
                    except Exception:
                        logger.debug("release_reminder_claim failed for ID=%s", item.id)
                    had_transient_error = True
                    continue

                delivered = False
                permanent_failure = False
                notif_id: int | None = None
                sent_message_id: int | None = None

                try:
                    notif_id, sent_message_id = await send_reminder_notification(
                        bot=bot,
                        user_id=item.user_id,
                        reminder_id=item.id,
                        text=item.text,
                        recurrence=item.recurrence,
                        scheduled_at=item.remind_at,
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
                    try:
                        await release_reminder_claim(item.id)
                    except Exception:
                        logger.debug("release_reminder_claim failed for ID=%s", item.id)
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
                    finalized = await _finalize_with_retries(
                        notif_id=notif_id if delivered else None,
                        message_id=sent_message_id if delivered else None,
                        reminder_id=item.id,
                        offset_mins=offset_mins,
                        expected_remind_at=item.remind_at,
                    )
                    if not finalized:
                        had_transient_error = True
                    elif delivered:
                        try:
                            await sync_user_commands(bot, item.user_id)
                        except Exception:
                            logger.exception(
                                "Не удалось синхронизировать команды пользователя %s после отправки уведомления",
                                item.user_id,
                            )
                else:
                    try:
                        await release_reminder_claim(item.id)
                    except Exception:
                        logger.debug("release_reminder_claim failed for ID=%s", item.id)

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
