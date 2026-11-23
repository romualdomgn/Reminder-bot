import html
import logging
import socket
import aiohttp
from aiohttp_socks import ProxyConnector

from config import (
    ADMIN_IDS,
    BOT_TOKEN,
    WEBAPP_TELEGRAM_PROXY,
    WEBAPP_URL,
    WELCOME_INVITE_TEXT,
    sanitize_secrets,
)
from database import add_tracked_message

logger = logging.getLogger(__name__)

_TG_API_TIMEOUT = aiohttp.ClientTimeout(total=5)


def _build_connector() -> aiohttp.BaseConnector:
    if WEBAPP_TELEGRAM_PROXY:
        return ProxyConnector.from_url(
            WEBAPP_TELEGRAM_PROXY,
            rdns=not WEBAPP_TELEGRAM_PROXY.lower().startswith("socks5://"),
            family=socket.AF_INET,
        )
    return aiohttp.TCPConnector(family=socket.AF_INET)


async def _tg_api_call(method: str, payload: dict) -> dict | None:
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"
    try:
        async with aiohttp.ClientSession(
            connector=_build_connector(),
            timeout=_TG_API_TIMEOUT,
        ) as session:
            async with session.post(url, json=payload) as resp:
                body = await resp.json(content_type=None)
                if resp.status == 200 and isinstance(body, dict) and body.get("ok"):
                    return body
                logger.warning(
                    "Telegram API %s returned HTTP %s from webapp", method, resp.status
                )
                return None
    except Exception as exc:
        logger.warning(
            "Telegram API %s failed from webapp: %s",
            method,
            sanitize_secrets(str(exc)),
        )
        return None


async def cleanup_chat_message(
    user_id: int, message_id: int, track_on_failure: bool = True
) -> None:
    """Удаляет уведомление в чате Telegram сразу; при сбое передаёт ID боту на очистку."""
    if not message_id or message_id <= 0:
        return
    res = await _tg_api_call(
        "deleteMessage",
        {"chat_id": user_id, "message_id": message_id},
    )
    if not res and track_on_failure:
        await add_tracked_message(user_id, message_id)


async def send_welcome_invite(new_user_id: int) -> None:
    if WEBAPP_URL:
        await _tg_api_call(
            "setChatMenuButton",
            {
                "chat_id": new_user_id,
                "menu_button": {
                    "type": "web_app",
                    "text": "Mini App",
                    "web_app": {"url": WEBAPP_URL},
                },
            },
        )
    res = await _tg_api_call(
        "sendMessage",
        {"chat_id": new_user_id, "text": WELCOME_INVITE_TEXT},
    )
    msg_id = (res or {}).get("result", {}).get("message_id")
    if msg_id:
        await add_tracked_message(new_user_id, int(msg_id))


async def notify_admins_new_user(
    new_user_id: int,
    new_name: str,
    inviter_id: int,
    inviter_name: str,
) -> None:
    inviter_label = (
        f"{html.escape(inviter_name)} (<code>{inviter_id}</code>)"
        if inviter_name
        else f"<code>{inviter_id}</code>"
    )
    text = (
        "👤 <b>Добавлен новый пользователь</b>\n\n"
        f"👤 <b>Имя:</b> {html.escape(new_name)}\n"
        f"🆔 <b>Telegram ID:</b> <code>{new_user_id}</code>\n"
        f"➕ <b>Пригласил:</b> {inviter_label}"
    )
    reply_markup = {
        "inline_keyboard": [[{"text": "Ok", "callback_data": "ack_alert"}]]
    }
    for admin_id in ADMIN_IDS:
        await _tg_api_call(
            "sendMessage",
            {
                "chat_id": admin_id,
                "text": text,
                "parse_mode": "HTML",
                "reply_markup": reply_markup,
            },
        )


async def notify_user_removed(target_user_id: int) -> None:
    await _tg_api_call(
        "setChatMenuButton",
        {"chat_id": target_user_id, "menu_button": {"type": "commands"}},
    )
    await _tg_api_call(
        "sendMessage",
        {
            "chat_id": target_user_id,
            "text": "⛔ <b>Вы удалены из списка пользователей, доступ к боту прекращён.</b>",
            "parse_mode": "HTML",
        },
    )
