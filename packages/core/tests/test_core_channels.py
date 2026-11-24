"""Notification channel requests and responses."""

from datetime import UTC, datetime

import pytest

from gsuite_core import Channel
from gsuite_core.channels import channel_body, parse_channel, parse_expiration, stop_body
from gsuite_core.exceptions import ValidationError


def test_body():
    body = channel_body("https://x.example/hook", "secret", "my-channel", ttl=3600)
    assert body == {
        "id": "my-channel",
        "type": "web_hook",
        "address": "https://x.example/hook",
        "token": "secret",
        "params": {"ttl": "3600"},
    }


def test_body_generates_an_id():
    first = channel_body("https://x.example/hook", "secret")
    second = channel_body("https://x.example/hook", "secret")
    assert first["id"] != second["id"]
    assert "params" not in first


@pytest.mark.parametrize(
    ("kwargs", "field"),
    [
        ({"address": "http://x.example/hook", "token": "s"}, "address"),
        ({"address": "https://x.example/hook", "token": ""}, "token"),
        ({"address": "https://x.example/hook", "token": "s" * 257}, "token"),
        ({"address": "https://x.example/hook", "token": "s", "ttl": 0}, "ttl"),
    ],
)
def test_body_validation(kwargs, field):
    with pytest.raises(ValidationError) as error:
        channel_body(**kwargs)
    assert error.value.field == field


def test_parse_channel():
    data = {
        "id": "c1",
        "resourceId": "r1",
        "resourceUri": "https://www.googleapis.com/calendar/v3/calendars/primary/events",
        "expiration": "1767225600000",
    }
    channel = parse_channel(data, "secret")

    assert (channel.id, channel.resource_id, channel.token) == ("c1", "r1", "secret")
    assert channel.expiration == datetime(2026, 1, 1, tzinfo=UTC)
    assert channel.raw is data
    assert "secret" not in repr(channel)


@pytest.mark.parametrize("value", [None, "", "soon", "9" * 30])
def test_expiration_that_is_not_a_timestamp(value):
    assert parse_expiration(value) is None


def test_stop_body():
    channel = Channel(id="c1", resource_id="r1")
    assert stop_body(channel) == {"id": "c1", "resourceId": "r1"}
    assert stop_body("c1", "r1") == {"id": "c1", "resourceId": "r1"}
    with pytest.raises(ValidationError):
        stop_body("c1")
