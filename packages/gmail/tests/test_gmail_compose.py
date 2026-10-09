"""Composing, replying, forwarding and drafts."""

import base64
import email
from email import policy
from unittest.mock import MagicMock, Mock, patch

import pytest

from gsuite_gmail.client import Gmail
from gsuite_gmail.message import Attachment, Message

ME = "me@example.com"


def _raw_original(**headers):
    base = {
        "From": "Ana <ana@example.com>",
        "To": f"{ME}, Bo <bo@example.com>",
        "Subject": "Plan",
        "Message-ID": "<orig@mail.example.com>",
        "References": "<root@mail.example.com>",
    }
    base.update(headers)
    return {
        "id": "orig",
        "threadId": "t1",
        "payload": {"headers": [{"name": k, "value": v} for k, v in base.items()]},
    }


@pytest.fixture
def service():
    with patch("gsuite_gmail.client.build") as build:
        svc = MagicMock()
        svc.users().getProfile().execute.return_value = {"emailAddress": ME}
        svc.users().messages().send().execute.return_value = {"id": "sent"}
        svc.users().messages().get().execute.side_effect = lambda: _raw_original()
        build.return_value = svc
        yield svc


@pytest.fixture
def gmail(service):
    return Gmail(Mock())


def sent_email(service) -> email.message.EmailMessage:
    body = service.users().messages().send.call_args.kwargs["body"]
    return email.message_from_bytes(base64.urlsafe_b64decode(body["raw"]), policy=policy.default)


def sent_thread(service) -> str | None:
    return service.users().messages().send.call_args.kwargs["body"].get("threadId")


class TestSend:
    def test_attachments_are_sent(self, gmail, service, tmp_path):
        # Used to be accepted and silently dropped
        report = tmp_path / "report.pdf"
        report.write_bytes(b"%PDF-1.7")

        gmail.send(
            ["a@x.com"], "Report", "See attached", attachments=[report, ("notes.txt", b"hi")]
        )

        parts = list(sent_email(service).iter_attachments())
        assert [(p.get_filename(), p.get_content_type(), p.get_content()) for p in parts] == [
            ("report.pdf", "application/pdf", b"%PDF-1.7"),
            ("notes.txt", "text/plain", "hi"),
        ]

    def test_html_has_text_alternative(self, gmail, service):
        gmail.send(["a@x.com"], "Hi", "<p>Hola <b>ñandú</b></p><br>chau", html=True)

        msg = sent_email(service)
        assert msg.get_body(("plain",)).get_content().strip() == "Hola ñandú\n\nchau"
        assert "<b>ñandú</b>" in msg.get_body(("html",)).get_content()

    def test_non_ascii_subject_and_recipients(self, gmail, service):
        gmail.send(["José <jose@x.com>"], "Reunión mañana", "ok", cc=["c@x.com"], bcc=["b@x.com"])

        msg = sent_email(service)
        assert msg["Subject"] == "Reunión mañana"
        assert msg["Cc"] == "c@x.com" and msg["Bcc"] == "b@x.com"

    def test_reply_to_sets_threading_headers(self, gmail, service):
        # reply_to used to be ignored entirely
        gmail.send(["ana@example.com"], "Re: Plan", "ok", reply_to="orig")

        msg = sent_email(service)
        assert msg["In-Reply-To"] == "<orig@mail.example.com>"
        assert msg["References"] == "<root@mail.example.com> <orig@mail.example.com>"
        assert sent_thread(service) == "t1"

    def test_signature_appended(self, gmail, service):
        service.users().settings().sendAs().get().execute.return_value = {
            "signature": "<b>Pablo</b>"
        }
        gmail.send(["a@x.com"], "s", "body", signature=True)
        assert sent_email(service).get_content().strip() == "body\n\nPablo"


