"""New Gmail (drafts, labels, filters, threads, forward) and Calendar routes."""

from datetime import UTC, datetime

import pytest

from gsuite_calendar import Event
from gsuite_gmail import Draft, Label, Message, Thread


def _message(**overrides) -> Message:
    fields = {
        "id": "m1",
        "thread_id": "t1",
        "subject": "Hi",
        "sender": "a@x.com",
        "recipient": "b@x.com",
    }
    fields.update(overrides)
    return Message(**fields)


@pytest.fixture
def gmail(services):
    return services["gmail"]


@pytest.fixture
def calendar(services):
    return services["calendar"]


class TestGmail:
    def test_forward(self, client, gmail):
        gmail.get_message.return_value = _message()
        gmail.forward.return_value = _message(id="f1", thread_id="t2")

        response = client.post(
            "/gmail/messages/m1/forward", json={"to": ["c@x.com"], "body": "FYI"}
        )

        assert response.json() == {"id": "f1", "thread_id": "t2", "status": "sent"}
        assert gmail.forward.call_args.args[1:] == (["c@x.com"], "FYI")

    def test_forward_needs_recipient(self, client):
        assert client.post("/gmail/messages/m1/forward", json={"to": []}).status_code == 422

    def test_threads(self, client, gmail):
        gmail.get_threads.return_value = [
            Thread(id="t1", messages=[_message(labels=["UNREAD"])], snippet="s")
        ]

        body = client.get("/gmail/threads", params={"query": "from:a"}).json()

        assert body["threads"][0] == {
            "id": "t1",
            "subject": "Hi",
            "snippet": "s",
            "message_count": 1,
            "has_unread": True,
        }

    def test_drafts_lifecycle(self, client, gmail):
        gmail.create_draft.return_value = Draft(id="d1", message=_message())
        gmail.list_drafts.return_value = [Draft(id="d1", message=_message())]
        gmail.send_draft.return_value = _message(id="sent")
        gmail.delete_draft.return_value = True

        assert (
            client.post(
                "/gmail/drafts", json={"to": ["c@x.com"], "subject": "s", "body": "b"}
            ).json()["id"]
            == "d1"
        )
        assert client.get("/gmail/drafts").json()["count"] == 1
        assert client.post("/gmail/drafts/d1/send").json()["id"] == "sent"
        assert client.delete("/gmail/drafts/d1").json()["deleted"] is True

    def test_missing_draft(self, client, gmail):
        gmail.get_draft.return_value = None
        gmail.delete_draft.return_value = False
        assert client.get("/gmail/drafts/x").status_code == 404
        assert client.delete("/gmail/drafts/x").status_code == 404

    def test_labels(self, client, gmail):
        gmail.create_label.return_value = Label(id="Label_1", name="Clients")
        gmail.rename_label.return_value = Label(id="Label_1", name="Customers")
        gmail.delete_label.return_value = False

        assert client.post("/gmail/labels", json={"name": "Clients"}).json()["id"] == "Label_1"
        assert (
            client.patch("/gmail/labels/Clients", json={"name": "Customers"}).json()["name"]
            == "Customers"
        )
        assert client.delete("/gmail/labels/Nope").status_code == 404

    def test_filters(self, client, gmail):
        gmail.list_filters.return_value = [{"id": "f1"}]
        gmail.create_filter.return_value = {"id": "f2"}
        gmail.delete_filter.return_value = True

        assert client.get("/gmail/filters").json()["count"] == 1
        body = {"criteria": {"from": "x@y.com"}, "action": {"addLabelIds": ["Alerts"]}}
        assert client.post("/gmail/filters", json=body).json() == {"id": "f2"}
        assert client.delete("/gmail/filters/f1").status_code == 200


class TestCalendar:
    def _event(self, **overrides):
        fields = {
            "id": "e1",
            "summary": "Sync",
            "start": datetime(2026, 3, 1, 10, tzinfo=UTC),
            "meet_link": "https://meet.google.com/x",
        }
        fields.update(overrides)
        return Event(**fields)

    def test_create_with_meet_and_attendees(self, client, calendar):
        calendar.create_event.return_value = self._event()

        response = client.post(
            "/calendar/events",
            json={
                "summary": "Sync",
                "start": "2026-03-01T10:00:00Z",
                "meet": True,
                "attendees": ["a@x.com"],
                "send_updates": "all",
            },
        )

        assert response.json()["meet_link"] == "https://meet.google.com/x"
        kwargs = calendar.create_event.call_args.kwargs
        assert (
            kwargs["meet"] is True
            and kwargs["attendees"] == ["a@x.com"]
            and kwargs["send_updates"] == "all"
        )

    def test_invalid_send_updates(self, client):
        body = {"summary": "x", "start": "2026-03-01T10:00:00Z", "send_updates": "everyone"}
        assert client.post("/calendar/events", json=body).status_code == 422

    def test_update(self, client, calendar):
        calendar.update_event.return_value = self._event(summary="Moved")

        response = client.patch("/calendar/events/e1", json={"summary": "Moved"})

        assert response.json()["summary"] == "Moved"
        assert calendar.update_event.call_args.kwargs["summary"] == "Moved"
        assert calendar.update_event.call_args.kwargs["attendees"] is None

    def test_quick_add(self, client, calendar):
        calendar.quick_add.return_value = self._event()
        assert (
            client.post("/calendar/events:quickAdd", json={"text": "Lunch tomorrow"}).status_code
            == 200
        )

    def test_instances(self, client, calendar):
        calendar.get_instances.return_value = [self._event(recurring_event_id="e1")] * 3
        body = client.get("/calendar/events/e1/instances").json()
        assert body["count"] == 3 and body["events"][0]["recurring_event_id"] == "e1"

    def test_delete_missing_is_404(self, client, calendar):
        # Used to answer 200 {"status": "failed"}
        calendar.delete_event.return_value = False
        assert client.delete("/calendar/events/e1").status_code == 404

    def test_free_busy(self, client, calendar):
        calendar.get_free_busy.return_value = {
            "me": [
                {
                    "start": datetime(2026, 3, 1, 13, tzinfo=UTC),
                    "end": datetime(2026, 3, 1, 14, tzinfo=UTC),
                }
            ]
        }

        body = client.post(
            "/calendar/freebusy",
            json={
                "time_min": "2026-03-01T09:00:00Z",
                "time_max": "2026-03-01T18:00:00Z",
                "calendars": ["me"],
            },
        ).json()

        assert body == {
            "calendars": {
                "me": [{"start": "2026-03-01T13:00:00+00:00", "end": "2026-03-01T14:00:00+00:00"}]
            }
        }
