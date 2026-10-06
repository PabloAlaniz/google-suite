"""gsuite_sheets.engine_adapter: port surface and request details.

Behavior is covered by running every engine test through the adapter
(``pytest --engine-backend=adapter``); these tests pin what that can't see:
the exact requests sent to Google.
"""

from typing import Any
from unittest.mock import MagicMock, Mock

import pytest

from gsuite_core.exceptions import NotFoundError
from gsuite_sheets.client import Sheets
from gsuite_sheets.engine.domain.errors import SpreadsheetNotFoundError, WorksheetNotFoundError
from gsuite_sheets.engine.infrastructure.cache import (
    CachingClient,
    CachingSpreadsheet,
    CachingWorksheet,
    _Cache,
)
from gsuite_sheets.engine.ports.sheets import ClientPort, SpreadsheetPort, WorksheetPort
from gsuite_sheets.engine.testing import InMemoryClient, InMemorySpreadsheet, InMemoryWorksheet
from gsuite_sheets.engine_adapter import (
    Cell,
    GoogleApiClient,
    GoogleApiSpreadsheet,
    GoogleApiWorksheet,
)


def _members(protocol: type) -> list[str]:
    return sorted(name for name in vars(protocol) if not name.startswith("_"))


def _memory_spreadsheet() -> InMemorySpreadsheet:
    ss = InMemorySpreadsheet("doc", "doc0")
    ss.seed("Hoja1", [["a"]])
    return ss


def _adapter_spreadsheet() -> GoogleApiSpreadsheet:
    return GoogleApiSpreadsheet(Sheets(Mock()), "sid", [("Hoja1", 0)])


CONTRACT = [
    (WorksheetPort, InMemoryWorksheet(_memory_spreadsheet(), "Hoja1", 0)),
    (
        WorksheetPort,
        CachingWorksheet(InMemoryWorksheet(_memory_spreadsheet(), "Hoja1", 0), _Cache()),
    ),
    (WorksheetPort, GoogleApiWorksheet(_adapter_spreadsheet(), "Hoja1", 0)),
    (SpreadsheetPort, _memory_spreadsheet()),
    (SpreadsheetPort, CachingSpreadsheet(_memory_spreadsheet(), _Cache())),
    (SpreadsheetPort, _adapter_spreadsheet()),
    (ClientPort, InMemoryClient()),
    (ClientPort, CachingClient(InMemoryClient())),
    (ClientPort, GoogleApiClient(Sheets(Mock()))),
]


@pytest.mark.parametrize(
    ("port", "implementation"),
    CONTRACT,
    ids=[f"{p.__name__}-{type(i).__name__}" for p, i in CONTRACT],
)
def test_implements_full_port_surface(port: type, implementation: Any) -> None:
    missing = [m for m in _members(port) if not hasattr(implementation, m)]
    assert not missing, f"{type(implementation).__name__} lacks {missing}"


@pytest.fixture
def service():
    return MagicMock()


@pytest.fixture
def sheets(service):
    client = Sheets(Mock())
    client._sheets_service = service
    client._drive_service = service
    return client


@pytest.fixture
def ws(sheets):
    return GoogleApiWorksheet(
        GoogleApiSpreadsheet(sheets, "sid", [("Pablo's 2024", 7)]), "Pablo's 2024", 7
    )


def _kwargs(method: Any) -> dict[str, Any]:
    return method.call_args.kwargs


class TestRanges:
    def test_titles_are_quoted(self, ws, service):
        service.spreadsheets().values().get().execute.return_value = {"values": [["x"]]}

        ws.get_all_values()
        ws.update_cell(2, 3, "v")

        assert _kwargs(service.spreadsheets().values().get)["range"] == "'Pablo''s 2024'"
        assert _kwargs(service.spreadsheets().values().update)["range"] == "'Pablo''s 2024'!C2"

    def test_batch_update_qualifies_bare_ranges_only(self, ws, service):
        ws.batch_update(
            [{"range": "A1", "values": [[1]]}, {"range": "'Other'!B2", "values": [[2]]}], "RAW"
        )

        data = _kwargs(service.spreadsheets().values().batchUpdate)["body"]["data"]
        assert [d["range"] for d in data] == ["'Pablo''s 2024'!A1", "'Other'!B2"]

    def test_get_all_values_is_rectangular(self, ws, service):
        service.spreadsheets().values().get().execute.return_value = {"values": [["a", "b"], ["c"]]}
        assert ws.get_all_values() == [["a", "b"], ["c", ""]]

    def test_range_includes_empty_cells(self, ws, service):
        # GSpreadManager's native client returned only cells with data, so
        # row_with_empty_in_column never found the empty cell it looks for
        service.spreadsheets().values().get().execute.return_value = {"values": [["x"], [], ["z"]]}

        cells = ws.range("B1:B4")

        assert [c.value for c in cells] == ["x", "", "z", ""]
        assert cells[1] == Cell(row=2, col=2, value="")

    def test_format_and_merge_use_grid_ranges(self, ws, service):
        ws.format("A1:B1", {"textFormat": {"bold": True}})
        request = _kwargs(service.spreadsheets().batchUpdate)["body"]["requests"][0]["repeatCell"]
        assert request["range"] == {
            "sheetId": 7,
            "startRowIndex": 0,
            "endRowIndex": 1,
            "startColumnIndex": 0,
            "endColumnIndex": 2,
        }
        assert request["fields"] == "userEnteredFormat(textFormat)"


