import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand, BotCommandScopeDefault

from config import BOT_TOKEN, ADMIN_IDS
from database import init_db, get_all_bot_users
from middlewares import AccessControlMiddleware
from handlers import router
from handlers.common import sync_user_commands
from scheduler import reminder_scheduler_loop

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)


async def set_bot_commands(bot: Bot) -> None:
    for lang in (None, "ru", "en"):
        try:
            await bot.set_my_description(description="", language_code=lang)
        except Exception:
            pass

    user_commands = [
        BotCommand(command="start", description="🧭 Главное меню"),
        BotCommand(command="reminders", description="📋 Напоминания"),
        BotCommand(command="settings", description="⚙️ Настройки"),
        BotCommand(command="info", description="ℹ️ Информация"),
    ]
    await bot.set_my_commands(user_commands, scope=BotCommandScopeDefault())

    users = await get_all_bot_users()
    all_uids = {u.user_id for u in users} | set(ADMIN_IDS)
    for uid in all_uids:
        await sync_user_commands(bot, uid)


async def main() -> None:
    await init_db()

    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())

    dp.message.middleware(AccessControlMiddleware())
    dp.callback_query.middleware(AccessControlMiddleware())

    dp.include_router(router)
    await set_bot_commands(bot)

    scheduler_task = asyncio.create_task(reminder_scheduler_loop(bot))

    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    finally:
        scheduler_task.cancel()
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
