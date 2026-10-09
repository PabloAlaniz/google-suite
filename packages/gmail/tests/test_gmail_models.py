"""Message fluent methods and Thread properties."""

from unittest.mock import MagicMock

import pytest

from gsuite_gmail.message import Attachment, Message
from gsuite_gmail.thread import Thread


def _message(labels=("INBOX",), **extra):
    msg = Message(
        id="m1",
        thread_id="t1",
        subject="s",
        sender="a@x.com",
        recipient="b@x.com",
        labels=list(labels),
        **extra,
    )
    msg._gmail = MagicMock()
    msg._gmail._get_label_id.side_effect = lambda name: {"Work": "Label_7"}.get(name)
    return msg


@pytest.mark.parametrize(
    ("method", "kwargs", "labels_after"),
    [
        ("mark_as_read", {"remove": ["UNREAD"]}, ["INBOX"]),
        ("mark_as_unread", {"add": ["UNREAD"]}, ["INBOX", "UNREAD"]),
        ("star", {"add": ["STARRED"]}, ["INBOX", "STARRED"]),
        ("mark_important", {"add": ["IMPORTANT"]}, ["INBOX", "IMPORTANT"]),
        ("archive", {"remove": ["INBOX"]}, []),
    ],
)
def test_label_changes(method, kwargs, labels_after):
    msg = _message(labels=["INBOX", "UNREAD"] if method == "mark_as_read" else ["INBOX"])

    assert getattr(msg, method)() is msg  # chainable
    msg._gmail._modify_labels.assert_called_once_with("m1", **kwargs)
    assert msg.labels == labels_after


@pytest.mark.parametrize(
    ("method", "kwargs"),
    [
        ("unstar", {"remove": ["STARRED"]}),
        ("mark_not_important", {"remove": ["IMPORTANT"]}),
        ("move_to_inbox", {"add": ["INBOX"]}),
    ],
)
def test_more_label_changes(method, kwargs):
    msg = _message(labels=["STARRED", "IMPORTANT"])
    getattr(msg, method)()
    msg._gmail._modify_labels.assert_called_once_with("m1", **kwargs)


def test_custom_labels_by_name():
    msg = _message()
    msg.add_label("Work").remove_label("Work")
    assert [c.kwargs for c in msg._gmail._modify_labels.call_args_list] == [
        {"add": ["Label_7"]},
        {"remove": ["Label_7"]},
    ]


def test_unknown_custom_label_is_ignored():
    msg = _message()
    msg.add_label("Nope")
    msg._gmail._modify_labels.assert_not_called()


def test_trash_untrash():
    msg = _message()
    msg.trash().untrash()
    msg._gmail._trash_message.assert_called_once_with("m1")
    msg._gmail._untrash_message.assert_called_once_with("m1")


def test_body_prefers_plain():
    assert _message(plain="p", html="<p>h</p>").body == "p"
    assert _message(html="<p>h</p>").body == "<p>h</p>"


def test_forward_delegates():
    msg = _message()
    msg.forward(["c@x.com"], "fyi")
    msg._gmail.forward.assert_called_once_with(msg, ["c@x.com"], "fyi", include_attachments=True)


def test_unlinked_message():
    msg = Message(id="m", thread_id="t", subject="", sender="", recipient="")
    with pytest.raises(RuntimeError):
        msg.reply("x")
    with pytest.raises(RuntimeError):
        Attachment(id="a", filename="f", mime_type="x", size=0).download()


def test_attachment_save(tmp_path):
    att = Attachment(id="a", filename="f.txt", mime_type="text/plain", size=2, _data=b"hi")
    path = att.save(str(tmp_path / "out.txt"))
    assert open(path, "rb").read() == b"hi"


def test_thread_properties():
    first = _message(labels=["INBOX"])
    second = _message(labels=["UNREAD"])
    second.sender = "c@x.com"
    thread = Thread(id="t1", messages=[first, second])

    assert thread.subject == "s"
    assert thread.message_count == 2
    assert thread.participants == {"a@x.com", "b@x.com", "c@x.com"}
    assert thread.has_unread
    assert thread.labels == {"INBOX", "UNREAD"}
    assert Thread(id="empty").subject == ""
