import asyncio
import calendar
from datetime import datetime, date, timezone, timedelta
from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Integer,
    String,
    event,
    or_,
    select,
    delete,
    func,
    update,
)
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.pool import NullPool

from config import (
    DATABASE_URL,
    DEFAULT_TZ_OFFSET_HOURS,
    ADMIN_IDS,
    USER_IDS,
    clear_rendered_reminders_state,
)

engine = create_async_engine(DATABASE_URL, echo=False, poolclass=NullPool)


@event.listens_for(engine.sync_engine, "connect")
def _set_sqlite_pragma(dbapi_connection, _connection_record) -> None:
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA cache_size = -2000")
        cursor.execute("PRAGMA busy_timeout = 5000")
        cursor.execute("PRAGMA journal_mode = WAL")
    finally:
        cursor.close()


async_session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

UNDO_TTL_SECONDS = 60

RECURRENCE_LABELS: dict[str, str] = {
    "once": "Один раз",
    "daily": "🔁 Каждый день",
    "weekly": "🔁 Раз в неделю",
    "biweekly": "🔁 Каждые две недели",
    "monthly": "🔁 Ежемесячно",
    "yearly": "🔁 Ежегодно",
}

TZ_ABBR_MAP: dict[int, str] = {
    60: "London (UTC+1)",
    120: "Калининград (UTC+2)",
    180: "Москва (UTC+3)",
    240: "Самара (UTC+4)",
    300: "Магнитогорск (UTC+5)",
    360: "Омск (UTC+6)",
    420: "Красноярск (UTC+7)",
    480: "Иркутск (UTC+8)",
    540: "Якутск (UTC+9)",
    600: "Хабаровск (UTC+10)",
    660: "Магадан (UTC+11)",
    720: "Камчатка (UTC+12)",
}


def format_recurrence_label(recurrence: str) -> str:
    return RECURRENCE_LABELS.get(recurrence, "")


def add_two_weeks_date(src_date: date) -> date:
    return src_date + timedelta(days=14)


def add_one_month_date(src_date: date) -> date:
    year = src_date.year + (src_date.month // 12)
    month = (src_date.month % 12) + 1
    max_day = calendar.monthrange(year, month)[1]
    return date(year, month, min(src_date.day, max_day))


def add_one_year_date(src_date: date) -> date:
    year = src_date.year + 1
    max_day = calendar.monthrange(year, src_date.month)[1]
    return date(year, src_date.month, min(src_date.day, max_day))


def compute_next_recurring_local_dt(
    current_local_dt: datetime, recurrence: str, now_local_dt: datetime
) -> datetime:
    next_dt = current_local_dt
    while next_dt <= now_local_dt:
        if recurrence == "daily":
            next_dt = next_dt + timedelta(days=1)
        elif recurrence == "weekly":
            next_dt = next_dt + timedelta(days=7)
        elif recurrence == "biweekly":
            next_dt = next_dt + timedelta(days=14)
        elif recurrence == "monthly":
            next_date = add_one_month_date(next_dt.date())
            next_dt = datetime.combine(next_date, next_dt.time())
        elif recurrence == "yearly":
            next_date = add_one_year_date(next_dt.date())
            next_dt = datetime.combine(next_date, next_dt.time())
        else:
            break
    return next_dt


class Base(DeclarativeBase):
    pass


class AppMeta(Base):
    __tablename__ = "app_meta"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(String(255), default="", nullable=False)


class BotUser(Base):
    __tablename__ = "bot_users"

    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    invited_by: Mapped[int | None] = mapped_column(BigInteger, index=True, nullable=True)
    has_invited: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None), nullable=False
    )


class Reminder(Base):
    __tablename__ = "reminders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True, nullable=False)
    text: Mapped[str] = mapped_column(String(1024), nullable=False)
    remind_at: Mapped[datetime] = mapped_column(DateTime, index=True, nullable=False)
    recurrence: Mapped[str] = mapped_column(String(32), default="once", nullable=False)
    is_sent: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    processing_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, default=None)


class PendingNotification(Base):
    """Хранит активные (непрочитанные) сработавшие уведомления для раздела /notifications."""
    __tablename__ = "pending_notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True, nullable=False)
    reminder_id: Mapped[int] = mapped_column(Integer, nullable=False)
    message_id: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    text: Mapped[str] = mapped_column(String(1024), nullable=False)
    recurrence: Mapped[str] = mapped_column(String(32), default="", nullable=False)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, default=None)


