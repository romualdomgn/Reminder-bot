import asyncio
import html
import json
import logging
import urllib.request

from config import ADMIN_IDS, BOT_TOKEN, WEBAPP_URL
from database import add_tracked_message

logger = logging.getLogger(__name__)

WELCOME_INVITE_TEXT = (
    "Привет. Вы приглашены в бот Напоминалкин.\n\n"
    "Нажмите Menu или Start.\n\n"
    "Ознакомиться с тем, как работает бот можно в Меню в разделе Информация.\n\n"
    "Перед началом работы задайте в Настройках свой текущий часовой пояс, чтобы время бота и Вашего устройства совпадало"
)


def _tg_api_call_sync(method: str, payload: dict) -> dict | None:
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=4) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            if body.get("ok"):
                return body
            return None
    except Exception as exc:
        logger.warning("Telegram API %s failed from webapp: %s", method, exc)
        return None


async def cleanup_chat_message(user_id: int, message_id: int) -> None:
    """Удаляет уведомление в чате Telegram сразу; при сбое передаёт ID боту на очистку."""
    if not message_id or message_id <= 0:
        return
    res = await asyncio.to_thread(
        _tg_api_call_sync,
        "deleteMessage",
        {"chat_id": user_id, "message_id": message_id},
    )
    if not res:
        await add_tracked_message(user_id, message_id)


async def send_welcome_invite(new_user_id: int) -> None:
    if WEBAPP_URL:
        await asyncio.to_thread(
            _tg_api_call_sync,
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
    res = await asyncio.to_thread(
        _tg_api_call_sync,
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
        await asyncio.to_thread(
            _tg_api_call_sync,
            "sendMessage",
            {
                "chat_id": admin_id,
                "text": text,
                "parse_mode": "HTML",
                "reply_markup": reply_markup,
            },
        )


async def notify_user_removed(target_user_id: int) -> None:
    await asyncio.to_thread(
        _tg_api_call_sync,
        "setChatMenuButton",
        {"chat_id": target_user_id, "menu_button": {"type": "commands"}},
    )
    await asyncio.to_thread(
        _tg_api_call_sync,
        "sendMessage",
        {
            "chat_id": target_user_id,
            "text": "⛔ <b>Вы удалены из списка пользователей, доступ к боту прекращён.</b>",
            "parse_mode": "HTML",
        },
    )
