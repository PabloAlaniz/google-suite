"""Query escaping and pagination in the Drive client."""

from unittest.mock import MagicMock, Mock, patch

import pytest

from gsuite_drive.client import Drive


@pytest.fixture
def service():
    with patch("gsuite_drive.client.build") as build:
        svc = MagicMock()
        svc.files().list().execute.return_value = {"files": []}
        build.return_value = svc
        yield svc


def _query(service) -> str:
    return service.files().list.call_args.kwargs["q"]


def test_search_escapes_quotes(service):
    Drive(Mock()).search("Pablo's notes")
    assert _query(service).startswith("(name contains 'Pablo\\'s notes')")


def test_search_cannot_inject_query(service):
    Drive(Mock()).search("x' or trashed=true or name contains '")
    query = _query(service)
    # The whole input stays inside one string literal
    assert query.startswith("(name contains 'x\\' or trashed=true or name contains \\'')")
    assert query.endswith(" and trashed=false")


def test_parent_and_mime_are_quoted(service):
    Drive(Mock()).list_files(parent_id="abc", mime_type="text/plain")
    assert _query(service) == "'abc' in parents and mimeType='text/plain' and trashed=false"


def test_requests_next_page_token(service):
    Drive(Mock()).list_files()
    assert service.files().list.call_args.kwargs["fields"].startswith("nextPageToken, files(")


def test_files_follow_pages(service):
    pages = iter(
        [
            {"files": [{"id": "1", "name": "a", "mimeType": "text/plain"}], "nextPageToken": "p2"},
            {"files": [{"id": "2", "name": "b", "mimeType": "text/plain"}]},
        ]
    )
    service.files().list.side_effect = lambda **kw: Mock(
        method="GET", execute=Mock(return_value=next(pages))
    )

    assert [f.id for f in Drive(Mock()).list_files(max_results=None)] == ["1", "2"]


def test_download_maps_http_errors(service, http_error):
    from gsuite_core.exceptions import NotFoundError

    with patch("gsuite_drive.client.MediaIoBaseDownload") as downloader:
        downloader.return_value.next_chunk.side_effect = http_error(404)
        with pytest.raises(NotFoundError):
            Drive(Mock()).get_content("missing")
