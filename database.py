import calendar
from datetime import datetime, date, timezone, timedelta
from sqlalchemy import BigInteger, Boolean, DateTime, Integer, String, select, delete, func
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from config import DATABASE_URL, DEFAULT_TZ_OFFSET_HOURS, ADMIN_IDS, USER_IDS

engine = create_async_engine(DATABASE_URL, echo=False)
async_session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

RECURRENCE_LABELS: dict[str, str] = {
    "once": "Один раз",
    "daily": "Каждый день",
    "weekly": "Раз в неделю",
    "monthly": "Раз в месяц",
    "yearly": "Раз в год",
}

TZ_ABBR_MAP: dict[int, str] = {
    0: "UTC",
    60: "CET",
    120: "Клд",
    180: "Мск",
    240: "Смр",
    300: "Мгн",
    360: "Омск",
    420: "Крс",
    480: "Ирк",
    540: "Якт",
    600: "Влд",
    660: "Мгд",
    720: "Кмч",
}


def format_recurrence_label(recurrence: str) -> str:
    return RECURRENCE_LABELS.get(recurrence, "Один раз")


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


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

        res_rem = await conn.exec_driver_sql("PRAGMA table_info(reminders)")
        rem_cols = [row[1] for row in res_rem.fetchall()]
        if "recurrence" not in rem_cols:
            await conn.exec_driver_sql(
                "ALTER TABLE reminders ADD COLUMN recurrence VARCHAR(32) NOT NULL DEFAULT 'once'"
            )

        res_users = await conn.exec_driver_sql("PRAGMA table_info(bot_users)")
        user_cols = [row[1] for row in res_users.fetchall()]
        if "name" not in user_cols:
            await conn.exec_driver_sql(
                "ALTER TABLE bot_users ADD COLUMN name VARCHAR(255) NOT NULL DEFAULT ''"
            )
        if "invited_by" not in user_cols:
            await conn.exec_driver_sql(
                "ALTER TABLE bot_users ADD COLUMN invited_by BIGINT DEFAULT NULL"
            )
        if "has_invited" not in user_cols:
            await conn.exec_driver_sql(
                "ALTER TABLE bot_users ADD COLUMN has_invited BOOLEAN NOT NULL DEFAULT 0"
            )

    async with async_session() as session:
        count = await session.scalar(select(func.count()).select_from(BotUser))
        if not count:
            for uid in USER_IDS:
                if uid not in ADMIN_IDS:
                    session.add(BotUser(user_id=uid, name="Пользователь", is_admin=False))

        for admin_id in ADMIN_IDS:
            existing = await session.get(BotUser, admin_id)
            if existing:
                existing.is_admin = True
                if not existing.name:
                    existing.name = "Администратор"
            else:
                session.add(BotUser(user_id=admin_id, name="Администратор", is_admin=True))

        await session.commit()


# --- Управление доступом и пользователями (/users и /user) ---

def is_admin_id(user_id: int) -> bool:
    return user_id in ADMIN_IDS


async def is_user_allowed(user_id: int) -> bool:
    if user_id in ADMIN_IDS:
        return True
    async with async_session() as session:
        user = await session.get(BotUser, user_id)
        return user is not None


async def get_all_bot_users() -> list[BotUser]:
    async with async_session() as session:
        stmt = select(BotUser).order_by(BotUser.is_admin.desc(), BotUser.created_at.asc())
        result = await session.execute(stmt)
        return list(result.scalars().all())


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
        await session.commit()
        return True


async def user_has_invited_anyone(user_id: int) -> bool:
    """Проверяет, добавил ли пользователь хотя бы одного нового пользователя."""
    async with async_session() as session:
        user = await session.get(BotUser, user_id)
        if user and user.has_invited:
            return True
        count = await session.scalar(
            select(func.count()).select_from(BotUser).where(BotUser.invited_by == user_id)
        )
        return bool(count and count > 0)


async def get_users_with_user_section() -> list[int]:
    """Возвращает ID всех не-админов, которым доступен раздел /user."""
    async with async_session() as session:
        stmt = select(BotUser.user_id).where(
            BotUser.is_admin.is_(False),
            BotUser.has_invited.is_(True),
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())


async def get_invited_users(inviter_id: int) -> list[BotUser]:
    """Возвращает список пользователей, которых пригласил данный пользователь."""
    async with async_session() as session:
        stmt = (
            select(BotUser)
            .where(BotUser.invited_by == inviter_id, BotUser.is_admin.is_(False))
            .order_by(BotUser.created_at.asc())
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())


async def get_invited_bot_user(inviter_id: int, target_user_id: int) -> BotUser | None:
    """Возвращает пользователя только в том случае, если его создал inviter_id."""
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
    """Изменяет имя пользователя, только если он был создан inviter_id."""
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


async def remove_bot_user(user_id: int) -> bool:
    if user_id in ADMIN_IDS:
        return False
    async with async_session() as session:
        existing = await session.get(BotUser, user_id)
        if not existing or existing.is_admin:
            return False
        await session.delete(existing)
        await session.execute(delete(Reminder).where(Reminder.user_id == user_id))
        await session.commit()
        return True


async def remove_invited_bot_user(inviter_id: int, target_user_id: int) -> bool:
    """Удаляет пользователя, только если он был создан inviter_id."""
    if target_user_id in ADMIN_IDS:
        return False
    async with async_session() as session:
        stmt = select(BotUser).where(
            BotUser.user_id == target_user_id,
            BotUser.invited_by == inviter_id,
            BotUser.is_admin.is_(False),
        )
        result = await session.execute(stmt)
        existing = result.scalar_one_or_none()
        if not existing:
            return False
        await session.delete(existing)
        await session.execute(delete(Reminder).where(Reminder.user_id == target_user_id))
        await session.commit()
        return True


