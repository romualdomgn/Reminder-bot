"""Автотесты по замечаниям обоих code review (P1–P3 + BUG/MEM/DB/SEC/EXC).

Запуск на VPS (без установки дополнительных пакетов):
    /opt/reminder_bot/venv/bin/python -m unittest discover -s tests -v
Или через pytest:
    /opt/reminder_bot/venv/bin/pytest -v tests/test_review_fixes.py
"""
import asyncio
import importlib
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "123456:TEST_TOKEN_SECRET_XYZ")
os.environ.setdefault("ADMIN_TELEGRAM_ID", "1001")
os.environ.setdefault("USER_TELEGRAM_ID", "2001,2002")
os.environ.setdefault("TZ_OFFSET_HOURS", "5")
os.environ.setdefault("TELEGRAM_PROXY", "socks5://alice:supersecret@127.0.0.1:49000")


class ReviewFixesAsyncTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db_file = Path(self._tmpdir.name) / "test_reminders.db"

        import config
        import database

        self.config = config
        self.database = database

        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
        from sqlalchemy.pool import NullPool

        self._orig_engine = database.engine
        self._orig_session = database.async_session

        test_url = f"sqlite+aiosqlite:///{self.db_file}"
        database.engine = create_async_engine(test_url, echo=False, poolclass=NullPool)
        from sqlalchemy import event

        event.listen(database.engine.sync_engine, "connect", database._set_sqlite_pragma)
        database.async_session = async_sessionmaker(
            database.engine, expire_on_commit=False, class_=AsyncSession
        )
        await database.init_db()

    async def asyncTearDown(self) -> None:
        await self.database.engine.dispose()
        self.database.engine = self._orig_engine
        self.database.async_session = self._orig_session
        self._tmpdir.cleanup()

    # --- P1.1: атомарная финализация доставки и защита от дубля при сбое ---
    async def test_p1_1_delivery_claim_and_idempotent_finalize(self) -> None:
        db = self.database
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        rem = await db.create_reminder(1001, "Позвонить", now - timedelta(minutes=1), "once")

        claimed1 = await db.claim_due_reminder(rem.id, rem.remind_at, now, lease_seconds=60)
        claimed2 = await db.claim_due_reminder(rem.id, rem.remind_at, now, lease_seconds=60)
        self.assertTrue(claimed1)
        self.assertFalse(claimed2)

        # Имитация отправки: создаём pending, сохраняем message_id (как после fallback),
        # затем повторный вызов get_or_create_pending_for_trigger видит already_sent=True
        notif, already = await db.get_or_create_pending_for_trigger(
            1001, rem.id, rem.text, rem.recurrence, rem.remind_at
        )
        self.assertFalse(already)
        await db.update_pending_notification_msg_id(notif.id, 777)

        notif2, already2 = await db.get_or_create_pending_for_trigger(
            1001, rem.id, rem.text, rem.recurrence, rem.remind_at
        )
        self.assertTrue(already2)
        self.assertEqual(notif2.id, notif.id)
        self.assertEqual(notif2.message_id, 777)

        ok = await db.finalize_triggered_delivery(
            notif_id=notif.id,
            message_id=777,
            reminder_id=rem.id,
            offset_mins=300,
            expected_remind_at=rem.remind_at,
        )
        self.assertTrue(ok)
        self.assertIsNone(await db.get_reminder_by_id(1001, rem.id))

    # --- P1.2: отложить сохраняет уведомление при отсутствии исходного напоминания ---
    async def test_p1_2_snooze_preserves_notification_when_reminder_missing(self) -> None:
        db = self.database
        notif = await db.add_pending_notification(1001, 999999, 555, "Призрак", "once")
        new_utc = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(minutes=30)

        status, msg_id = await db.claim_and_snooze_notification(1001, notif.id, new_utc)
        self.assertEqual(status, "reminder_not_found")
        self.assertEqual(msg_id, 0)

        still_there = await db.get_pending_notification_by_id(1001, notif.id)
        self.assertIsNotNone(still_there)

    # --- P1.3: конкурентные snooze/ack к одному уведомлению ---
    async def test_p1_3_concurrent_snooze_and_ack(self) -> None:
        db = self.database
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        rem = await db.create_reminder(1001, "Встреча", now - timedelta(minutes=1), "daily")
        notif = await db.add_pending_notification(1001, rem.id, 888, rem.text, "daily")
        new_utc = now + timedelta(minutes=10)

        r1, r2 = await asyncio.gather(
            db.claim_and_snooze_notification(1001, notif.id, new_utc),
            db.claim_and_snooze_notification(1001, notif.id, new_utc),
        )
        statuses = sorted([r1[0], r2[0]])
        self.assertEqual(statuses, ["already_processed", "ok"])

        active = await db.get_active_reminders(1001)
        # Исходное daily + ровно один snooze-клон
        self.assertEqual(len(active), 2)

        # Повторный ack должен вернуть None
        ack = await db.claim_and_ack_notification(1001, notif.id)
        self.assertIsNone(ack)

    # --- P1.5: атомарный PATCH при невалидном тексте не меняет дату ---
    async def test_p1_5_patch_invalid_text_does_not_mutate_datetime(self) -> None:
        try:
            from fastapi import HTTPException
            from webapp.auth import WebAppUser
            from webapp.routes_reminders import edit_reminder
            from webapp.schemas import ReminderUpdateRequest
        except ImportError:
            self.skipTest("fastapi не установлен в этом окружении")

        db = self.database
        orig_utc = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=2)
        rem = await db.create_reminder(1001, "Оригинал", orig_utc, "once")

        user = WebAppUser(user_id=1001, first_name="Admin", username="adm", is_admin=True)
        future_date = (datetime.now(timezone.utc) + timedelta(days=5)).date().isoformat()
        payload = ReminderUpdateRequest(date=future_date, time="16:00", text="<b>   </b>")

        with self.assertRaises(HTTPException) as ctx:
            await edit_reminder(rem.id, payload, user)
        self.assertEqual(ctx.exception.status_code, 400)

        unchanged = await db.get_reminder_by_id(1001, rem.id)
        self.assertEqual(unchanged.remind_at, orig_utc)
        self.assertEqual(unchanged.text, "Оригинал")

    # --- P2.8: время прошло во время FSM-создания ---
    async def test_p2_8_time_passed_during_fsm_returns_to_time_step(self) -> None:
        try:
            from handlers.reminders_create import save_reminder_with_recurrence
            from handlers.states import ReminderFSM
        except ImportError:
            self.skipTest("aiogram не установлен в этом окружении")

        db = self.database
        user_now, _ = await db.get_user_now(1001)
        past_local = user_now.replace(tzinfo=None) - timedelta(minutes=2)

        fake_state = AsyncMock()
        fake_state.get_data.return_value = {
            "reminder_text": "Просроченное",
            "target_date": past_local.date().isoformat(),
            "target_time": past_local.time().replace(second=0, microsecond=0).isoformat(),
        }
        fake_bot = AsyncMock()

        with patch("handlers.reminders_create.prompt_for_time", new=AsyncMock()) as mocked_prompt:
            await save_reminder_with_recurrence(fake_bot, 1001, fake_state, "once")
            mocked_prompt.assert_awaited_once()
            fake_state.set_state.assert_awaited_with(ReminderFSM.waiting_for_time)

        self.assertEqual(len(await db.get_active_reminders(1001)), 0)

    # --- P2.9: временная ошибка удаления возвращает ID в tracked_messages ---
    async def test_p2_9_transient_delete_error_requeues_tracked_ids(self) -> None:
        try:
            from aiogram.exceptions import TelegramBadRequest
            from handlers.common import safe_delete_messages_batch
        except ImportError:
            self.skipTest("aiogram не установлен в этом окружении")

        db = self.database
        fake_bot = AsyncMock()
        fake_bot.delete_messages.side_effect = RuntimeError("batch failed")

        async def fake_delete_message(chat_id: int, message_id: int):
            if message_id == 101:
                raise TimeoutError("temporary network timeout")
            if message_id == 102:
                raise TelegramBadRequest(
                    method=MagicMock(), message="Bad Request: message to delete not found"
                )
            return True

        fake_bot.delete_message.side_effect = fake_delete_message

        failed = await safe_delete_messages_batch(fake_bot, 1001, [101, 102, 103])
        self.assertEqual(failed, [101])

        popped = await db.pop_tracked_messages(1001)
        self.assertEqual(popped, [101])

    # --- P2.11 + BUG-3: Undo в SQLite, серверный TTL и одноразовость ---
    async def test_p2_11_undo_sqlite_ttl_and_single_use(self) -> None:
        db = self.database
        future = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=3)

        await db.save_undo_reminder(1001, "Удалённое", future, "once", ttl_seconds=60)
        res1, res2 = await asyncio.gather(
            db.pop_undo_reminder(1001),
            db.pop_undo_reminder(1001),
        )
        non_none = [r for r in (res1, res2) if r is not None]
        self.assertEqual(len(non_none), 1)
        self.assertEqual(non_none[0]["text"], "Удалённое")

        # Истекший TTL
        await db.save_undo_reminder(1001, "Старое", future, "once", ttl_seconds=-1)
        self.assertIsNone(await db.pop_undo_reminder(1001))

    # --- P2.12 + BUG-1: удаление пользователя чистит связанные таблицы, не трогая приглашённых ---
    async def test_p2_12_remove_user_cleans_related_keeps_invitees(self) -> None:
        db = self.database
        await db.add_bot_user(3001, "Пригласивший", invited_by=1001)
        await db.add_bot_user(3002, "Приглашённый", invited_by=3001)
        await db.set_user_offset_minutes(3001, 180)
        await db.set_panel_message_id(3001, 41)
        await db.add_tracked_message(3001, 42)
        await db.create_reminder(
            3001, "Тест", datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=1)
        )

        removed, msg_ids = await db.remove_bot_user_with_cleanup(3001)
        self.assertTrue(removed)
        self.assertEqual(msg_ids, [41, 42])

        # Связанные записи удалённого пользователя очищены
        self.assertIsNone(await db.get_bot_user(3001))
        self.assertIsNone(await db.get_panel_message_id(3001))
        self.assertFalse(await db.has_tracked_messages(3001))
        self.assertEqual(
            await db.get_user_offset_minutes(3001),
            self.config.DEFAULT_TZ_OFFSET_HOURS * 60,
        )

        # Приглашённый пользователь сохранён, и его invited_by остался для истории админа
        invitee = await db.get_bot_user(3002)
        self.assertIsNotNone(invitee)
        self.assertEqual(invitee.invited_by, 3001)

    # --- P2.16 + DB-1: параллельный init_db на пустой БД ---
    async def test_p2_16_parallel_init_db(self) -> None:
        db = self.database
        await asyncio.gather(db.init_db(), db.init_db(), db.init_db())
        ids = set(await db.get_all_bot_user_ids())
        self.assertTrue({1001, 2001, 2002}.issubset(ids))

    # --- P3.17 + SEC-1: маскирование прокси и токена ---
    def test_p3_17_secrets_masking(self) -> None:
        masked = self.config.mask_proxy_url("socks5://alice:supersecret@127.0.0.1:49000")
        self.assertEqual(masked, "socks5://***:***@127.0.0.1:49000")
        self.assertNotIn("supersecret", masked)

        sanitized = self.config.sanitize_secrets(
            f"Error on https://api.telegram.org/bot{self.config.BOT_TOKEN}/sendMessage via {self.config.TELEGRAM_PROXY}"
        )
        self.assertNotIn(self.config.BOT_TOKEN, sanitized)
        self.assertNotIn("supersecret", sanitized)

    # --- P3.18: имя пользователя из пробелов возвращает ошибку валидации ---
    def test_p3_18_whitespace_username_rejected(self) -> None:
        from pydantic import ValidationError
        from webapp.schemas import UserCreateRequest, UserUpdateRequest

        with self.assertRaises(ValidationError):
            UserCreateRequest(user_id=555, name="    ")
        with self.assertRaises(ValidationError):
            UserUpdateRequest(name="  \t  ")

        ok = UserCreateRequest(user_id=555, name="  Иван  ")
        self.assertEqual(ok.name, "Иван")

    # --- UX-6 / Блок Б #6: Камчатка UTC+12 присутствует, UTC+0 убран из пресетов ---
    def test_tz_presets_kamchatka_and_no_utc0(self) -> None:
        db = self.database
        self.assertNotIn(0, db.TZ_ABBR_MAP)
        self.assertIn(720, db.TZ_ABBR_MAP)
        self.assertEqual(db.format_tz_label(0), "UTC+0")
        self.assertEqual(db.format_tz_label(720), "Камчатка (UTC+12)")


if __name__ == "__main__":
    unittest.main()