class TestClient:
    def test_open_escapes_title(self, sheets, service):
        service.files().list().execute.return_value = {"files": [{"id": "k"}]}
        service.spreadsheets().get().execute.return_value = {"sheets": []}

        GoogleApiClient(sheets).open("Pablo's budget")

        assert _kwargs(service.files().list)["q"].startswith("name = 'Pablo\\'s budget'")

    def test_open_missing(self, sheets, service):
        service.files().list().execute.return_value = {"files": []}
        with pytest.raises(SpreadsheetNotFoundError):
            GoogleApiClient(sheets).open("nope")

    def test_open_by_key_maps_not_found(self, sheets, service, http_error):
        service.spreadsheets().get().execute.side_effect = http_error(404)
        with pytest.raises(SpreadsheetNotFoundError) as exc_info:
            GoogleApiClient(sheets).open_by_key("missing")
        assert isinstance(exc_info.value.__cause__, NotFoundError)

    def test_open_is_cached(self, sheets, service):
        service.spreadsheets().get().execute.return_value = {
            "sheets": [{"properties": {"sheetId": 0, "title": "A"}}]
        }
        client = GoogleApiClient(sheets)
        get = service.spreadsheets().get
        get.reset_mock()

        assert client.open_by_key("k") is client.open_by_key("k")
        assert get.call_count == 1

    def test_missing_worksheet(self, sheets):
        ss = GoogleApiSpreadsheet(sheets, "sid", [("A", 0)])
        with pytest.raises(WorksheetNotFoundError):
            ss.worksheet("B")

    def test_copy_with_permissions_skips_owner(self, sheets, service):
        service.files().copy().execute.return_value = {"id": "new"}
        service.permissions().list().execute.return_value = {
            "permissions": [
                {"id": "o", "type": "user", "role": "owner", "emailAddress": "me@x.com"},
                {"id": "w", "type": "user", "role": "writer", "emailAddress": "ana@x.com"},
            ]
        }
        service.spreadsheets().get().execute.return_value = {"sheets": []}

        GoogleApiClient(sheets).copy("src", "Copy", copy_permissions=True, folder_id=None)

        created = [
            c.kwargs["body"] for c in service.permissions().create.call_args_list if c.kwargs
        ]
        assert created == [{"type": "user", "role": "writer", "emailAddress": "ana@x.com"}]


class TestSharing:
    def test_domain_share_sends_the_domain(self, sheets, service):
        # GSpreadManager's native client dropped it (emailAddress only for users)
        GoogleApiSpreadsheet(sheets, "sid", []).share(
            "example.com", "domain", "reader", False, None, True
        )

        kwargs = _kwargs(service.permissions().create)
        assert kwargs["body"] == {
            "type": "domain",
            "role": "reader",
            "domain": "example.com",
            "allowFileDiscovery": False,
        }
        assert "sendNotificationEmail" not in kwargs

    def test_user_share_notifies(self, sheets, service):
        GoogleApiSpreadsheet(sheets, "sid", []).share(
            "a@x.com", "user", "writer", True, "hi", False
        )

        kwargs = _kwargs(service.permissions().create)
        assert kwargs["sendNotificationEmail"] is True and kwargs["emailMessage"] == "hi"

    def test_remove_permissions_by_value_and_role(self, sheets, service):
        service.permissions().list().execute.return_value = {
            "permissions": [
                {"id": "1", "role": "writer", "emailAddress": "a@x.com"},
                {"id": "2", "role": "reader", "emailAddress": "a@x.com"},
            ]
        }

        removed = GoogleApiSpreadsheet(sheets, "sid", []).remove_permissions("a@x.com", "writer")

        assert removed == ["1"]
