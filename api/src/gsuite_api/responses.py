"""Shared response helpers."""

import re
from urllib.parse import quote

from fastapi import Response


def content_disposition(filename: str | None) -> str:
    """Attachment header that survives quotes, newlines and non-ASCII names.

    Filenames come from email senders or Drive users, so they are untrusted:
    an ASCII fallback with unsafe characters replaced, plus the exact name as
    an RFC 5987 filename* parameter (RFC 6266).
    """
    name = filename or "attachment"
    fallback = re.sub(r"[^A-Za-z0-9._ -]", "_", name).strip() or "attachment"
    return f"attachment; filename=\"{fallback}\"; filename*=UTF-8''{quote(name, safe='')}"


def download_response(content: bytes, filename: str | None, media_type: str) -> Response:
    """Bytes served as a file download."""
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": content_disposition(filename)},
    )
