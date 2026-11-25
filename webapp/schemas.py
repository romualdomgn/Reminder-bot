from typing import Literal
from pydantic import BaseModel, Field, field_validator


RecurrenceCode = Literal["once", "daily", "weekly", "biweekly", "monthly", "yearly"]
SnoozeInterval = Literal["5m", "30m", "1h", "1d"]
LangCode = Literal["ru", "en"]


class ReminderCreateRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=3500)
    date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    time: str = Field(..., pattern=r"^\d{2}:\d{2}$")
    recurrence: RecurrenceCode = "once"


class ReminderUpdateRequest(BaseModel):
    text: str | None = Field(default=None, min_length=1, max_length=3500)
    date: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    time: str | None = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    recurrence: RecurrenceCode | None = None


class SnoozeRequest(BaseModel):
    interval: SnoozeInterval


class UserCreateRequest(BaseModel):
    user_id: int = Field(..., gt=0)
    name: str = Field(..., min_length=1, max_length=100)

    @field_validator("name", mode="before")
    @classmethod
    def normalize_name(cls, value: object) -> object:
        if isinstance(value, str):
            value = value.strip()
            if not value:
                raise ValueError("Имя пользователя не может быть пустым")
        return value


class UserUpdateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)

    @field_validator("name", mode="before")
    @classmethod
    def normalize_name(cls, value: object) -> object:
        if isinstance(value, str):
            value = value.strip()
            if not value:
                raise ValueError("Имя пользователя не может быть пустым")
        return value


class TzUpdateRequest(BaseModel):
    offset_minutes: int | None = Field(default=None, ge=-720, le=840)
    device_time: str | None = Field(default=None, pattern=r"^\d{1,2}\D+\d{1,2}$")


class LangUpdateRequest(BaseModel):
    lang: LangCode
