# gsuite-calendar

Simple, Pythonic Google Calendar API client.

## Installation

```bash
pip install gsuite-calendar
```

## Quick Start

```python
from gsuite_core import GoogleAuth
from gsuite_calendar import Calendar

# Authenticate
auth = GoogleAuth()
auth.authenticate()  # Opens browser for consent

calendar = Calendar(auth)
```

## Reading Events

```python
# Get today's events
for event in calendar.get_today():
    print(f"{event.start.strftime('%H:%M')} - {event.summary}")

# Get upcoming events (next 7 days)
for event in calendar.get_upcoming(days=7):
    print(f"{event.start}: {event.summary}")
    if event.location:
        print(f"  📍 {event.location}")
    if event.description:
        print(f"  📝 {event.description[:100]}...")

# Get events in a specific range
from datetime import datetime

events = calendar.get_events(
    time_min=datetime(2026, 2, 1),
    time_max=datetime(2026, 2, 28),
)
```

## Event Properties

```python
event = calendar.get_upcoming(days=1)[0]

# Basic info
event.id          # Event ID
event.summary     # Title
event.description # Description
event.location    # Location

# Times
event.start       # datetime
event.end         # datetime
event.is_all_day  # bool
event.timezone    # str

# Recurrence
event.is_recurring    # bool
event.recurrence      # Recurrence rule

# Attendees
for attendee in event.attendees:
    print(f"{attendee.email} - {attendee.response_status}")
    # response_status: needsAction, declined, tentative, accepted

# Links
event.html_link      # Link to Google Calendar
event.hangout_link   # Google Meet link (if any)

# Metadata
event.created        # datetime
event.updated        # datetime
event.creator_email  # Who created it
event.organizer_email # Who's organizing
```

## Creating Events

```python
from datetime import datetime, timedelta

# Simple event
calendar.create_event(
    summary="Team Meeting",
    start=datetime(2026, 2, 15, 10, 0),
    end=datetime(2026, 2, 15, 11, 0),
)

# With all options
calendar.create_event(
    summary="Project Review",
    description="Quarterly review of project progress",
    location="Conference Room A",
    start=datetime(2026, 2, 15, 14, 0),
    end=datetime(2026, 2, 15, 15, 30),
    attendees=["alice@company.com", "bob@company.com"],
    send_notifications=True,
)

# All-day event
calendar.create_event(
    summary="Company Holiday",
    start=datetime(2026, 2, 20),
    all_day=True,
)

# Quick add (natural language)
calendar.quick_add("Lunch with John tomorrow at 12pm")
```

## Updating Events

```python
# Get an event
events = calendar.get_upcoming(days=7)
event = events[0]

# Update it
calendar.update_event(
    event_id=event.id,
    summary="Updated Meeting Title",
    location="New Location",
)
```

## Deleting Events

```python
# Delete by event ID
calendar.delete_event(event_id="abc123xyz")

# Delete an event object
event = calendar.get_upcoming(days=1)[0]
calendar.delete_event(event_id=event.id)
```

## Working with Multiple Calendars

```python
# List all calendars
for cal in calendar.get_calendars():
    print(f"{cal.summary} ({cal.id})")
    print(f"  Primary: {cal.primary}")
    print(f"  Access: {cal.access_role}")

# Use a specific calendar
work_calendar = Calendar(auth, calendar_id="work@company.com")
events = work_calendar.get_upcoming(days=7)

# Or specify per-call
events = calendar.get_events(
    calendar_id="family@group.calendar.google.com",
    time_min=datetime(2026, 2, 1),
)
```

## Free/Busy Queries

```python
# Check availability across calendars
busy_times = calendar.get_free_busy(
    time_min=datetime(2026, 2, 15, 9, 0),
    time_max=datetime(2026, 2, 15, 18, 0),
    calendars=["me", "colleague@company.com"],
)

for cal_id, times in busy_times.items():
    print(f"{cal_id}:")
    for busy in times:
        print(f"  Busy: {busy['start']} - {busy['end']}")
```

## Recurring Events

```python
# Create recurring event
calendar.create_event(
    summary="Weekly Standup",
    start=datetime(2026, 2, 3, 9, 0),  # Monday
    end=datetime(2026, 2, 3, 9, 30),
    recurrence=["RRULE:FREQ=WEEKLY;BYDAY=MO,WE,FR"],
)

# Get recurring events (single_events=True expands them)
events = calendar.get_events(
    time_min=datetime(2026, 2, 1),
    time_max=datetime(2026, 2, 28),
    single_events=True,  # Returns each occurrence
)

# Get recurring events as single items
events = calendar.get_events(
    time_min=datetime(2026, 2, 1),
    time_max=datetime(2026, 2, 28),
    single_events=False,  # Returns master event only
)
```

## Error Handling

```python
from gsuite_core.exceptions import (
    GsuiteError,
    NotFoundError,
    RateLimitError,
)

try:
    calendar.delete_event("nonexistent_id")
except NotFoundError:
    print("Event not found")
except RateLimitError:
    print("Rate limited, retry later")
except GsuiteError as e:
    print(f"Calendar error: {e}")
```

## Configuration

Uses `gsuite-core` settings. See [gsuite-core README](../core/README.md) for auth configuration.

## License

MIT
