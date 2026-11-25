"""What changed in Drive since a page token (incremental sync)."""

from dataclasses import dataclass, field

from gsuite_drive.file import File


@dataclass
class ChangesDelta:
    """Files changed or removed since a page token, and the token to resume from.

    ``changed`` holds each file as it is now; a trashed file is a change
    (``file.trashed``). ``removed`` holds the IDs of files deleted for good or
    no longer shared with the user. Keep ``page_token`` and pass it to the next
    ``Drive.changes``.
    """

    changed: list[File] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    page_token: str | None = None
