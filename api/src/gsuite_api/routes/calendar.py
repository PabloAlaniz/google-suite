"""Calendar API routes."""

from datetime import datetime

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from gsuite_api.dependencies import CalendarDep

router = APIRouter()


class EventResponse(BaseModel):
    id: str
    summary: str
    description: str | None
    location: str | None
    start: str | None
    end: str | None
    all_day: bool
    html_link: str | None


class CreateEventRequest(BaseModel):
    summary: str
    start: str  # ISO format
    end: str | None = None
    description: str | None = None
    location: str | None = None
    all_day: bool = False


@router.get("/events")
async def list_events(
    calendar: CalendarDep,
    days: int = Query(7, le=365),
    calendar_id: str | None = None,
    limit: int = Query(100, le=500),
):
    """Get upcoming events."""
    events = calendar.get_upcoming(days=days, calendar_id=calendar_id, max_results=limit)
    return {
        "events": [
            EventResponse(
                id=e.id,
                summary=e.summary,
                description=e.description,
                location=e.location,
                start=e.start.isoformat() if e.start else None,
                end=e.end.isoformat() if e.end else None,
                all_day=e.all_day,
                html_link=e.html_link,
            )
            for e in events
        ],
        "count": len(events),
    }


@router.get("/events/today")
async def list_today(calendar: CalendarDep, calendar_id: str | None = None):
    """Get today's events."""
    events = calendar.get_today(calendar_id=calendar_id)
    return {
        "events": [
            EventResponse(
                id=e.id,
                summary=e.summary,
                description=e.description,
                location=e.location,
                start=e.start.isoformat() if e.start else None,
                end=e.end.isoformat() if e.end else None,
                all_day=e.all_day,
                html_link=e.html_link,
            )
            for e in events
        ],
        "count": len(events),
    }


@router.get("/events/{event_id}")
async def get_event(event_id: str, calendar: CalendarDep, calendar_id: str | None = None):
    """Get a specific event."""
    event = calendar.get_event(event_id, calendar_id=calendar_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    return EventResponse(
        id=event.id,
        summary=event.summary,
        description=event.description,
        location=event.location,
        start=event.start.isoformat() if event.start else None,
        end=event.end.isoformat() if event.end else None,
        all_day=event.all_day,
        html_link=event.html_link,
    )


@router.post("/events")
async def create_event(request: CreateEventRequest, calendar: CalendarDep):
    """Create a new event."""
    start = datetime.fromisoformat(request.start)
    end = datetime.fromisoformat(request.end) if request.end else None

    event = calendar.create_event(
        summary=request.summary,
        start=start,
        end=end,
        description=request.description,
        location=request.location,
        all_day=request.all_day,
    )

    return {
        "id": event.id,
        "summary": event.summary,
        "status": "created",
    }


@router.delete("/events/{event_id}")
async def delete_event(event_id: str, calendar: CalendarDep, calendar_id: str | None = None):
    """Delete an event."""
    success = calendar.delete_event(event_id, calendar_id=calendar_id)
    return {"status": "deleted" if success else "failed"}


@router.get("/calendars")
async def list_calendars(calendar: CalendarDep):
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
