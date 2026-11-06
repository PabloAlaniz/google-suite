"""The modules Gmail delegates to: label resolution and MIME building."""

import base64
from email import message_from_bytes
from unittest.mock import Mock

import pytest

from gsuite_core.exceptions import ValidationError
from gsuite_gmail._labels import LabelResolver
from gsuite_gmail._mime import MessageSpec, build_message, encode_for_api, prefixed

LABELS = [{"id": "Label_7", "name": "Work"}, {"id": "Label_8", "name": "Bills"}]


class TestLabelResolver:
    def test_names_and_ids_resolve_from_one_listing(self):
        listing = Mock(return_value=LABELS)
        labels = LabelResolver(listing)

        assert labels.resolve("Work") == "Label_7"
        assert labels.resolve("Label_8") == "Label_8"
        assert labels.resolve("Nope") is None
        listing.assert_called_once()

    def test_system_and_category_labels_skip_the_listing(self):
        listing = Mock(return_value=LABELS)
        labels = LabelResolver(listing)

        assert labels.resolve("INBOX") == "INBOX"
        assert labels.resolve("CATEGORY_PROMOTIONS") == "CATEGORY_PROMOTIONS"
        listing.assert_not_called()
        assert not labels.cached

    def test_invalidate_lists_again(self):
        listing = Mock(return_value=LABELS)
        labels = LabelResolver(listing)
        labels.resolve("Work")

        labels.invalidate()
        listing.return_value = [*LABELS, {"id": "Label_9", "name": "New"}]

        assert labels.resolve("New") == "Label_9"
        assert listing.call_count == 2

    def test_require_names_the_unknown_label(self):
        labels = LabelResolver(Mock(return_value=LABELS))

        assert labels.require(["Work", "UNREAD"]) == ["Label_7", "UNREAD"]
        with pytest.raises(ValidationError, match="Nope"):
            labels.require(["Work", "Nope"])


def _decode(body: dict) -> object:
    return message_from_bytes(base64.urlsafe_b64decode(body["raw"]))


class TestMime:
    def test_reply_headers_extend_references(self):
        spec = MessageSpec(
            to=["a@example.com"],
            subject="Re: Hi",
            body="ok",
            in_reply_to="<b@mail>",
            references="<a@mail>",
        )
        parsed = _decode(encode_for_api(build_message(spec)))

        assert parsed["In-Reply-To"] == "<b@mail>"
        assert parsed["References"] == "<a@mail> <b@mail>"

    def test_no_threading_headers_without_a_parent(self):
        parsed = _decode(encode_for_api(build_message(MessageSpec(["a@example.com"], "Hi", "x"))))

        assert parsed["In-Reply-To"] is None
        assert parsed["References"] is None

    def test_html_gets_a_plain_alternative(self):
        spec = MessageSpec(["a@example.com"], "Hi", "<p>Hello</p><p>there</p>", html=True)
        parsed = _decode(encode_for_api(build_message(spec)))

        parts = {part.get_content_type(): part for part in parsed.walk()}
        assert "Hello\nthere" in parts["text/plain"].get_payload(decode=True).decode()
        assert "<p>Hello</p>" in parts["text/html"].get_payload(decode=True).decode()

    def test_thread_id_only_when_given(self):
        message = build_message(MessageSpec(["a@example.com"], "Hi", "x"))

        assert "threadId" not in encode_for_api(message)
        assert encode_for_api(message, "t1")["threadId"] == "t1"

    @pytest.mark.parametrize(
        ("subject", "expected"),
        [("Hi", "Re: Hi"), ("Re: Hi", "Re: Hi"), ("RE: Hi", "RE: Hi")],
    )
    def test_prefixed_keeps_an_existing_prefix(self, subject, expected):
        assert prefixed(subject, "Re:") == expected
