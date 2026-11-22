from typing import Literal
from pydantic import BaseModel, Field


RecurrenceCode = Literal["once", "daily", "weekly", "biweekly", "monthly", "yearly"]
SnoozeInterval = Literal["5m", "30m", "1h", "1d"]


class ReminderCreateRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=1000)
    date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    time: str = Field(..., pattern=r"^\d{2}:\d{2}$")
    recurrence: RecurrenceCode = "once"


class ReminderUpdateRequest(BaseModel):
    text: str | None = Field(default=None, min_length=1, max_length=1000)
    date: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    time: str | None = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    recurrence: RecurrenceCode | None = None


class SnoozeRequest(BaseModel):
    interval: SnoozeInterval


class UserCreateRequest(BaseModel):
    user_id: int = Field(..., gt=0)
    name: str = Field(..., min_length=1, max_length=100)


class UserUpdateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)


class TzUpdateRequest(BaseModel):
    offset_minutes: int | None = Field(default=None, ge=-720, le=840)
    device_time: str | None = Field(default=None, pattern=r"^\d{1,2}\D+\d{1,2}$")