class TestReply:
    def _message(self, gmail, **headers):
        return gmail._parse_message(_raw_original(**headers), include_body=False)

    def test_reply_goes_to_sender_in_thread(self, gmail, service):
        gmail.reply(self._message(gmail), "Thanks")

        msg = sent_email(service)
        assert msg["To"] == "Ana <ana@example.com>"
        assert msg["Subject"] == "Re: Plan"
        assert msg["In-Reply-To"] == "<orig@mail.example.com>"
        assert sent_thread(service) == "t1"

    def test_reply_to_header_wins(self, gmail, service):
        gmail.reply(self._message(gmail, **{"Reply-To": "list@example.com"}), "ok")
        assert sent_email(service)["To"] == "list@example.com"

    def test_subject_prefix_not_doubled(self, gmail, service):
        gmail.reply(self._message(gmail, Subject="RE: Plan"), "ok")
        assert sent_email(service)["Subject"] == "RE: Plan"

    def test_reply_all_excludes_me_and_duplicates(self, gmail, service):
        message = self._message(gmail, Cc="ana@example.com, Cy <cy@example.com>")

        gmail.reply(message, "ok", reply_all=True)

        msg = sent_email(service)
        assert msg["To"] == "Ana <ana@example.com>"
        assert msg["Cc"] == "Bo <bo@example.com>, Cy <cy@example.com>"

    def test_reply_to_my_own_message_goes_to_recipients(self, gmail, service):
        message = self._message(gmail, From=f"Me <{ME}>", To="Bo <bo@example.com>")
        gmail.reply(message, "following up")
        assert sent_email(service)["To"] == "Bo <bo@example.com>"

    def test_message_reply_delegates(self, gmail, service):
        self._message(gmail).reply("ok", reply_all=True)
        assert sent_email(service)["Cc"] == "Bo <bo@example.com>"


def test_forward_quotes_and_reattaches(gmail, service):
    original = Message(
        id="orig",
        thread_id="t1",
        subject="Plan",
        sender="ana@example.com",
        recipient=ME,
        plain="the plan",
        attachments=[
            Attachment(
                id="a", filename="plan.pdf", mime_type="application/pdf", size=3, _data=b"PDF"
            )
        ],
    )

    gmail.forward(original, ["bo@example.com"], "FYI")

    msg = sent_email(service)
    assert msg["Subject"] == "Fwd: Plan"
    text = msg.get_body(("plain",)).get_content()
    assert text.startswith("FYI\n\n---------- Forwarded message ---------")
    assert "the plan" in text
    assert [p.get_filename() for p in msg.iter_attachments()] == ["plan.pdf"]
    assert sent_thread(service) is None  # a forward starts a new conversation


class TestDrafts:
    def test_create(self, gmail, service):
        service.users().drafts().create().execute.return_value = {
            "id": "d1",
            "message": {"id": "orig"},
        }

        draft = gmail.create_draft(["a@x.com"], "Draft", "body")

        assert draft.id == "d1" and draft.message.id == "orig"
        assert "raw" in service.users().drafts().create.call_args.kwargs["body"]["message"]

    def test_get_missing(self, gmail, service, http_error):
        service.users().drafts().get().execute.side_effect = http_error(404)
        assert gmail.get_draft("nope") is None

    def test_get(self, gmail, service):
        service.users().drafts().get().execute.return_value = {
            "id": "d1",
            "message": _raw_original(),
        }
        assert gmail.get_draft("d1").message.subject == "Plan"

    def test_list(self, gmail, service, batching):
        batching(service)
        service.users().drafts().list().execute.return_value = {
            "drafts": [{"id": "d1"}, {"id": "d2"}]
        }
        service.users().drafts().get().execute.side_effect = lambda: {
            "id": "d",
            "message": _raw_original(),
        }

        assert len(gmail.list_drafts()) == 2

    def test_send(self, gmail, service):
        service.users().drafts().send().execute.return_value = {"id": "orig"}
        assert gmail.send_draft("d1").id == "orig"
        assert service.users().drafts().send.call_args.kwargs["body"] == {"id": "d1"}

    def test_delete(self, gmail, service, http_error):
        assert gmail.delete_draft("d1") is True
        service.users().drafts().delete().execute.side_effect = http_error(404)
        assert gmail.delete_draft("d1") is False
