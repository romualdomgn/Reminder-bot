import html
import logging
import socket
import aiohttp
from aiohttp_socks import ProxyConnector

from config import ADMIN_IDS, BOT_TOKEN, WEBAPP_TELEGRAM_PROXY, WEBAPP_URL, sanitize_secrets
from database import add_tracked_message, get_pending_notifications_count, get_user_language, is_admin_id, user_has_invited_anyone
from i18n import DEFAULT_LANG, t

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
        async with aiohttp.ClientSession(connector=_build_connector(), timeout=_TG_API_TIMEOUT) as session:
            async with session.post(url, json=payload) as resp:
                body = await resp.json(content_type=None)
                if resp.status == 200 and isinstance(body, dict) and body.get("ok"):
                    return body
                logger.warning("Telegram API %s returned HTTP %s from webapp", method, resp.status)
                return None
    except Exception as exc:
        logger.warning("Telegram API %s failed from webapp: %s", method, sanitize_secrets(str(exc)))
        return None


async def cleanup_chat_message(user_id: int, message_id: int, track_on_failure: bool = True) -> None:
    if not message_id or message_id <= 0:
        return
    res = await _tg_api_call("deleteMessage", {"chat_id": user_id, "message_id": message_id})
    if not res and track_on_failure:
        await add_tracked_message(user_id, message_id)


async def sync_chat_commands_from_webapp(user_id: int, lang: str) -> None:
    pending_count = await get_pending_notifications_count(user_id)
    if is_admin_id(user_id):
        commands = [{"command": "start", "description": t(lang, "cmd_start")}]
        if pending_count > 0:
            commands.append({"command": "notifications", "description": t(lang, "cmd_notifications")})
        commands.extend([
            {"command": "reminders", "description": t(lang, "cmd_reminders")},
            {"command": "users", "description": t(lang, "cmd_users")},
            {"command": "settings", "description": t(lang, "cmd_settings")},
        ])
    else:
        has_sec = await user_has_invited_anyone(user_id)
        commands = [{"command": "start", "description": t(lang, "cmd_start")}]
        if pending_count > 0:
            commands.append({"command": "notifications", "description": t(lang, "cmd_notifications")})
        commands.append({"command": "reminders", "description": t(lang, "cmd_reminders")})
        if has_sec:
            commands.append({"command": "user", "description": t(lang, "cmd_users")})
        commands.extend([
            {"command": "settings", "description": t(lang, "cmd_settings")},
            {"command": "info", "description": t(lang, "cmd_info")},
        ])
    await _tg_api_call("setMyCommands", {"commands": commands, "scope": {"type": "chat", "chat_id": user_id}})


async def send_welcome_invite(new_user_id: int, lang: str = DEFAULT_LANG) -> None:
    if WEBAPP_URL:
        await _tg_api_call(
            "setChatMenuButton",
            {"chat_id": new_user_id, "menu_button": {"type": "web_app", "text": "Mini App", "web_app": {"url": WEBAPP_URL}}},
        )
    res = await _tg_api_call("sendMessage", {"chat_id": new_user_id, "text": t(lang, "welcome_invite")})
    msg_id = (res or {}).get("result", {}).get("message_id")
    if msg_id:
        await add_tracked_message(new_user_id, int(msg_id))


async def notify_admins_new_user(new_user_id: int, new_name: str, inviter_id: int, inviter_name: str) -> None:
    inviter_label = f"{html.escape(inviter_name)} (<code>{inviter_id}</code>)" if inviter_name else f"<code>{inviter_id}</code>"
    for admin_id in ADMIN_IDS:
        admin_lang = await get_user_language(admin_id)
        text = t(admin_lang, "admin_new_user_alert", new_name=html.escape(new_name), new_user_id=new_user_id, inviter_label=inviter_label)
        reply_markup = {"inline_keyboard": [[{"text": t(admin_lang, "btn_ok"), "callback_data": "ack_alert"}]]}
        await _tg_api_call("sendMessage", {"chat_id": admin_id, "text": text, "parse_mode": "HTML", "reply_markup": reply_markup})


async def notify_user_removed(target_user_id: int, lang: str = DEFAULT_LANG) -> None:
    await _tg_api_call("setChatMenuButton", {"chat_id": target_user_id, "menu_button": {"type": "commands"}})
    await _tg_api_call("sendMessage", {"chat_id": target_user_id, "text": t(lang, "user_removed_notice"), "parse_mode": "HTML"})
