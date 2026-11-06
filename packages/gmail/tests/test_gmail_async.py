"""AsyncGmail against a fake Gmail REST API (httpx.MockTransport)."""

import base64
import json
import re
from email import message_from_bytes
from unittest.mock import patch

import httpx
import pytest

from gsuite_core import Settings
from gsuite_core.exceptions import ValidationError
from gsuite_gmail import AsyncGmail, Message

ME = "me@example.com"


class FakeCredentials:
    valid = True

    def apply(self, headers):
        headers["authorization"] = "Bearer t"


def raw_message(mid, subject="Hi", sender="ana@example.com", to=ME, **extra):
    headers = [
        {"name": "Subject", "value": subject},
        {"name": "From", "value": sender},
        {"name": "To", "value": to},
        {"name": "Message-ID", "value": f"<{mid}@mail>"},
    ]
    payload = {
        "mimeType": "text/plain",
        "headers": headers,
        "body": {"data": base64.urlsafe_b64encode(b"Body").decode()},
    }
    payload.update(extra.pop("payload", {}))
    return {"id": mid, "threadId": f"t-{mid}", "labelIds": ["INBOX"], "payload": payload, **extra}


class FakeGmailApi:
    """Routes requests to handlers; records each (method, path, params, json)."""

    def __init__(self):
        self.messages = {"m1": raw_message("m1"), "m2": raw_message("m2", subject="Second")}
        self.labels = [{"id": "Label_7", "name": "Work"}]
        self.calls = []
        self.sent = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path.removeprefix("/gmail/v1/users/me/")
        body = json.loads(request.content) if request.content else None
        self.calls.append((request.method, path, dict(request.url.params), body))
        for (method, pattern), route in self.routes().items():
            match = re.fullmatch(pattern, path)
            if request.method == method and match:
                status, payload = route(body, *match.groups())
                return httpx.Response(status, json=payload)
        return httpx.Response(404, json={"error": {"code": 404, "message": f"no route {path}"}})

    def routes(self):
        return {
            ("GET", "messages"): lambda _: (
                200,
                {"messages": [{"id": "m1"}, {"id": "gone"}, {"id": "m2"}]},
            ),
            ("GET", r"messages/([\w-]+)"): self._get_message,
            ("POST", r"messages/([\w-]+)/trash"): lambda _, mid: (200, {"id": mid}),
            ("GET", r"messages/(\w+)/attachments/(\w+)"): lambda _, mid, aid: (
                200,
                {"data": base64.urlsafe_b64encode(f"{mid}:{aid}".encode()).decode()},
            ),
            ("POST", "messages/send"): self._send,
            ("POST", "messages/batchModify"): lambda _: (204, None),
            ("POST", r"messages/(\w+)/modify"): lambda body, mid: (200, {"id": mid}),
            ("GET", "settings/filters"): lambda _: (200, {"filter": [{"id": "flt1"}]}),
            ("POST", "settings/filters"): lambda body: (200, {"id": "flt2", **body}),
            ("DELETE", r"settings/filters/(\w+)"): lambda _, fid: (
                (204, None) if fid == "flt1" else (404, {"error": {"code": 404}})
            ),
            ("GET", "profile"): lambda _: (200, {"emailAddress": ME}),
            ("GET", r"settings/sendAs/(.+)"): lambda _, email: (403, {"error": {"code": 403}}),
            ("GET", "labels"): lambda _: (200, {"labels": self.labels}),
            ("GET", r"labels/(\w+)"): lambda _, lid: (
                200,
                {**next(lb for lb in self.labels if lb["id"] == lid), "messagesTotal": 3},
            ),
            ("POST", "labels"): self._create_label,
            ("DELETE", r"labels/(\w+)"): lambda _, lid: (204, None),
            ("GET", "threads"): lambda _: (200, {"threads": [{"id": "t1"}]}),
            ("GET", r"threads/(\w+)"): lambda _, tid: (
                200,
                {"id": tid, "snippet": "s", "messages": [self.messages["m1"]]},
            ),
            ("POST", "drafts"): lambda body: (200, {"id": "d1", "message": {"id": "m1"}}),
            ("GET", "drafts"): lambda _: (200, {"drafts": [{"id": "d1"}]}),
            ("GET", r"drafts/(\w+)"): lambda _, did: (
                (200, {"id": did, "message": self.messages["m1"]})
                if did == "d1"
                else (404, {"error": {"code": 404}})
            ),
            ("POST", "drafts/send"): lambda body: (200, {"id": "m2"}),
            ("DELETE", r"drafts/(\w+)"): lambda _, did: (
                (204, None) if did == "d1" else (404, {"error": {"code": 404}})
            ),
        }

    def _get_message(self, _, mid):
        if mid not in self.messages:
            return 404, {"error": {"code": 404, "message": "not found"}}
        return 200, self.messages[mid]

    def _send(self, body):
        self.sent.append(body)
        return 200, {"id": "m2"}

    def _create_label(self, body):
        label = {"id": f"Label_{len(self.labels) + 7}", "name": body["name"]}
        self.labels.append(label)
        return 200, label

    def decoded(self, index=-1):
        return message_from_bytes(base64.urlsafe_b64decode(self.sent[index]["raw"]))

    def paths(self, method):
        return [path for m, path, _, _ in self.calls if m == method]


