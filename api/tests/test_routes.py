"""Route behavior with mocked Google clients."""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from gsuite_calendar import Event
from gsuite_gmail import Label, Message, Thread
from gsuite_gmail.message import Attachment


def _message(**overrides) -> Message:
    fields = {
        "id": "m1",
        "thread_id": "t1",
        "subject": "Hi",
        "sender": "a@example.com",
        "recipient": "b@example.com",
        "date": datetime(2026, 1, 2, 3, 4),
        "labels": ["INBOX", "UNREAD"],
    }
    fields.update(overrides)
    return Message(**fields)


class TestGmail:
    def test_list_messages(self, client, services):
        services["gmail"].get_messages.return_value = [_message()]

        response = client.get("/gmail/messages", params={"query": "is:unread", "limit": 5})

        assert response.status_code == 200
        body = response.json()
        assert body["count"] == 1
        assert body["messages"][0]["id"] == "m1"
        assert body["messages"][0]["is_unread"] is True
        services["gmail"].get_messages.assert_called_once_with(
            query="is:unread", labels=None, max_results=5
        )

    def test_limit_is_bounded(self, client):
        assert client.get("/gmail/messages", params={"limit": 1000}).status_code == 422

    def test_get_missing_message(self, client, services):
        services["gmail"].get_message.return_value = None

        response = client.get("/gmail/messages/nope")

        assert response.status_code == 404
        assert response.json()["detail"] == "Message not found"

    def test_send(self, client, services):
        services["gmail"].send.return_value = _message(id="sent1")

        response = client.post(
            "/gmail/messages/send",
            json={"to": ["c@example.com"], "subject": "S", "body": "B"},
        )

        assert response.status_code == 200
        assert response.json() == {"id": "sent1", "thread_id": "t1", "status": "sent"}

    def test_send_rejects_invalid_email(self, client):
        response = client.post(
            "/gmail/messages/send", json={"to": ["not-an-email"], "subject": "S", "body": "B"}
        )
        assert response.status_code == 422

    def test_attachment_filename_is_encoded(self, client, services):
        attachment = MagicMock(spec=Attachment)
        attachment.id = "att1"
        attachment.mime_type = "application/pdf"
        attachment.filename = 'informe "final"\r\nX-Injected: 1 ñ.pdf'
        attachment.download.return_value = b"%PDF"
        services["gmail"].get_message.return_value = _message(attachments=[attachment])

        response = client.get("/gmail/messages/m1/attachments/att1")

        assert response.status_code == 200
        assert response.content == b"%PDF"
        disposition = response.headers["content-disposition"]
        assert "\r" not in disposition and "\n" not in disposition
        assert "x-injected" not in response.headers
        assert (
            "filename*=UTF-8''informe%20%22final%22%0D%0AX-Injected%3A%201%20%C3%B1.pdf"
            in disposition
        )


class TestCalendar:
    def test_list_events(self, client, services):
        services["calendar"].get_upcoming.return_value = [
            Event(id="e1", summary="Sync", start=datetime(2026, 1, 1, 10), all_day=False)
        ]

        response = client.get("/calendar/events", params={"days": 3})

        assert response.status_code == 200
        assert response.json()["events"][0]["start"] == "2026-01-01T10:00:00"

    def test_create_event_parses_dates(self, client, services):
        services["calendar"].create_event.return_value = Event(id="e2", summary="New")

        response = client.post(
            "/calendar/events", json={"summary": "New", "start": "2026-03-01T09:00:00"}
        )

        assert response.status_code == 200
        kwargs = services["calendar"].create_event.call_args.kwargs
        assert kwargs["start"] == datetime(2026, 3, 1, 9)
        assert kwargs["end"] is None


class TestSheets:
    def test_get_values(self, client, services):
        services["sheets"].get_values.return_value = [["a", "b"]]

        response = client.get("/sheets/sid/values/Sheet1!A1:B1")

        assert response.status_code == 200
        assert response.json()["values"] == [["a", "b"]]
        services["sheets"].get_values.assert_called_once_with("sid", "Sheet1!A1:B1")

    def test_update_values(self, client, services):
        services["sheets"].update_values.return_value = {"updatedCells": 2, "updatedRows": 1}

        response = client.put(
            "/sheets/sid/values/A1:B1", json={"range": "A1:B1", "values": [[1, 2]]}
        )

        assert response.status_code == 200
        assert response.json()["updated_cells"] == 2


