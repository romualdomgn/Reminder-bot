import asyncio
from typing import Any, Awaitable, Callable, Dict
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery

from config import clear_last_deleted_reminder
from database import is_user_allowed

_USER_LOCKS: dict[int, asyncio.Lock] = {}


def _get_user_lock(user_id: int) -> asyncio.Lock:
    lock = _USER_LOCKS.get(user_id)
    if lock is None:
        lock = asyncio.Lock()
        _USER_LOCKS[user_id] = lock
    return lock


class AccessControlMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        if not user or not await is_user_allowed(user.id):
            if isinstance(event, CallbackQuery):
                try:
                    await event.answer("У Вас нет доступа к боту", show_alert=True)
                except Exception:
                    pass
            elif isinstance(event, Message):
                text = (event.text or "").strip().lower()
                if text.startswith("/start"):
                    await event.answer("У Вас нет доступа к боту")
                else:
                    try:
                        await event.delete()
                    except Exception:
                        pass
            return None

        lock = _get_user_lock(user.id)
        async with lock:
            if isinstance(event, CallbackQuery):
                if event.data != "rem:undo_delete":
                    clear_last_deleted_reminder(user.id)
            elif isinstance(event, Message):
                clear_last_deleted_reminder(user.id)

            return await handler(event, data)
