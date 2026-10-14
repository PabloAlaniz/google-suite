"""Fuzz GmailParser.parse_message with Gmail-API-shaped, attacker-controlled messages."""

import base64
import sys
from typing import Any

import atheris

with atheris.instrument_imports():
    from gsuite_gmail._testing.properties import check_parse_message

HEADER_NAMES = ["Date", "Content-Type", "Subject", "From", "To", "Cc", "Bcc", "Reply-To"]
MIME_TYPES = ["text/plain", "text/html", "multipart/mixed", "multipart/alternative", "image/png"]
MAX_DEPTH = 40


def _text(fdp: atheris.FuzzedDataProvider, size: int = 40) -> str:
    return fdp.ConsumeUnicodeNoSurrogates(size)


def _pick(fdp: atheris.FuzzedDataProvider, options: list[str]) -> str:
    if fdp.ConsumeBool():
        return options[fdp.ConsumeIntInRange(0, len(options) - 1)]
    return _text(fdp, 20)


def _body(fdp: atheris.FuzzedDataProvider) -> dict[str, Any]:
    body: dict[str, Any] = {}
    if fdp.ConsumeBool():
        raw = fdp.ConsumeBytes(fdp.ConsumeIntInRange(0, 200))
        # Mostly valid base64url, sometimes garbage
        body["data"] = base64.urlsafe_b64encode(raw).decode() if fdp.ConsumeBool() else _text(fdp)
    if fdp.ConsumeBool():
        body["attachmentId"] = _text(fdp, 8)
    if fdp.ConsumeBool():
        body["size"] = fdp.ConsumeIntInRange(0, 10**9)
    return body


def _part(fdp: atheris.FuzzedDataProvider, depth: int) -> dict[str, Any]:
    part: dict[str, Any] = {}
    if fdp.ConsumeBool():
        part["mimeType"] = _pick(fdp, MIME_TYPES)
    if fdp.ConsumeBool():
        part["headers"] = [
            {"name": _pick(fdp, HEADER_NAMES), "value": _text(fdp)}
            for _ in range(fdp.ConsumeIntInRange(0, 6))
        ]
    if fdp.ConsumeBool():
        part["body"] = _body(fdp)
    if fdp.ConsumeBool():
        part["filename"] = _text(fdp, 12)
    if depth < MAX_DEPTH and fdp.ConsumeBool():
        part["parts"] = [_part(fdp, depth + 1) for _ in range(fdp.ConsumeIntInRange(0, 3))]
    return part


def TestOneInput(data: bytes) -> None:
    fdp = atheris.FuzzedDataProvider(data)
    message: dict[str, Any] = {"id": _text(fdp, 8) or "m"}
    if fdp.ConsumeBool():
        message["threadId"] = _text(fdp, 8)
    if fdp.ConsumeBool():
        message["internalDate"] = str(fdp.ConsumeIntInRange(0, 2**100))
    if fdp.ConsumeBool():
        message["snippet"] = _text(fdp, 20)
    include_body = fdp.ConsumeBool()
    message["payload"] = _part(fdp, 0)
    check_parse_message(message, include_body)


def main() -> None:
    atheris.Setup(sys.argv, TestOneInput)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
