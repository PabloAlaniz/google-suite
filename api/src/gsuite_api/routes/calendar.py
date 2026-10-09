"""Calendar API routes."""

from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, EmailStr, Field

from gsuite_api.dependencies import CalendarDep
from gsuite_calendar import Event

router = APIRouter()

SendUpdates = Literal["all", "externalOnly", "none"]


class EventResponse(BaseModel):
    id: str
    summary: str
    description: str | None
    location: str | None
    start: str | None
    end: str | None
    all_day: bool
    html_link: str | None
    meet_link: str | None
    attendees: list[str]
    recurring_event_id: str | None


class CreateEventRequest(BaseModel):
    summary: str
    start: datetime  # ISO 8601; invalid values get a 422
    end: datetime | None = None
    description: str | None = None
    location: str | None = None
    all_day: bool = False
    attendees: list[EmailStr] | None = None
    recurrence: list[str] | None = Field(None, description='e.g. ["RRULE:FREQ=WEEKLY;BYDAY=MO"]')
    meet: bool = Field(False, description="Attach a Google Meet link")
    send_updates: SendUpdates = Field("none", description="Email the attendees")


class UpdateEventRequest(BaseModel):
    summary: str | None = None
    start: datetime | None = None
    end: datetime | None = None
    description: str | None = None
    location: str | None = None
    all_day: bool = False
    attendees: list[EmailStr] | None = Field(None, description="Replaces the whole list")
    send_updates: SendUpdates = "none"


class QuickAddRequest(BaseModel):
    text: str = Field(..., min_length=1, examples=["Lunch with Ana tomorrow at 1pm"])


class FreeBusyRequest(BaseModel):
    time_min: datetime
    time_max: datetime
    calendars: list[str] | None = Field(None, description='Calendar IDs/emails; "me" = primary')


def _event(e: Event) -> EventResponse:
    return EventResponse(
        id=e.id,
        summary=e.summary,
        description=e.description,
        location=e.location,
        start=e.start.isoformat() if e.start else None,
        end=e.end.isoformat() if e.end else None,
        all_day=e.all_day,
        html_link=e.html_link,
        meet_link=e.meet_link,
        attendees=[a.email for a in e.attendees],
        recurring_event_id=e.recurring_event_id,
    )


@router.get("/events")
def list_events(
    calendar: CalendarDep,
    days: int = Query(7, le=365),
    calendar_id: str | None = None,
    limit: int = Query(100, le=500),
) -> dict[str, Any]:
    """Get upcoming events."""
    events = calendar.get_upcoming(days=days, calendar_id=calendar_id, max_results=limit)
    return {"events": [_event(e) for e in events], "count": len(events)}


@router.get("/events/today")
def list_today(calendar: CalendarDep, calendar_id: str | None = None) -> dict[str, Any]:
    """Get today's events (in GSUITE_DEFAULT_TIMEZONE)."""
    events = calendar.get_today(calendar_id=calendar_id)
    return {"events": [_event(e) for e in events], "count": len(events)}


@router.post("/events:quickAdd")
def quick_add(
    request: QuickAddRequest, calendar: CalendarDep, calendar_id: str | None = None
) -> EventResponse:
    """Create an event from natural language."""
    return _event(calendar.quick_add(request.text, calendar_id=calendar_id))


@router.get("/events/{event_id}")
def get_event(
    event_id: str, calendar: CalendarDep, calendar_id: str | None = None
) -> EventResponse:
    """Get a specific event."""
    event = calendar.get_event(event_id, calendar_id=calendar_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    return _event(event)


@router.get("/events/{event_id}/instances")
def list_instances(
    event_id: str,
    calendar: CalendarDep,
    time_min: datetime | None = None,
    time_max: datetime | None = None,
    calendar_id: str | None = None,
    limit: int = Query(100, ge=1, le=2500),
) -> dict[str, Any]:
    """Occurrences of a recurring event."""
    events = calendar.get_instances(
        event_id, time_min=time_min, time_max=time_max, max_results=limit, calendar_id=calendar_id
    )
    return {"events": [_event(e) for e in events], "count": len(events)}


@router.post("/events")
def create_event(
    request: CreateEventRequest, calendar: CalendarDep, calendar_id: str | None = None
) -> EventResponse:
    """Create a new event."""
    event = calendar.create_event(
        summary=request.summary,
        start=request.start,
        end=request.end,
        description=request.description,
        location=request.location,
        attendees=[str(a) for a in request.attendees] if request.attendees else None,
        calendar_id=calendar_id,
        all_day=request.all_day,
        recurrence=request.recurrence,
        meet=request.meet,
        send_updates=request.send_updates,
    )
    return _event(event)


@router.patch("/events/{event_id}")
def update_event(
    event_id: str,
    request: UpdateEventRequest,
    calendar: CalendarDep,
    calendar_id: str | None = None,
) -> EventResponse:
    """Change an event; only the fields you send are updated."""
    event = calendar.update_event(
        event_id,
        summary=request.summary,
        start=request.start,
        end=request.end,
        description=request.description,
        location=request.location,
        attendees=[str(a) for a in request.attendees] if request.attendees is not None else None,
        all_day=request.all_day,
        calendar_id=calendar_id,
        send_updates=request.send_updates,
    )
    return _event(event)


@router.delete("/events/{event_id}")
def delete_event(
    event_id: str,
    calendar: CalendarDep,
    calendar_id: str | None = None,
    send_updates: SendUpdates = "none",
) -> dict[str, Any]:
    """Delete an event."""
    # Used to answer 200 {"status": "failed"} for a missing event
    if not calendar.delete_event(event_id, calendar_id=calendar_id, send_updates=send_updates):
        raise HTTPException(status_code=404, detail="Event not found")
    return {"id": event_id, "status": "deleted"}


@router.post("/freebusy")
def free_busy(request: FreeBusyRequest, calendar: CalendarDep) -> dict[str, Any]:
    """Busy intervals per calendar."""
    busy = calendar.get_free_busy(request.time_min, request.time_max, request.calendars)
    return {
        "calendars": {
            cal: [
                {
                    "start": b["start"].isoformat() if b["start"] else None,
                    "end": b["end"].isoformat() if b["end"] else None,
                }
                for b in intervals
            ]
            for cal, intervals in busy.items()
        }
    }


@router.get("/calendars")
def list_calendars(calendar: CalendarDep) -> dict[str, Any]:
    """List all accessible calendars."""
    calendars = calendar.get_calendars()
    return {
        "calendars": [
            {
                "id": c.id,
                "summary": c.summary,
                "primary": c.primary,
                "access_role": c.access_role,
            }
            for c in calendars
        ],
        "count": len(calendars),
    }