class TestHealthAuth:
    def test_requires_key(self, anonymous):
        assert anonymous.get("/health/auth").status_code == 401

    def test_reports_state(self, client, google_auth):
        google_auth.is_authenticated.return_value = False
        google_auth.needs_refresh.return_value = True

        response = client.get("/health/auth")

        assert response.json() == {"authenticated": False, "needs_refresh": True}


class TestGmailActions:
    ACTIONS = [
        ("POST", "read", "mark_as_read"),
        ("POST", "unread", "mark_as_unread"),
        ("POST", "star", "star"),
        ("DELETE", "star", "unstar"),
        ("POST", "important", "mark_important"),
        ("DELETE", "important", "mark_not_important"),
        ("POST", "untrash", "untrash"),
        ("POST", "archive", "archive"),
        ("POST", "inbox", "move_to_inbox"),
    ]

    @pytest.mark.parametrize(("method", "action", "message_method"), ACTIONS)
    def test_action_calls_message_method(self, client, services, method, action, message_method):
        message = MagicMock()
        services["gmail"].get_message.return_value = message

        response = client.request(method, f"/gmail/messages/m1/{action}")

        assert response.status_code == 200
        getattr(message, message_method).assert_called_once_with()

    @pytest.mark.parametrize(("method", "action", "_"), ACTIONS)
    def test_action_on_missing_message(self, client, services, method, action, _):
        services["gmail"].get_message.return_value = None
        assert client.request(method, f"/gmail/messages/m1/{action}").status_code == 404

    def test_trash(self, client, services):
        message = MagicMock()
        services["gmail"].get_message.return_value = message

        assert client.delete("/gmail/messages/m1").status_code == 200
        message.trash.assert_called_once_with()

    def test_modify_labels(self, client, services):
        message = MagicMock()
        services["gmail"].get_message.return_value = message

        response = client.post(
            "/gmail/messages/m1/labels", json={"add_labels": ["A"], "remove_labels": ["B"]}
        )

        assert response.status_code == 200
        message.add_label.assert_called_once_with("A")
        message.remove_label.assert_called_once_with("B")

    def test_batch_read_reaches_batch_endpoint(self, client, services):
        messages = {"a": MagicMock(), "b": MagicMock()}
        services["gmail"].get_message.side_effect = messages.get

        response = client.post("/gmail/messages/batch/read", json={"message_ids": ["a", "b"]})

        assert response.status_code == 200
        assert response.json()["count"] == 2
        for message in messages.values():
            message.mark_as_read.assert_called_once_with()

    def test_batch_requires_ids(self, client):
        response = client.post("/gmail/messages/batch/labels", json={"message_ids": []})
        assert response.status_code == 400

    def test_batch_labels(self, client, services):
        message = MagicMock()
        services["gmail"].get_message.return_value = message

        response = client.post(
            "/gmail/messages/batch/labels",
            json={"message_ids": ["a"], "add_labels": ["X"], "remove_labels": ["Y"]},
        )

        assert response.status_code == 200
        message.add_label.assert_called_once_with("X")
        message.remove_label.assert_called_once_with("Y")

    def test_reply(self, client, services):
        message = MagicMock()
        message.reply.return_value = _message(id="r1")
        services["gmail"].get_message.return_value = message

        response = client.post("/gmail/messages/m1/reply", json={"body": "thanks"})

        assert response.json() == {"id": "r1", "thread_id": "t1", "status": "sent"}
        message.reply.assert_called_once_with(body="thanks", html=False, signature=False)


class TestGmailReads:
    @pytest.mark.parametrize(
        ("path", "method"),
        [
            ("unread", "get_unread"),
            ("starred", "get_starred"),
            ("important", "get_important"),
            ("sent", "get_sent"),
        ],
    )
    def test_shortcut_lists(self, client, services, path, method):
        getattr(services["gmail"], method).return_value = [_message()]

        response = client.get(f"/gmail/messages/{path}")

        assert response.json()["count"] == 1

    def test_get_message_detail(self, client, services):
        services["gmail"].get_message.return_value = _message(plain="body")

        response = client.get("/gmail/messages/m1")

        assert response.json()["body_plain"] == "body"

    def test_thread(self, client, services):
        services["gmail"].get_thread.return_value = Thread(
            id="t1", messages=[_message(), _message(id="m2", sender="c@example.com", labels=[])]
        )

        response = client.get("/gmail/threads/t1")

        body = response.json()
        assert body["message_count"] == 2
        assert body["has_unread"] is True
        assert set(body["participants"]) == {"a@example.com", "b@example.com", "c@example.com"}

    def test_missing_thread(self, client, services):
        services["gmail"].get_thread.return_value = None
        assert client.get("/gmail/threads/t1").status_code == 404

    def test_labels(self, client, services):
        services["gmail"].get_labels.return_value = [Label(id="L1", name="Work")]

        response = client.get("/gmail/labels")

        assert response.json()["labels"][0] == {
            "id": "L1",
            "name": "Work",
            "type": "user",
            "messages_total": 0,
            "messages_unread": 0,
            "threads_total": 0,
            "threads_unread": 0,
        }

    def test_profile(self, client, services):
        services["gmail"].get_profile.return_value = {"emailAddress": "me@example.com"}
        assert client.get("/gmail/profile").json() == {"emailAddress": "me@example.com"}


