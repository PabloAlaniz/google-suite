"""Request parameters and bodies for the Drive API, shared by the sync and async clients."""

from typing import Any

from gsuite_core import drive_query_literal
from gsuite_core.exceptions import ValidationError

FILE_FIELDS = (
    "id, name, mimeType, size, createdTime, modifiedTime, parents, webViewLink, "
    "webContentLink, description, starred, trashed, md5Checksum"
)
PERMISSION_FIELDS = "id, type, role, emailAddress, domain, displayName"
FOLDER_MIME_TYPE = "application/vnd.google-apps.folder"

# Short names accepted by export(); values are the MIME types Drive exports to.
EXPORT_FORMATS = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "odt": "application/vnd.oasis.opendocument.text",
    "ods": "application/vnd.oasis.opendocument.spreadsheet",
    "odp": "application/vnd.oasis.opendocument.presentation",
    "rtf": "application/rtf",
    "txt": "text/plain",
    "md": "text/markdown",
    "html": "text/html",
    "epub": "application/epub+zip",
    "csv": "text/csv",
    "tsv": "text/tab-separated-values",
    "png": "image/png",
    "jpeg": "image/jpeg",
    "svg": "image/svg+xml",
}

_DEFAULT_EXPORTS = {
    "application/vnd.google-apps.document": "docx",
    "application/vnd.google-apps.spreadsheet": "xlsx",
    "application/vnd.google-apps.presentation": "pptx",
    "application/vnd.google-apps.drawing": "pdf",
}


def default_export_format(mime_type: str) -> str:
    """Export format used when downloading a Google file without choosing one."""
    return _DEFAULT_EXPORTS.get(mime_type, "pdf")


def files_query(
    query: str | None, parent_id: str | None, mime_type: str | None, trashed: bool | None
) -> str:
    """The q= of files.list: the raw query and each filter, joined with "and"."""
    parts = []
    if query:
        parts.append(f"({query})")
    if parent_id:
        parts.append(f"{drive_query_literal(parent_id)} in parents")
    if mime_type:
        parts.append(f"mimeType={drive_query_literal(mime_type)}")
    if trashed is not None:
        parts.append(f"trashed={'true' if trashed else 'false'}")
    return " and ".join(parts)


def name_query(name: str, exact: bool) -> str:
    """q= for a name search."""
    literal = drive_query_literal(name)
    return f"name={literal}" if exact else f"name contains {literal}"


def export_mime_type(format: str) -> str:
    """MIME type for a short export name or a MIME type; ValidationError otherwise."""
    mime_type = EXPORT_FORMATS.get(format.lower(), format)
    if "/" not in mime_type:
        raise ValidationError(
            "format", f"unknown export format {format!r}; use one of {sorted(EXPORT_FORMATS)}"
        )
    return mime_type


def metadata_body(
    name: str | None = None,
    description: str | None = None,
    starred: bool | None = None,
) -> dict[str, Any]:
    """files.update body with only the fields given."""
    fields = {"name": name, "description": description, "starred": starred}
    return {key: value for key, value in fields.items() if value is not None}


def new_file_body(
    name: str | None, parent_id: str | None, mime_type: str | None = None
) -> dict[str, Any]:
    """Metadata for files.create / files.copy; empty values are left to Drive."""
    body: dict[str, Any] = {}
    if name:
        body["name"] = name
    if mime_type:
        body["mimeType"] = mime_type
    if parent_id:
        body["parents"] = [parent_id]
    return body


def permission_request(
    role: str, type: str, email: str | None, domain: str | None, notify: bool
) -> tuple[dict[str, Any], dict[str, Any]]:
    """(body, extra query params) for permissions.create; ValidationError if incomplete."""
    if type in ("user", "group") and not email:
        raise ValidationError("email", f"required for type={type!r}")
    if type == "domain" and not domain:
        raise ValidationError("domain", "required for type='domain'")

    body: dict[str, Any] = {"type": type, "role": role}
    if email:
        body["emailAddress"] = email
    if domain:
        body["domain"] = domain
    params: dict[str, Any] = {}
    if type in ("user", "group"):
        params["sendNotificationEmail"] = notify
    return body, params
