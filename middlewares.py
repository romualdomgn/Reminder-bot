import asyncio
import logging
from typing import Any, Awaitable, Callable, Dict
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery

from config import clear_last_deleted_reminder
from database import clear_undo_reminder, ensure_user_language, is_user_allowed
from i18n import detect_language_from_code, t

logger = logging.getLogger(__name__)
_USER_LOCKS: dict[int, asyncio.Lock] = {}


def _get_user_lock(user_id: int) -> asyncio.Lock:
    lock = _USER_LOCKS.get(user_id)
    if lock is None:
        lock = asyncio.Lock()
        _USER_LOCKS[user_id] = lock
    return lock


def clear_user_lock(user_id: int) -> None:
    lock = _USER_LOCKS.get(user_id)
    if lock is not None and not lock.locked():
        _USER_LOCKS.pop(user_id, None)


class AccessControlMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        tg_lang_code = getattr(user, "language_code", None) if user else None
        if not user or not await is_user_allowed(user.id):
            deny_text = t(detect_language_from_code(tg_lang_code), "access_denied")
            if isinstance(event, CallbackQuery):
                try:
                    await event.answer(deny_text, show_alert=True)
                except Exception as exc:
                    logger.debug("Access deny callback answer failed: %s", exc)
            elif isinstance(event, Message):
                text = (event.text or "").strip().lower()
                if text.startswith("/start"):
                    await event.answer(deny_text)
                else:
                    try:
                        await event.delete()
                    except Exception as exc:
                        logger.debug("Access deny message delete failed: %s", exc)
            return None

        lock = _get_user_lock(user.id)
        async with lock:
            await ensure_user_language(user.id, tg_lang_code)
            if isinstance(event, CallbackQuery):
                if event.data != "rem:undo_delete":
                    clear_last_deleted_reminder(user.id)
                    await clear_undo_reminder(user.id)
            elif isinstance(event, Message):
                clear_last_deleted_reminder(user.id)
                await clear_undo_reminder(user.id)

            return await handler(event, data)