class DeletedReminderUndo(Base):
    """Хранит последнее удалённое напоминание пользователя для отмены удаления с серверным TTL."""
    __tablename__ = "deleted_reminders_undo"

    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    text: Mapped[str] = mapped_column(String(1024), nullable=False)
    remind_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    recurrence: Mapped[str] = mapped_column(String(32), default="once", nullable=False)
    number_label: Mapped[str] = mapped_column(String(32), default="", nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class UserPanel(Base):
    __tablename__ = "user_panels"

    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    panel_message_id: Mapped[int] = mapped_column(BigInteger, nullable=False)


class UserSettings(Base):
    __tablename__ = "user_settings"

    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    tz_offset_minutes: Mapped[int] = mapped_column(
        Integer, nullable=False, default=DEFAULT_TZ_OFFSET_HOURS * 60
    )


class TrackedMessage(Base):
    __tablename__ = "tracked_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True, nullable=False)
    message_id: Mapped[int] = mapped_column(BigInteger, nullable=False)


async def _add_column_if_missing(conn, table: str, col: str, ddl: str) -> None:
    res = await conn.exec_driver_sql(f"PRAGMA table_info({table})")
    cols = {row[1] for row in res.fetchall()}
    if col in cols:
        return
    try:
        await conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}")
    except OperationalError as exc:
        if "duplicate column name" not in str(exc).lower():
            raise


async def init_db() -> None:
    last_err: Exception | None = None
    for attempt in range(5):
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)

                await _add_column_if_missing(
                    conn, "reminders", "recurrence", "VARCHAR(32) NOT NULL DEFAULT 'once'"
                )
                await _add_column_if_missing(
                    conn, "reminders", "processing_until", "DATETIME DEFAULT NULL"
                )
                await _add_column_if_missing(
                    conn, "pending_notifications", "scheduled_at", "DATETIME DEFAULT NULL"
                )
                await _add_column_if_missing(
                    conn, "bot_users", "name", "VARCHAR(255) NOT NULL DEFAULT ''"
                )
                await _add_column_if_missing(
                    conn, "bot_users", "invited_by", "BIGINT DEFAULT NULL"
                )
                await _add_column_if_missing(
                    conn, "bot_users", "has_invited", "BOOLEAN NOT NULL DEFAULT 0"
                )
                await conn.exec_driver_sql(
                    "CREATE UNIQUE INDEX IF NOT EXISTS uq_pending_rem_sched "
                    "ON pending_notifications (reminder_id, scheduled_at) "
                    "WHERE scheduled_at IS NOT NULL"
                )

            async with async_session() as session:
                seed_stmt = (
                    sqlite_insert(AppMeta)
                    .values(key="initial_users_seeded", value="1")
                    .on_conflict_do_nothing(index_elements=["key"])
                )
                seed_res = await session.execute(seed_stmt)
                if (seed_res.rowcount or 0) > 0:
                    existing_count = await session.scalar(
                        select(func.count()).select_from(BotUser)
                    )
                    if not existing_count:
                        for uid in USER_IDS:
                            if uid not in ADMIN_IDS:
                                await session.execute(
                                    sqlite_insert(BotUser)
                                    .values(user_id=uid, name="Пользователь", is_admin=False)
                                    .on_conflict_do_nothing(index_elements=["user_id"])
                                )

                for admin_id in ADMIN_IDS:
                    await session.execute(
                        sqlite_insert(BotUser)
                        .values(user_id=admin_id, name="Администратор", is_admin=True)
                        .on_conflict_do_update(
                            index_elements=["user_id"],
                            set_={"is_admin": True},
                        )
                    )
                    await session.execute(
                        update(BotUser)
                        .where(BotUser.user_id == admin_id, BotUser.name == "")
                        .values(name="Администратор")
                    )

                await session.commit()
            return
        except OperationalError as exc:
            last_err = exc
            msg = str(exc).lower()
            if ("locked" in msg or "busy" in msg) and attempt < 4:
                await asyncio.sleep(0.3 * (attempt + 1))
                continue
            raise
    if last_err:
        raise last_err


# --- Функции для работы с PendingNotification ---

async def add_pending_notification(
    user_id: int,
    reminder_id: int,
    message_id: int,
    text: str,
    recurrence: str,
    scheduled_at: datetime | None = None,
) -> PendingNotification:
    async with async_session() as session:
        notif = PendingNotification(
            user_id=user_id,
            reminder_id=reminder_id,
            message_id=message_id,
            text=text,
            recurrence=recurrence,
            scheduled_at=scheduled_at.replace(tzinfo=None) if scheduled_at else None,
        )
        session.add(notif)
        await session.commit()
        await session.refresh(notif)
        return notif


async def get_or_create_pending_for_trigger(
    user_id: int,
    reminder_id: int,
    text_val: str,
    recurrence: str,
    scheduled_at: datetime,
) -> tuple[PendingNotification, bool]:
    """Идемпотентно создаёт или находит pending-уведомление для конкретного срабатывания."""
    sched_naive = scheduled_at.replace(tzinfo=None)
    async with async_session() as session:
        await session.execute(
            sqlite_insert(PendingNotification)
            .values(
                user_id=user_id,
                reminder_id=reminder_id,
                message_id=0,
                text=text_val,
                recurrence=recurrence,
                scheduled_at=sched_naive,
            )
            .on_conflict_do_nothing()
        )
        await session.commit()
        res = await session.execute(
            select(PendingNotification).where(
                PendingNotification.reminder_id == reminder_id,
                PendingNotification.scheduled_at == sched_naive,
            )
        )
        notif = res.scalar_one()
        return notif, bool(notif.message_id and notif.message_id > 0)