@pytest.fixture(autouse=True)
def settings():
    s = Settings(max_retries=0, _env_file=None)
    with patch("gsuite_core.config.get_settings", return_value=s):
        yield s


@pytest.fixture
def api():
    return FakeGmailApi()


@pytest.fixture
async def gmail(api):
    async with AsyncGmail(FakeCredentials(), transport=httpx.MockTransport(api.handler)) as g:
        yield g


class TestReading:
    async def test_messages_skip_one_deleted_while_listing(self, gmail):
        messages = await gmail.get_messages(query="is:unread", max_results=10)

        assert [m.subject for m in messages] == ["Hi", "Second"]

    async def test_query_and_page_size_reach_the_api(self, gmail, api):
        await gmail.search("from:ana", max_results=2)

        _, _, params, _ = next(c for c in api.calls if c[1] == "messages")
        assert params == {"q": "from:ana", "maxResults": "2"}

    async def test_get_message_none_when_missing(self, gmail):
        assert (await gmail.get_message("m1")).subject == "Hi"
        assert await gmail.get_message("nope") is None

    async def test_threads(self, gmail):
        (thread,) = await gmail.get_threads()

        assert thread.id == "t1"
        assert thread.messages[0].subject == "Hi"
        assert await gmail.get_thread("t1") is not None

    async def test_attachment_download(self, gmail):
        assert await gmail.download_attachment("m1", "a9") == b"m1:a9"


class TestAsyncOnlyMessages:
    async def test_fluent_methods_raise_instead_of_doing_nothing(self, gmail):
        message = await gmail.get_message("m1")

        with pytest.raises(TypeError, match="AsyncGmail"):
            message.trash()
        with pytest.raises(TypeError, match="modify_message"):
            message.star()

    async def test_inline_attachment_downloads_without_a_request(self, gmail, api):
        part = {
            "filename": "note.txt",
            "mimeType": "text/plain",
            "body": {"data": base64.urlsafe_b64encode(b"inline").decode(), "size": 6},
        }
        api.messages["m4"] = raw_message(
            "m4", payload={"mimeType": "multipart/mixed", "parts": [part]}
        )
        (attachment,) = (await gmail.get_message("m4")).attachments
        calls = len(api.calls)

        assert attachment.is_inline
        assert attachment.download() == b"inline"
        assert len(api.calls) == calls

    async def test_trash_is_awaited_on_the_client(self, gmail, api):
        await gmail.trash("m1")

        assert api.paths("POST") == ["messages/m1/trash"]


class TestLabels:
    async def test_system_labels_need_no_listing(self, gmail, api):
        assert await gmail.batch_modify(["m1", "m2"], remove_labels=["UNREAD"]) == 2

        assert api.paths("GET") == []
        (_, _, _, body) = api.calls[-1]
        assert body == {"ids": ["m1", "m2"], "removeLabelIds": ["UNREAD"]}

    async def test_names_resolve_from_one_listing(self, gmail, api):
        await gmail.batch_modify(["m1"], add_labels=["Work"])
        await gmail.batch_modify(["m2"], add_labels=["Work", "STARRED"])

        assert api.paths("GET").count("labels") == 1
        assert api.calls[-1][3]["addLabelIds"] == ["Label_7", "STARRED"]

    async def test_unknown_label_is_a_validation_error(self, gmail):
        with pytest.raises(ValidationError, match="Nope"):
            await gmail.batch_modify(["m1"], add_labels=["Nope"])

    async def test_ids_are_sent_in_chunks_of_1000(self, gmail, api):
        await gmail.batch_modify([f"m{i}" for i in range(2500)], add_labels=["INBOX"])

        sizes = [len(body["ids"]) for m, p, _, body in api.calls if p == "messages/batchModify"]
        assert sizes == [1000, 1000, 500]

    async def test_get_labels_includes_counts(self, gmail):
        (label,) = await gmail.get_labels()

        assert (label.name, label.messages_total) == ("Work", 3)

    async def test_create_invalidates_the_cache(self, gmail, api):
        await gmail.batch_modify(["m1"], add_labels=["Work"])
        await gmail.create_label("New")

        await gmail.batch_modify(["m1"], add_labels=["New"])

        assert api.paths("GET").count("labels") == 2

    async def test_delete_unknown_label_is_false(self, gmail, api):
        assert await gmail.delete_label("Nope") is False
        assert await gmail.delete_label("Work") is True
        assert api.paths("DELETE") == ["labels/Label_7"]


