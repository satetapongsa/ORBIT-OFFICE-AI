"""Calendar and meeting schemas (ADR-070)."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, Field, StringConstraints

from app.models.meeting import MeetingResponse


def _https(value: str | None) -> str | None:
    if value in (None, ""):
        return None
    if not value.startswith("https://") or len(value) > 500 or " " in value:
        raise ValueError("ลิงก์ประชุมออนไลน์ต้องขึ้นต้นด้วย https://")
    return value


Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Location = Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)]
Description = Annotated[str, StringConstraints(strip_whitespace=True, max_length=5000)]
OnlineUrl = Annotated[str | None, AfterValidator(_https)]


class MeetingCreate(BaseModel):
    title: Title
    description: Description = ""
    location: Location | None = None
    online_url: OnlineUrl = None
    start_at: datetime
    end_at: datetime
    attendee_ids: list[uuid.UUID] = Field(default_factory=list, max_length=100)
    reminder_minutes: int = Field(default=15, ge=0, le=1440)


class MeetingUpdate(BaseModel):
    title: Title | None = None
    description: Description | None = None
    location: Location | None = None
    online_url: OnlineUrl = None
    start_at: datetime | None = None
    end_at: datetime | None = None
    attendee_ids: list[uuid.UUID] | None = Field(default=None, max_length=100)
    reminder_minutes: int | None = Field(default=None, ge=0, le=1440)


class MeetingRespond(BaseModel):
    response: Literal["ACCEPTED", "TENTATIVE", "DECLINED"]


class MeetingPerson(BaseModel):
    id: uuid.UUID
    display_name: str
    department_name: str | None


class AttendeeOut(MeetingPerson):
    response: MeetingResponse
    is_organizer: bool


class MeetingOut(BaseModel):
    id: uuid.UUID
    title: str
    description: str
    location: str | None
    online_url: str | None
    start_at: datetime
    end_at: datetime
    organizer: MeetingPerson | None
    attendees: list[AttendeeOut]
    my_response: MeetingResponse | None
    is_organizer: bool
    cancelled: bool
    reminder_minutes: int


class LeaveEvent(BaseModel):
    id: uuid.UUID
    person_name: str
    leave_type: str
    color: str
    start_date: date
    end_date: date
    half_day: str


class CalendarFeed(BaseModel):
    meetings: list[MeetingOut]
    leave: list[LeaveEvent]


class AvailabilityRequest(BaseModel):
    user_ids: list[uuid.UUID] = Field(max_length=100)
    start_at: datetime
    end_at: datetime
    exclude_meeting_id: uuid.UUID | None = None


class Conflict(BaseModel):
    user_id: uuid.UUID
    display_name: str
    kind: Literal["meeting", "leave"]
    detail: str


class AvailabilityOut(BaseModel):
    conflicts: list[Conflict]