async def update_pending_notification_msg_id(notif_id: int, message_id: int) -> None:
    async with async_session() as session:
        notif = await session.get(PendingNotification, notif_id)
        if notif:
            notif.message_id = message_id
            await session.commit()


async def get_pending_notifications(user_id: int) -> list:
    async with async_session() as session:
        stmt = (
            select(
                PendingNotification.id,
                PendingNotification.reminder_id,
                PendingNotification.message_id,
                PendingNotification.text,
                PendingNotification.recurrence,
            )
            .where(PendingNotification.user_id == user_id)
            .order_by(PendingNotification.id.asc())
        )
        result = await session.execute(stmt)
        return list(result.all())


async def get_pending_notification_by_id(
    user_id: int, notif_id: int
) -> PendingNotification | None:
    if notif_id <= 0:
        return None
    async with async_session() as session:
        stmt = select(PendingNotification).where(
            PendingNotification.user_id == user_id,
            PendingNotification.id == notif_id,
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()


async def get_pending_notification_by_message_id(
    user_id: int, message_id: int
) -> PendingNotification | None:
    if message_id <= 0:
        return None
    async with async_session() as session:
        stmt = select(PendingNotification).where(
            PendingNotification.user_id == user_id,
            PendingNotification.message_id == message_id,
        )
        result = await session.execute(stmt)
        return result.scalars().first()


async def remove_pending_notification(notif_id: int) -> None:
    async with async_session() as session:
        notif = await session.get(PendingNotification, notif_id)
        if notif:
            await session.delete(notif)
            await session.commit()


async def claim_and_ack_notification(
    user_id: int, notif_id: int, fallback_message_id: int = 0
) -> int | None:
    """Атомарно удаляет pending-уведомление. Возвращает message_id или None, если уже обработано."""
    async with async_session() as session:
        if notif_id > 0:
            res = await session.execute(
                delete(PendingNotification)
                .where(
                    PendingNotification.id == notif_id,
                    PendingNotification.user_id == user_id,
                )
                .returning(PendingNotification.message_id)
            )
            row = res.first()
            if row is not None:
                await session.commit()
                return int(row[0] or 0)
        if fallback_message_id > 0:
            res = await session.execute(
                delete(PendingNotification)
                .where(
                    PendingNotification.user_id == user_id,
                    PendingNotification.message_id == fallback_message_id,
                )
                .returning(PendingNotification.message_id)
            )
            row = res.first()
            if row is not None:
                await session.commit()
                return int(row[0] or 0)
        await session.rollback()
        return None


async def claim_and_snooze_notification(
    user_id: int,
    notif_id: int,
    new_remind_at_utc: datetime,
    fallback_message_id: int = 0,
) -> tuple[str, int]:
    """Одной транзакцией удаляет уведомление и переносит/клонирует напоминание."""
    remind_at_naive = new_remind_at_utc.replace(tzinfo=None)
    async with async_session() as session:
        row = None
        if notif_id > 0:
            res = await session.execute(
                delete(PendingNotification)
                .where(
                    PendingNotification.id == notif_id,
                    PendingNotification.user_id == user_id,
                )
                .returning(PendingNotification.reminder_id, PendingNotification.message_id)
            )
            row = res.first()
        if row is None and fallback_message_id > 0:
            res = await session.execute(
                delete(PendingNotification)
                .where(
                    PendingNotification.user_id == user_id,
                    PendingNotification.message_id == fallback_message_id,
                )
                .returning(PendingNotification.reminder_id, PendingNotification.message_id)
            )
            row = res.first()

        if row is None:
            await session.rollback()
            return "already_processed", 0

        reminder_id, msg_id = int(row[0]), int(row[1] or 0)
        rem_res = await session.execute(
            select(Reminder).where(
                Reminder.id == reminder_id,
                Reminder.user_id == user_id,
            )
        )
        reminder = rem_res.scalar_one_or_none()
        if not reminder:
            await session.rollback()
            return "reminder_not_found", 0

        if reminder.is_sent:
            reminder.remind_at = remind_at_naive
            reminder.is_sent = False
            reminder.processing_until = None
        else:
            session.add(
                Reminder(
                    user_id=user_id,
                    text=reminder.text,
                    remind_at=remind_at_naive,
                    recurrence="once",
                    is_sent=False,
                )
            )
        await session.commit()
        return "ok", msg_id


async def claim_and_repeat_notification(
    user_id: int, notif_id: int, fallback_message_id: int = 0
) -> tuple[str, str, int]:
    """Атомарно забирает уведомление для повтора."""
    async with async_session() as session:
        row = None
        if notif_id > 0:
            res = await session.execute(
                delete(PendingNotification)
                .where(
                    PendingNotification.id == notif_id,
                    PendingNotification.user_id == user_id,
                )
                .returning(
                    PendingNotification.reminder_id,
                    PendingNotification.message_id,
                    PendingNotification.text,
                )
            )
            row = res.first()
        if row is None and fallback_message_id > 0:
            res = await session.execute(
                delete(PendingNotification)
                .where(
                    PendingNotification.user_id == user_id,
                    PendingNotification.message_id == fallback_message_id,
                )
                .returning(
                    PendingNotification.reminder_id,
                    PendingNotification.message_id,
                    PendingNotification.text,
                )
            )
            row = res.first()

        if row is None:
            await session.rollback()
            return "already_processed", "", 0

        reminder_id, msg_id, reminder_text = int(row[0]), int(row[1] or 0), str(row[2] or "")
        if not reminder_text:
            rem_res = await session.execute(
                select(Reminder).where(
                    Reminder.id == reminder_id,
                    Reminder.user_id == user_id,
                )
            )
            rem = rem_res.scalar_one_or_none()
            if rem:
                reminder_text = rem.text

        await session.commit()
        if not reminder_text:
            return "not_found", "", msg_id
        return "ok", reminder_text, msg_id


async def get_pending_notifications_count(user_id: int) -> int:
    async with async_session() as session:
        count = await session.scalar(
            select(func.count())
            .select_from(PendingNotification)
            .where(PendingNotification.user_id == user_id)
        )
        return count or 0


# --- Undo удаления в SQLite с серверным TTL ---

async def save_undo_reminder(
    user_id: int,
    text_val: str,
    remind_at_utc: datetime,
    recurrence: str,
    number_label: str = "",
    ttl_seconds: int = UNDO_TTL_SECONDS,
) -> None:
    now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
    expires_at = now_utc + timedelta(seconds=ttl_seconds)
    remind_naive = remind_at_utc.replace(tzinfo=None)
    stmt = (
        sqlite_insert(DeletedReminderUndo)
        .values(
            user_id=user_id,
            text=text_val,
            remind_at=remind_naive,
            recurrence=recurrence,
            number_label=number_label,
            expires_at=expires_at,
        )
        .on_conflict_do_update(
            index_elements=["user_id"],
            set_={
                "text": text_val,
                "remind_at": remind_naive,
                "recurrence": recurrence,
                "number_label": number_label,
                "expires_at": expires_at,
            },
        )
    )
    async with async_session() as session:
        await session.execute(stmt)
        await session.commit()


async def pop_undo_reminder(user_id: int) -> dict | None:
    now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
    async with async_session() as session:
        res = await session.execute(
            delete(DeletedReminderUndo)
            .where(DeletedReminderUndo.user_id == user_id)
            .returning(
                DeletedReminderUndo.text,
                DeletedReminderUndo.remind_at,
                DeletedReminderUndo.recurrence,
                DeletedReminderUndo.number_label,
                DeletedReminderUndo.expires_at,
            )
        )
        row = res.first()
        await session.commit()
        if not row or row[4] < now_utc:
            return None
        return {
            "text": row[0],
            "remind_at": row[1],
            "recurrence": row[2],
            "number_label": row[3],
        }


async def clear_undo_reminder(user_id: int) -> None:
    async with async_session() as session:
        await session.execute(
            delete(DeletedReminderUndo).where(DeletedReminderUndo.user_id == user_id)
        )
        await session.commit()


# --- Управление доступом и пользователями ---

def is_admin_id(user_id: int) -> bool:
    return user_id in ADMIN_IDS


async def is_user_allowed(user_id: int) -> bool:
    if user_id in ADMIN_IDS:
        return True
    async with async_session() as session:
        exists = await session.scalar(
            select(BotUser.user_id).where(BotUser.user_id == user_id)
        )
        return exists is not None


async def get_all_bot_user_ids() -> list[int]:
    async with async_session() as session:
        result = await session.execute(select(BotUser.user_id))
        return list(result.scalars().all())


async def get_all_bot_users() -> list:
    async with async_session() as session:
        stmt = (
            select(
                BotUser.user_id,
                BotUser.name,
                BotUser.is_admin,
                BotUser.invited_by,
                BotUser.created_at,
            )
            .order_by(BotUser.is_admin.desc(), BotUser.created_at.asc())
        )
        result = await session.execute(stmt)
        return list(result.all())


async def get_removable_bot_users() -> list:
    async with async_session() as session:
        stmt = (
            select(
                BotUser.user_id,
                BotUser.name,
                BotUser.is_admin,
            )
            .where(BotUser.is_admin.is_(False))
            .order_by(BotUser.created_at.asc())
        )
        result = await session.execute(stmt)
        return list(result.all())


async def get_admin_my_users() -> list:
    async with async_session() as session:
        inviter_cond = (
            or_(BotUser.invited_by.in_(ADMIN_IDS), BotUser.invited_by.is_(None))
            if ADMIN_IDS
            else BotUser.invited_by.is_(None)
        )
        stmt = (
            select(
                BotUser.user_id,
                BotUser.name,
                BotUser.created_at,
            )
            .where(BotUser.is_admin.is_(False), inviter_cond)
            .order_by(BotUser.created_at.asc())
        )
        result = await session.execute(stmt)
        return list(result.all())


async def get_admin_other_users() -> list:
    async with async_session() as session:
        conditions = [BotUser.is_admin.is_(False), BotUser.invited_by.is_not(None)]
        if ADMIN_IDS:
            conditions.append(BotUser.invited_by.not_in(ADMIN_IDS))
        stmt = (
            select(
                BotUser.user_id,
                BotUser.name,
                BotUser.invited_by,
                BotUser.created_at,
            )
            .where(*conditions)
            .order_by(BotUser.created_at.asc())
        )
        result = await session.execute(stmt)
        return list(result.all())


async def get_bot_user_names_map(user_ids: set[int]) -> dict[int, str]:
    if not user_ids:
        return {}
    async with async_session() as session:
        stmt = select(BotUser.user_id, BotUser.name).where(BotUser.user_id.in_(user_ids))
        result = await session.execute(stmt)
        return {row.user_id: row.name for row in result.all()}


async def get_bot_user(user_id: int) -> BotUser | None:
    async with async_session() as session:
        return await session.get(BotUser, user_id)


async def add_bot_user(user_id: int, name: str, invited_by: int | None = None) -> bool:
    async with async_session() as session:
        existing = await session.get(BotUser, user_id)
        if existing:
            return False
        session.add(
            BotUser(
                user_id=user_id,
                name=name.strip(),
                is_admin=(user_id in ADMIN_IDS),
                invited_by=invited_by,
                has_invited=False,
            )
        )
        if invited_by:
            inviter = await session.get(BotUser, invited_by)
            if inviter:
                inviter.has_invited = True
        try:
            await session.commit()
            return True
        except IntegrityError:
            await session.rollback()
            return False


async def user_has_invited_anyone(user_id: int) -> bool:
    async with async_session() as session:
        has_flag = await session.scalar(
            select(BotUser.has_invited).where(BotUser.user_id == user_id)
        )
        if has_flag:
            return True
        count = await session.scalar(
            select(func.count()).select_from(BotUser).where(BotUser.invited_by == user_id)
        )
        return bool(count and count > 0)


async def get_users_with_user_section() -> list[int]:
    async with async_session() as session:
        stmt = select(BotUser.user_id).where(
            BotUser.is_admin.is_(False),
            BotUser.has_invited.is_(True),
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())


async def get_invited_users(inviter_id: int) -> list:
    async with async_session() as session:
        stmt = (
            select(BotUser.user_id, BotUser.name)
            .where(BotUser.invited_by == inviter_id, BotUser.is_admin.is_(False))
            .order_by(BotUser.created_at.asc())
        )
        result = await session.execute(stmt)
        return list(result.all())


async def get_invited_bot_user(inviter_id: int, target_user_id: int) -> BotUser | None:
    async with async_session() as session:
        stmt = select(BotUser).where(
            BotUser.user_id == target_user_id,
            BotUser.invited_by == inviter_id,
            BotUser.is_admin.is_(False),
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()


async def update_bot_user_name(user_id: int, new_name: str) -> BotUser | None:
    async with async_session() as session:
        user = await session.get(BotUser, user_id)
        if not user:
            return None
        user.name = new_name.strip()
        await session.commit()
        await session.refresh(user)
        return user


async def update_invited_bot_user_name(
    inviter_id: int, target_user_id: int, new_name: str
) -> BotUser | None:
    async with async_session() as session:
        stmt = select(BotUser).where(
            BotUser.user_id == target_user_id,
            BotUser.invited_by == inviter_id,
            BotUser.is_admin.is_(False),
        )
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()
        if not user:
            return None
        user.name = new_name.strip()
        await session.commit()
        await session.refresh(user)
        return user


async def remove_bot_user_with_cleanup(
    user_id: int, inviter_id: int | None = None
) -> tuple[bool, list[int]]:
    """Одной транзакцией удаляет пользователя и все его служебные записи.

    Приглашённые им пользователи и их поле invited_by сохраняются для истории администратора.
    """
    if user_id in ADMIN_IDS:
        return False, []
    async with async_session() as session:
        conds = [BotUser.user_id == user_id, BotUser.is_admin.is_(False)]
        if inviter_id is not None:
            conds.append(BotUser.invited_by == inviter_id)
        res = await session.execute(select(BotUser).where(*conds))
        existing = res.scalar_one_or_none()
        if not existing:
            return False, []

        msg_ids: list[int] = []
        tracked_res = await session.execute(
            select(TrackedMessage.message_id).where(TrackedMessage.user_id == user_id)
        )
        msg_ids.extend(tracked_res.scalars().all())

        notif_res = await session.execute(
            select(PendingNotification.message_id).where(
                PendingNotification.user_id == user_id,
                PendingNotification.message_id > 0,
            )
        )
        msg_ids.extend(notif_res.scalars().all())

        panel = await session.get(UserPanel, user_id)
        if panel:
            msg_ids.append(panel.panel_message_id)
            await session.delete(panel)

        await session.delete(existing)
        await session.execute(delete(Reminder).where(Reminder.user_id == user_id))
        await session.execute(
            delete(PendingNotification).where(PendingNotification.user_id == user_id)
        )
        await session.execute(
            delete(TrackedMessage).where(TrackedMessage.user_id == user_id)
        )
        await session.execute(
            delete(UserSettings).where(UserSettings.user_id == user_id)
        )
        await session.execute(
            delete(DeletedReminderUndo).where(DeletedReminderUndo.user_id == user_id)
        )
        await session.commit()
        unique_msg_ids = sorted({int(m) for m in msg_ids if m and int(m) > 0})
        return True, unique_msg_ids


async def remove_bot_user(user_id: int) -> bool:
    removed, _ = await remove_bot_user_with_cleanup(user_id)
    return removed


async def remove_invited_bot_user(inviter_id: int, target_user_id: int) -> bool:
    removed, _ = await remove_bot_user_with_cleanup(target_user_id, inviter_id=inviter_id)
    return removed


# --- Настройки времени и табло ---

async def get_user_offset_minutes(user_id: int) -> int:
    async with async_session() as session:
        offset = await session.scalar(
            select(UserSettings.tz_offset_minutes).where(UserSettings.user_id == user_id)
        )
        if offset is not None:
            return offset
        return DEFAULT_TZ_OFFSET_HOURS * 60


async def set_user_offset_minutes(user_id: int, offset_minutes: int) -> None:
    async with async_session() as session:
        settings = await session.get(UserSettings, user_id)
        if settings:
            settings.tz_offset_minutes = offset_minutes
        else:
            session.add(UserSettings(user_id=user_id, tz_offset_minutes=offset_minutes))
        await session.commit()


def format_tz_label(offset_minutes: int) -> str:
    if offset_minutes in TZ_ABBR_MAP:
        return TZ_ABBR_MAP[offset_minutes]
    sign = "+" if offset_minutes >= 0 else "-"
    total = abs(offset_minutes)
    hours, mins = divmod(total, 60)
    if mins:
        return f"UTC{sign}{hours}:{mins:02d}"
    return f"UTC{sign}{hours}"


def format_tz_cet(offset_minutes: int) -> str:
    return format_tz_label(offset_minutes)


async def get_user_now(user_id: int) -> tuple[datetime, int]:
    offset_mins = await get_user_offset_minutes(user_id)
    user_tz = timezone(timedelta(minutes=offset_mins))
    return datetime.now(user_tz), offset_mins


async def get_panel_message_id(user_id: int) -> int | None:
    async with async_session() as session:
        return await session.scalar(
            select(UserPanel.panel_message_id).where(UserPanel.user_id == user_id)
        )


async def set_panel_message_id(user_id: int, message_id: int) -> None:
    async with async_session() as session:
        panel = await session.get(UserPanel, user_id)
        if panel:
            panel.panel_message_id = message_id
        else:
            session.add(UserPanel(user_id=user_id, panel_message_id=message_id))
        await session.commit()


async def add_tracked_message(user_id: int, message_id: int) -> None:
    if not message_id or int(message_id) <= 0:
        return
    async with async_session() as session:
        session.add(TrackedMessage(user_id=user_id, message_id=int(message_id)))
        await session.commit()


async def add_tracked_messages_batch(user_id: int, message_ids: list[int]) -> None:
    unique_ids = sorted({int(mid) for mid in message_ids if mid and int(mid) > 0})
    if not unique_ids:
        return
    async with async_session() as session:
        for mid in unique_ids:
            session.add(TrackedMessage(user_id=user_id, message_id=mid))
        await session.commit()


async def remove_tracked_message(user_id: int, message_id: int) -> None:
    async with async_session() as session:
        await session.execute(
            delete(TrackedMessage).where(
                TrackedMessage.user_id == user_id,
                TrackedMessage.message_id == message_id,
            )
        )
        await session.commit()


async def has_tracked_messages(user_id: int) -> bool:
    async with async_session() as session:
        exists = await session.scalar(
            select(TrackedMessage.id).where(TrackedMessage.user_id == user_id).limit(1)
        )
        return exists is not None


async def pop_tracked_messages(user_id: int) -> list[int]:
    clear_rendered_reminders_state(user_id)
    async with async_session() as session:
        result = await session.execute(
            select(TrackedMessage.message_id).where(TrackedMessage.user_id == user_id)
        )
        msg_ids = list(result.scalars().all())
        if msg_ids:
            await session.execute(
                delete(TrackedMessage).where(TrackedMessage.user_id == user_id)
            )

        notif_res = await session.execute(
            select(PendingNotification.message_id).where(
                PendingNotification.user_id == user_id,
                PendingNotification.message_id > 0,
            )
        )
        notif_msg_ids = list(notif_res.scalars().all())
        if notif_msg_ids:
            msg_ids.extend(notif_msg_ids)
            await session.execute(
                update(PendingNotification)
                .where(
                    PendingNotification.user_id == user_id,
                    PendingNotification.message_id > 0,
                )
                .values(message_id=0)
            )

        if msg_ids:
            await session.commit()
        return msg_ids


async def pop_all_window_messages(user_id: int) -> list[int]:
    clear_rendered_reminders_state(user_id)
    async with async_session() as session:
        result = await session.execute(
            select(TrackedMessage.message_id).where(TrackedMessage.user_id == user_id)
        )
        msg_ids = list(result.scalars().all())
        if msg_ids:
            await session.execute(
                delete(TrackedMessage).where(TrackedMessage.user_id == user_id)
            )

        notif_res = await session.execute(
            select(PendingNotification.message_id).where(
                PendingNotification.user_id == user_id,
                PendingNotification.message_id > 0,
            )
        )
        notif_msg_ids = list(notif_res.scalars().all())
        if notif_msg_ids:
            msg_ids.extend(notif_msg_ids)
            await session.execute(
                update(PendingNotification)
                .where(
                    PendingNotification.user_id == user_id,
                    PendingNotification.message_id > 0,
                )
                .values(message_id=0)
            )

        panel = await session.get(UserPanel, user_id)
        if panel:
            msg_ids.append(panel.panel_message_id)
            await session.delete(panel)

        await session.commit()
        return msg_ids


# --- CRUD для напоминаний ---

async def create_reminder(
    user_id: int,
    text: str,
    remind_at_utc: datetime,
    recurrence: str = "once",
) -> Reminder:
    remind_at_naive = remind_at_utc.replace(tzinfo=None)
    async with async_session() as session:
        reminder = Reminder(
            user_id=user_id,
            text=text,
            remind_at=remind_at_naive,
            recurrence=recurrence,
            is_sent=False,
            processing_until=None,
        )
        session.add(reminder)
        await session.commit()
        await session.refresh(reminder)
        return reminder


async def get_active_reminders(user_id: int) -> list:
    async with async_session() as session:
        stmt = (
            select(
                Reminder.id,
                Reminder.remind_at,
                Reminder.recurrence,
                Reminder.text,
            )
            .where(Reminder.user_id == user_id, Reminder.is_sent.is_(False))
            .order_by(Reminder.remind_at.asc())
        )
        result = await session.execute(stmt)
        return list(result.all())


async def get_reminder_by_id(user_id: int, reminder_id: int) -> Reminder | None:
    async with async_session() as session:
        stmt = select(Reminder).where(
            Reminder.id == reminder_id,
            Reminder.user_id == user_id,
            Reminder.is_sent.is_(False),
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()


async def get_reminder_any_by_id(user_id: int, reminder_id: int) -> Reminder | None:
    async with async_session() as session:
        stmt = select(Reminder).where(
            Reminder.id == reminder_id,
            Reminder.user_id == user_id,
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()


async def snooze_or_clone_reminder(
    user_id: int, reminder_id: int, new_remind_at_utc: datetime
) -> Reminder | None:
    remind_at_naive = new_remind_at_utc.replace(tzinfo=None)
    async with async_session() as session:
        stmt = select(Reminder).where(
            Reminder.id == reminder_id,
            Reminder.user_id == user_id,
        )
        result = await session.execute(stmt)
        reminder = result.scalar_one_or_none()
        if not reminder:
            return None

        if reminder.is_sent:
            reminder.remind_at = remind_at_naive
            reminder.is_sent = False
            reminder.processing_until = None
            await session.commit()
            await session.refresh(reminder)
            return reminder
        else:
            snoozed = Reminder(
                user_id=user_id,
                text=reminder.text,
                remind_at=remind_at_naive,
                recurrence="once",
                is_sent=False,
            )
            session.add(snoozed)
            await session.commit()
            await session.refresh(snoozed)
            return snoozed


async def update_reminder_fields(
    user_id: int,
    reminder_id: int,
    *,
    remind_at_utc: datetime | None = None,
    text_val: str | None = None,
    recurrence: str | None = None,
) -> Reminder | None:
    """Атомарно обновляет переданные поля активного напоминания одной транзакцией."""
    values: dict = {}
    if remind_at_utc is not None:
        values["remind_at"] = remind_at_utc.replace(tzinfo=None)
        values["processing_until"] = None
    if text_val is not None:
        values["text"] = text_val
    if recurrence is not None:
        values["recurrence"] = recurrence
    if not values:
        return await get_reminder_by_id(user_id, reminder_id)

    async with async_session() as session:
        res = await session.execute(
            update(Reminder)
            .where(
                Reminder.id == reminder_id,
                Reminder.user_id == user_id,
                Reminder.is_sent.is_(False),
            )
            .values(**values)
        )
        if (res.rowcount or 0) == 0:
            await session.rollback()
            return None
        await session.commit()
        return await session.get(Reminder, reminder_id)


async def update_reminder_text(user_id: int, reminder_id: int, new_text: str) -> Reminder | None:
    return await update_reminder_fields(user_id, reminder_id, text_val=new_text)


async def update_reminder_datetime(
    user_id: int, reminder_id: int, new_remind_at_utc: datetime
) -> Reminder | None:
    return await update_reminder_fields(user_id, reminder_id, remind_at_utc=new_remind_at_utc)


async def update_reminder_recurrence(
    user_id: int, reminder_id: int, recurrence: str
) -> Reminder | None:
    return await update_reminder_fields(user_id, reminder_id, recurrence=recurrence)


async def delete_reminder_by_id(user_id: int, reminder_id: int) -> bool:
    async with async_session() as session:
        stmt = delete(Reminder).where(
            Reminder.id == reminder_id,
            Reminder.user_id == user_id,
        )
        result = await session.execute(stmt)
        await session.commit()
        return (result.rowcount or 0) > 0


async def get_due_reminders(now_utc_naive: datetime, limit: int = 100) -> list:
    async with async_session() as session:
        stmt = (
            select(
                Reminder.id,
                Reminder.user_id,
                Reminder.text,
                Reminder.recurrence,
                Reminder.remind_at,
            )
            .where(
                Reminder.is_sent.is_(False),
                Reminder.remind_at <= now_utc_naive,
                or_(
                    Reminder.processing_until.is_(None),
                    Reminder.processing_until <= now_utc_naive,
                ),
            )
            .order_by(Reminder.remind_at.asc())
            .limit(limit)
        )
        result = await session.execute(stmt)
        return list(result.all())


async def claim_due_reminder(
    reminder_id: int,
    expected_remind_at: datetime,
    now_utc: datetime,
    lease_seconds: int = 60,
) -> bool:
    lease_until = now_utc + timedelta(seconds=lease_seconds)
    async with async_session() as session:
        stmt = (
            update(Reminder)
            .where(
                Reminder.id == reminder_id,
                Reminder.is_sent.is_(False),
                Reminder.remind_at == expected_remind_at,
                or_(
                    Reminder.processing_until.is_(None),
                    Reminder.processing_until <= now_utc,
                ),
            )
            .values(processing_until=lease_until)
        )
        res = await session.execute(stmt)
        await session.commit()
        return (res.rowcount or 0) == 1


async def release_reminder_claim(reminder_id: int) -> None:
    async with async_session() as session:
        await session.execute(
            update(Reminder)
            .where(Reminder.id == reminder_id)
            .values(processing_until=None)
        )
        await session.commit()


async def finalize_triggered_delivery(
    notif_id: int | None,
    message_id: int | None,
    reminder_id: int,
    offset_mins: int,
    expected_remind_at: datetime | None = None,
) -> bool:
    """Атомарно фиксирует message_id уведомления и продвигает/закрывает Reminder в одной транзакции."""
    async with async_session() as session:
        if notif_id and message_id:
            await session.execute(
                update(PendingNotification)
                .where(PendingNotification.id == notif_id)
                .values(message_id=message_id)
            )

        reminder = await session.get(Reminder, reminder_id)
        if not reminder or reminder.is_sent:
            await session.commit()
            return False

        if expected_remind_at is not None and reminder.remind_at != expected_remind_at:
            await session.commit()
            return False

        if reminder.recurrence == "once" or reminder.recurrence not in RECURRENCE_LABELS:
            new_is_sent = True
            new_remind_at = reminder.remind_at
        else:
            now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
            now_local = now_utc + timedelta(minutes=offset_mins)
            current_local = reminder.remind_at + timedelta(minutes=offset_mins)
            next_local = compute_next_recurring_local_dt(
                current_local, reminder.recurrence, now_local
            )
            new_remind_at = next_local - timedelta(minutes=offset_mins)
            new_is_sent = False

        conditions = [
            Reminder.id == reminder_id,
            Reminder.is_sent.is_(False),
        ]
        if expected_remind_at is not None:
            conditions.append(Reminder.remind_at == expected_remind_at)

        stmt = (
            update(Reminder)
            .where(*conditions)
            .values(
                remind_at=new_remind_at,
                is_sent=new_is_sent,
                processing_until=None,
            )
        )
        result = await session.execute(stmt)
        await session.commit()
        return (result.rowcount or 0) > 0


async def process_triggered_reminder(
    reminder_id: int,
    offset_mins: int,
    expected_remind_at: datetime | None = None,
) -> bool:
    return await finalize_triggered_delivery(
        notif_id=None,
        message_id=None,
        reminder_id=reminder_id,
        offset_mins=offset_mins,
        expected_remind_at=expected_remind_at,
    )
