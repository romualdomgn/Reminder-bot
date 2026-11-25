import asyncio
import logging
import socket
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand, BotCommandScopeDefault

from config import BOT_TOKEN, TELEGRAM_PROXY, ADMIN_IDS, mask_proxy_url, trim_memory
from database import init_db, engine, get_all_bot_user_ids
from middlewares import AccessControlMiddleware
from handlers import router
from handlers.common import sync_user_commands
from i18n import t
from scheduler import reminder_scheduler_loop

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


async def set_bot_commands(bot: Bot) -> None:
    for lang in (None, "ru", "en"):
        try:
            await bot.set_my_description(description="", language_code=lang)
        except Exception as exc:
            logger.debug("set_my_description(lang=%s) failed: %s", lang, exc)

    for lang_code in ("ru", "en"):
        user_commands = [
            BotCommand(command="start", description=t(lang_code, "cmd_start")),
            BotCommand(command="reminders", description=t(lang_code, "cmd_reminders")),
            BotCommand(command="settings", description=t(lang_code, "cmd_settings")),
            BotCommand(command="info", description=t(lang_code, "cmd_info")),
        ]
        try:
            await bot.set_my_commands(
                user_commands,
                scope=BotCommandScopeDefault(),
                language_code=lang_code,
            )
        except Exception as exc:
            logger.debug("set_my_commands(lang=%s) failed: %s", lang_code, exc)
    await bot.set_my_commands(
        [
            BotCommand(command="start", description=t("ru", "cmd_start")),
            BotCommand(command="reminders", description=t("ru", "cmd_reminders")),
            BotCommand(command="settings", description=t("ru", "cmd_settings")),
            BotCommand(command="info", description=t("ru", "cmd_info")),
        ],
        scope=BotCommandScopeDefault(),
    )

    user_ids = await get_all_bot_user_ids()
    all_uids = set(user_ids) | set(ADMIN_IDS)
    for uid in all_uids:
        await sync_user_commands(bot, uid)


async def main() -> None:
    await init_db()

    if TELEGRAM_PROXY:
        logger.info("Используется прокси для Telegram API: %s", mask_proxy_url(TELEGRAM_PROXY))
        session = AiohttpSession(proxy=TELEGRAM_PROXY)
        if hasattr(session, "_connector_init") and isinstance(session._connector_init, dict):
            session._connector_init.update(
                family=socket.AF_INET,
                ttl_dns_cache=300,
                keepalive_timeout=120,
            )
            if TELEGRAM_PROXY.lower().startswith("socks5://"):
                session._connector_init["rdns"] = False
    else:
        session = AiohttpSession()
        if hasattr(session, "_connector_init") and isinstance(session._connector_init, dict):
            session._connector_init.update(
                family=socket.AF_INET,
                ttl_dns_cache=300,
                keepalive_timeout=120,
            )

    bot = Bot(
        token=BOT_TOKEN,
        session=session,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())

    dp.message.outer_middleware(AccessControlMiddleware())
    dp.callback_query.outer_middleware(AccessControlMiddleware())

    dp.include_router(router)
    await set_bot_commands(bot)
    trim_memory()

    scheduler_task = asyncio.create_task(reminder_scheduler_loop(bot))

    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    finally:
        scheduler_task.cancel()
        await bot.session.close()
        await engine.dispose()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
