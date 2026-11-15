from typing import Any, Awaitable, Callable, Dict
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery

from database import is_user_allowed


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
                await event.answer("У Вас нет доступа к боту", show_alert=True)
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
        return await handler(event, data)
