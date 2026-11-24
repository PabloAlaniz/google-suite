"""Notification channels: how Calendar and Drive push "something changed" to a URL.

A channel tells Google to POST to an HTTPS address whenever a resource
changes. The notification carries no data, only headers saying which channel
fired; the receiver then asks the API what changed (``Calendar.sync``,
``Drive.changes``). Channels expire and are not renewed by Google: watch again
before ``Channel.expiration``.
"""

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from gsuite_core.exceptions import ValidationError

MAX_TOKEN_LENGTH = 256


@dataclass
class Channel:
    """A notification channel, as Google created it.

    Keep ``id`` and ``resource_id``: both are needed to stop the channel.
    """

    id: str
    resource_id: str
    expiration: datetime | None = None
    # The secret Google echoes in X-Goog-Channel-Token with every notification
    token: str | None = field(default=None, repr=False)
    resource_uri: str | None = None
    raw: dict[str, Any] = field(default_factory=dict, repr=False)


def channel_body(
    address: str, token: str, channel_id: str | None = None, ttl: int | None = None
) -> dict[str, Any]:
    """The body of a ``watch`` request.

    Args:
        address: The HTTPS URL Google will POST notifications to
        token: A secret Google sends back in ``X-Goog-Channel-Token``; the
            receiver must check it, because the notification isn't signed
        channel_id: Your ID for the channel (default: a random UUID)
        ttl: Seconds the channel should live; Google caps it per API

    Raises:
        ValidationError: The address isn't HTTPS, or the token is missing or too long
    """
    if not address.startswith("https://"):
        raise ValidationError("address", "Google only delivers notifications to https:// URLs")
    if not token:
        raise ValidationError("token", "a secret token is required to verify notifications")
    if len(token) > MAX_TOKEN_LENGTH:
        raise ValidationError("token", f"at most {MAX_TOKEN_LENGTH} characters")
    body: dict[str, Any] = {
        "id": channel_id or str(uuid.uuid4()),
        "type": "web_hook",
        "address": address,
        "token": token,
    }
    if ttl is not None:
        if ttl <= 0:
            raise ValidationError("ttl", "must be a positive number of seconds")
        body["params"] = {"ttl": str(int(ttl))}
    return body


def parse_expiration(value: Any) -> datetime | None:
    """A Google expiration (milliseconds since the epoch, often as text) as a UTC datetime."""
    try:
        return datetime.fromtimestamp(int(value) / 1000, tz=UTC)
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def parse_channel(data: dict[str, Any], token: str | None = None) -> Channel:
    """A ``watch`` response as a Channel."""
    return Channel(
        id=str(data.get("id", "")),
        resource_id=str(data.get("resourceId", "")),
        expiration=parse_expiration(data.get("expiration")),
        token=token,
        resource_uri=data.get("resourceUri"),
        raw=data,
    )


def stop_body(channel: Channel | str, resource_id: str | None = None) -> dict[str, str]:
    """The body of ``channels.stop``, from a Channel or from its two IDs."""
    if isinstance(channel, Channel):
        channel_id, resource_id = channel.id, channel.resource_id
    else:
        channel_id = channel
    if not channel_id or not resource_id:
        raise ValidationError(
            "resource_id", "stopping a channel needs its id and resource_id (or the Channel)"
        )
    return {"id": channel_id, "resourceId": resource_id}