class TestCalendarMore:
    def test_today(self, client, services):
        services["calendar"].get_today.return_value = [Event(id="e1", summary="Lunch")]
        assert client.get("/calendar/events/today").json()["count"] == 1

    def test_get_event(self, client, services):
        services["calendar"].get_event.return_value = Event(id="e1", summary="Lunch")
        assert client.get("/calendar/events/e1").json()["id"] == "e1"

    def test_get_missing_event(self, client, services):
        services["calendar"].get_event.return_value = None
        assert client.get("/calendar/events/e1").status_code == 404

    def test_delete_event(self, client, services):
        services["calendar"].delete_event.return_value = True
        assert client.delete("/calendar/events/e1").status_code == 200

    def test_calendars(self, client, services):
        services["calendar"].get_calendars.return_value = []
        assert client.get("/calendar/calendars").status_code == 200


class TestSheetsMore:
    def test_metadata(self, client, services):
        worksheet = MagicMock(id=0, title="Sheet1", index=0, row_count=10, column_count=3)
        services["sheets"].open_by_key.return_value = MagicMock(
            id="sid",
            title="Budget",
            url="u",
            locale="en_US",
            time_zone="UTC",
            worksheets=[worksheet],
        )

        response = client.get("/sheets/sid")

        assert response.json()["worksheets"][0]["title"] == "Sheet1"

    def test_append(self, client, services):
        services["sheets"].append_values.return_value = {"updates": {"updatedRows": 1}}

        response = client.post("/sheets/sid/values/Sheet1:append", json={"values": [[1]]})

        assert response.json()["appended_rows"] == 1

    def test_batch_update(self, client, services):
        services["sheets"].batch_update.return_value = {"responses": []}

        response = client.post(
            "/sheets/sid/values:batchUpdate",
            json={"data": [{"range": "A1", "values": [[1]]}]},
        )

        assert response.json()["updated_ranges"] == 1
        services["sheets"].batch_update.assert_called_once_with(
            "sid", [{"range": "A1", "values": [[1]]}], "USER_ENTERED"
        )

    def test_clear(self, client, services):
        assert client.delete("/sheets/sid/values/A1:B2").json()["cleared"] is True

    def test_create(self, client, services):
        services["sheets"].create.return_value = MagicMock(id="new", title="T", url="u")
        assert client.post("/sheets/create", params={"title": "T"}).json()["id"] == "new"


class TestAdminLogs:
    def test_fetches_cloud_logging(self, client, monkeypatch):
        monkeypatch.setenv("ADMIN_API_KEY", "admin-secret")
        monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "proj")
        entry = MagicMock(payload={"message": "boom"}, severity="ERROR")
        entry.timestamp.isoformat.return_value = "2026-01-01T00:00:00+00:00"
        logging_client = MagicMock()
        logging_client.list_entries.return_value = [entry]

        with patch("google.cloud.logging.Client", return_value=logging_client):
            response = client.get(
                "/health/admin/logs",
                headers={"X-Admin-Key": "admin-secret"},
                params={"severity": "bogus"},
            )

        assert response.status_code == 200
        body = response.json()
        assert body["logs"] == [
            {"timestamp": "2026-01-01T00:00:00+00:00", "severity": "ERROR", "message": "boom"}
        ]
        # Unknown severities fall back to ERROR instead of reaching the filter
        assert "severity>=ERROR" in logging_client.list_entries.call_args.kwargs["filter_"]

    def test_project_not_configured(self, client, monkeypatch):
        monkeypatch.setenv("ADMIN_API_KEY", "admin-secret")
        monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)
        monkeypatch.delenv("GCP_PROJECT", raising=False)

        response = client.get("/health/admin/logs", headers={"X-Admin-Key": "admin-secret"})

        assert response.status_code == 503