class TestModifyMessage:
    async def test_sends_only_real_changes_and_updates_the_message(self, gmail, api):
        message = await gmail.get_message("m1")  # labels: INBOX

        await gmail.modify_message(
            message, add_labels=["STARRED", "INBOX"], remove_labels=["UNREAD"]
        )

        assert api.calls[-1][1:] == ("messages/m1/modify", {}, {"addLabelIds": ["STARRED"]})
        assert message.labels == ["INBOX", "STARRED"]

    async def test_nothing_to_change_makes_no_request(self, gmail, api):
        message = await gmail.get_message("m1")
        calls = len(api.calls)

        await gmail.modify_message(message, remove_labels=["UNREAD"])

        assert len(api.calls) == calls

    async def test_unknown_names_are_skipped_like_add_label(self, gmail, api):
        message = await gmail.get_message("m1")

        await gmail.modify_message(message, add_labels=["Work", "Nope"])

        assert api.calls[-1][3] == {"addLabelIds": ["Label_7"]}


class TestFilters:
    async def test_list_create_delete(self, gmail, api):
        assert await gmail.list_filters() == [{"id": "flt1"}]

        created = await gmail.create_filter({"from": "a@x.com"}, {"addLabelIds": ["Work"]})

        assert created["action"] == {"addLabelIds": ["Label_7"]}
        assert await gmail.delete_filter("flt1") is True
        assert await gmail.delete_filter("zz") is False


class TestSending:
    async def test_send_builds_mime_and_returns_the_sent_message(self, gmail, api):
        sent = await gmail.send(["bob@example.com"], "Hello", "Body", cc=["c@example.com"])

        assert isinstance(sent, Message)
        assert sent.id == "m2"
        mime = api.decoded()
        assert (mime["To"], mime["Cc"], mime["Subject"]) == (
            "bob@example.com",
            "c@example.com",
            "Hello",
        )
        assert "threadId" not in api.sent[-1]

    async def test_reply_threads_and_answers_the_sender(self, gmail, api):
        original = await gmail.get_message("m1")

        await gmail.reply(original, "Thanks")

        mime = api.decoded()
        assert mime["To"] == "ana@example.com"
        assert mime["Subject"] == "Re: Hi"
        assert mime["In-Reply-To"] == "<m1@mail>"
        assert api.sent[-1]["threadId"] == "t-m1"

    async def test_signature_failure_still_sends(self, gmail, api):
        await gmail.send(["bob@example.com"], "Hello", "Body", signature=True)

        assert api.decoded().get_payload(decode=True).decode().strip() == "Body"

    async def test_forward_downloads_attachments(self, gmail, api):
        part = {
            "filename": "a.pdf",
            "mimeType": "application/pdf",
            "body": {"attachmentId": "a9", "size": 5},
        }
        api.messages["m3"] = raw_message(
            "m3", payload={"mimeType": "multipart/mixed", "parts": [part]}
        )
        message = await gmail.get_message("m3")

        await gmail.forward(message, ["bob@example.com"], body="FYI")

        mime = api.decoded()
        assert mime["Subject"] == "Fwd: Hi"
        (attachment,) = [p for p in mime.walk() if p.get_filename()]
        assert attachment.get_payload(decode=True) == b"m3:a9"


class TestDrafts:
    async def test_create_list_send_delete(self, gmail, api):
        draft = await gmail.create_draft(["bob@example.com"], "Draft", "Body")
        assert (draft.id, draft.message.id) == ("d1", "m1")
        assert api.calls[0][3]["message"]["raw"]

        assert [d.id for d in await gmail.list_drafts()] == ["d1"]
        assert (await gmail.send_draft("d1")).id == "m2"
        assert await gmail.delete_draft("d1") is True
        assert await gmail.delete_draft("zz") is False
        assert await gmail.get_draft("zz") is None
