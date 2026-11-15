import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand, BotCommandScopeDefault, BotCommandScopeChat

from config import BOT_TOKEN, ADMIN_IDS
from database import init_db, get_users_with_user_section
from middlewares import AccessControlMiddleware
from handlers import router
from scheduler import reminder_scheduler_loop

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)


async def set_bot_commands(bot: Bot) -> None:
    # Базовое меню для обычных пользователей
    user_commands = [
        BotCommand(command="start", description="🎛 Открыть пульт напоминаний"),
        BotCommand(command="reminders", description="📋 Напоминания"),
        BotCommand(command="settings", description="⚙️ Настройки"),
        BotCommand(command="info", description="ℹ️ Информация"),
    ]
    await bot.set_my_commands(user_commands, scope=BotCommandScopeDefault())

    # Меню с разделом /user для пользователей, добавивших хотя бы одного нового пользователя
    inviter_commands = [
        BotCommand(command="start", description="🎛 Открыть пульт напоминаний"),
        BotCommand(command="reminders", description="📋 Напоминания"),
        BotCommand(command="user", description="👥 Пользователи"),
        BotCommand(command="settings", description="⚙️ Настройки"),
        BotCommand(command="info", description="ℹ️ Информация"),
    ]
    inviter_ids = await get_users_with_user_section()
    for uid in inviter_ids:
        try:
            await bot.set_my_commands(inviter_commands, scope=BotCommandScopeChat(chat_id=uid))
        except Exception:
            pass

    # Меню для администратора
    admin_commands = [
        BotCommand(command="start", description="🎛 Открыть пульт напоминаний"),
        BotCommand(command="reminders", description="📋 Напоминания"),
        BotCommand(command="users", description="👥 Пользователи"),
        BotCommand(command="settings", description="⚙️ Настройки"),
    ]
    for admin_id in ADMIN_IDS:
        try:
            await bot.set_my_commands(admin_commands, scope=BotCommandScopeChat(chat_id=admin_id))
        except Exception as e:
            logging.warning(f"Не удалось установить команды меню для админа {admin_id}: {e}")


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