# --- Настройки локального времени устройства пользователя ---

async def get_user_offset_minutes(user_id: int) -> int:
    async with async_session() as session:
        settings = await session.get(UserSettings, user_id)
        if settings is not None:
            return settings.tz_offset_minutes
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


async def get_user_now(user_id: int) -> tuple[datetime, int]:
    offset_mins = await get_user_offset_minutes(user_id)
    user_tz = timezone(timedelta(minutes=offset_mins))
    return datetime.now(user_tz), offset_mins


# --- Работа с главным табло и пакетная очистка чата (/clear) ---

async def get_panel_message_id(user_id: int) -> int | None:
    async with async_session() as session:
        panel = await session.get(UserPanel, user_id)
        return panel.panel_message_id if panel else None


async def set_panel_message_id(user_id: int, message_id: int) -> None:
    async with async_session() as session:
        panel = await session.get(UserPanel, user_id)
        if panel:
            panel.panel_message_id = message_id
        else:
            session.add(UserPanel(user_id=user_id, panel_message_id=message_id))
        await session.commit()


async def add_tracked_message(user_id: int, message_id: int) -> None:
    async with async_session() as session:
        session.add(TrackedMessage(user_id=user_id, message_id=message_id))
        await session.commit()


async def add_tracked_messages_batch(user_id: int, message_ids: list[int]) -> None:
    if not message_ids:
        return
    async with async_session() as session:
        for mid in message_ids:
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


async def pop_tracked_messages(user_id: int) -> list[int]:
    async with async_session() as session:
        result = await session.execute(
            select(TrackedMessage.message_id).where(TrackedMessage.user_id == user_id)
        )
        msg_ids = list(result.scalars().all())
        if msg_ids:
            await session.execute(
                delete(TrackedMessage).where(TrackedMessage.user_id == user_id)
            )
            await session.commit()
        return msg_ids


async def pop_all_window_messages(user_id: int) -> list[int]:
    async with async_session() as session:
        result = await session.execute(
            select(TrackedMessage.message_id).where(TrackedMessage.user_id == user_id)
        )
        msg_ids = list(result.scalars().all())
        if msg_ids:
            await session.execute(
                delete(TrackedMessage).where(TrackedMessage.user_id == user_id)
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
        )
        session.add(reminder)
        await session.commit()
        await session.refresh(reminder)
        return reminder


async def get_active_reminders(user_id: int) -> list[Reminder]:
    async with async_session() as session:
        stmt = (
            select(Reminder)
            .where(Reminder.user_id == user_id, Reminder.is_sent.is_(False))
            .order_by(Reminder.remind_at.asc())
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())


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


async def update_reminder_text(user_id: int, reminder_id: int, new_text: str) -> Reminder | None:
    async with async_session() as session:
        stmt = select(Reminder).where(
            Reminder.id == reminder_id,
            Reminder.user_id == user_id,
            Reminder.is_sent.is_(False),
        )
        result = await session.execute(stmt)
        reminder = result.scalar_one_or_none()
        if reminder:
            reminder.text = new_text
            await session.commit()
            await session.refresh(reminder)
        return reminder


async def update_reminder_datetime(
    user_id: int, reminder_id: int, new_remind_at_utc: datetime
) -> Reminder | None:
    remind_at_naive = new_remind_at_utc.replace(tzinfo=None)
    async with async_session() as session:
        stmt = select(Reminder).where(
            Reminder.id == reminder_id,
            Reminder.user_id == user_id,
            Reminder.is_sent.is_(False),
        )
        result = await session.execute(stmt)
        reminder = result.scalar_one_or_none()
        if reminder:
            reminder.remind_at = remind_at_naive
            await session.commit()
            await session.refresh(reminder)
        return reminder


async def update_reminder_recurrence(
    user_id: int, reminder_id: int, recurrence: str
) -> Reminder | None:
    async with async_session() as session:
        stmt = select(Reminder).where(
            Reminder.id == reminder_id,
            Reminder.user_id == user_id,
            Reminder.is_sent.is_(False),
        )
        result = await session.execute(stmt)
        reminder = result.scalar_one_or_none()
        if reminder:
            reminder.recurrence = recurrence
            await session.commit()
            await session.refresh(reminder)
        return reminder


async def delete_reminder_by_id(user_id: int, reminder_id: int) -> bool:
    async with async_session() as session:
        stmt = delete(Reminder).where(
            Reminder.id == reminder_id,
            Reminder.user_id == user_id,
        )
        result = await session.execute(stmt)
        await session.commit()
        return (result.rowcount or 0) > 0


async def get_due_reminders(now_utc_naive: datetime) -> list[Reminder]:
    async with async_session() as session:
        stmt = (
            select(Reminder)
            .where(Reminder.is_sent.is_(False), Reminder.remind_at <= now_utc_naive)
            .order_by(Reminder.remind_at.asc())
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())


async def process_triggered_reminder(reminder_id: int, offset_mins: int) -> None:
    async with async_session() as session:
        reminder = await session.get(Reminder, reminder_id)
        if not reminder:
            return

        if reminder.recurrence == "once" or reminder.recurrence not in RECURRENCE_LABELS:
            reminder.is_sent = True
        else:
            now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
            now_local = now_utc + timedelta(minutes=offset_mins)
            current_local = reminder.remind_at + timedelta(minutes=offset_mins)
            next_local = compute_next_recurring_local_dt(
                current_local, reminder.recurrence, now_local
            )
            reminder.remind_at = next_local - timedelta(minutes=offset_mins)
            reminder.is_sent = False

        await session.commit()
