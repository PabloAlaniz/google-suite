"""Formatting, protection, find/replace, worksheets and DataFrames."""

import re
from unittest.mock import MagicMock, Mock, patch

import pytest

from gsuite_core.exceptions import ValidationError
from gsuite_sheets.client import Sheets
from gsuite_sheets.spreadsheet import Spreadsheet
from gsuite_sheets.worksheet import Worksheet


@pytest.fixture
def service():
    with patch("gsuite_sheets.client.build") as build:
        svc = MagicMock()
        svc.spreadsheets().batchUpdate().execute.return_value = {"replies": [{}]}
        build.return_value = svc
        yield svc


@pytest.fixture
def sheets(service):
    return Sheets(Mock())


@pytest.fixture
def ws(sheets):
    doc = Spreadsheet(id="sid", title="Doc", url="u", _sheets=sheets)
    sheet = Worksheet(id=5, title="Pablo's 2024", index=0, _spreadsheet=doc)
    doc.worksheets.append(sheet)
    return sheet


def requests(service) -> list[dict]:
    return service.spreadsheets().batchUpdate.call_args.kwargs["body"]["requests"]


def value_call(service, method):
    return getattr(service.spreadsheets().values(), method).call_args.kwargs


class TestRanges:
    def test_sheet_title_is_quoted(self, ws, service):
        service.spreadsheets().values().get().execute.return_value = {"values": [["x"]]}
        ws.get("A1:B2")
        assert value_call(service, "get")["range"] == "'Pablo''s 2024'!A1:B2"

    def test_all_values_reads_whole_sheet(self, ws, service):
        # Used to request A1:ZZ and lose columns beyond ZZ
        service.spreadsheets().values().get().execute.return_value = {}
        ws.get_all_values()
        assert value_call(service, "get")["range"] == "'Pablo''s 2024'"

    def test_clear_whole_sheet(self, ws, service):
        ws.clear()
        assert value_call(service, "clear")["range"] == "'Pablo''s 2024'"

    def test_value_render(self, ws, service):
        service.spreadsheets().values().get().execute.return_value = {}
        ws.get("A1", value_render="FORMULA")
        assert value_call(service, "get")["valueRenderOption"] == "FORMULA"

    def test_raw_writes(self, ws, service):
        ws.update("A1", [["=1+1"]], value_input="RAW")
        assert value_call(service, "update")["valueInputOption"] == "RAW"

    def test_batch_get(self, ws, service):
        service.spreadsheets().values().batchGet().execute.return_value = {
            "valueRanges": [{"values": [["a"]]}, {}]
        }

        result = ws.batch_get(["A1", "C1:C2"])

        assert result == [[["a"]], []]
        assert value_call(service, "batchGet")["ranges"] == [
            "'Pablo''s 2024'!A1",
            "'Pablo''s 2024'!C1:C2",
        ]


class TestFormatting:
    def test_format(self, ws, service):
        ws.format("A1:B1", {"textFormat": {"bold": True}, "backgroundColor": {"red": 1}})

        (request,) = requests(service)
        repeat = request["repeatCell"]
        assert repeat["range"] == {
            "sheetId": 5,
            "startRowIndex": 0,
            "endRowIndex": 1,
            "startColumnIndex": 0,
            "endColumnIndex": 2,
        }
        # Only the given keys are overwritten
        assert repeat["fields"] == "userEnteredFormat(textFormat,backgroundColor)"

    def test_empty_format_rejected(self, ws):
        with pytest.raises(ValidationError):
            ws.format("A1", {})

    def test_freeze(self, ws, service):
        ws.freeze(rows=1)

        props = requests(service)[0]["updateSheetProperties"]
        assert props["properties"]["gridProperties"] == {"frozenRowCount": 1}
        assert props["fields"] == "gridProperties.frozenRowCount"

    def test_freeze_needs_something(self, ws):
        with pytest.raises(ValidationError):
            ws.freeze()

    def test_protect_range(self, ws, service):
        service.spreadsheets().batchUpdate().execute.return_value = {
            "replies": [{"addProtectedRange": {"protectedRange": {"protectedRangeId": 42}}}]
        }

        protected_id = ws.protect("A1:A10", description="Totals", editors=["a@x.com"])

        protected = requests(service)[0]["addProtectedRange"]["protectedRange"]
        assert protected_id == 42
        assert protected["editors"] == {"users": ["a@x.com"]}
        assert protected["range"]["endRowIndex"] == 10

    def test_protect_whole_sheet_warning_only(self, ws, service):
        service.spreadsheets().batchUpdate().execute.return_value = {
            "replies": [{"addProtectedRange": {"protectedRange": {"protectedRangeId": 1}}}]
        }

        ws.protect(warning_only=True, editors=["ignored@x.com"])

        protected = requests(service)[0]["addProtectedRange"]["protectedRange"]
        assert protected["range"] == {"sheetId": 5}
        # The API rejects editors together with warningOnly
        assert "editors" not in protected


class TestFindReplace:
    def test_replace_in_sheet(self, ws, service):
        service.spreadsheets().batchUpdate().execute.return_value = {
            "replies": [{"findReplace": {"occurrencesChanged": 3}}]
        }

        assert ws.replace(r"Mr\.", "Mr", regex=True) == 3
        request = requests(service)[0]["findReplace"]
        assert request["sheetId"] == 5
        assert request["searchByRegex"] is True

    def test_replace_everywhere(self, sheets, service):
        service.spreadsheets().batchUpdate().execute.return_value = {"replies": [{}]}

        assert sheets.find_replace("sid", "a", "b") == 0
        assert requests(service)[0]["findReplace"]["allSheets"] is True

    def test_find_exact_and_regex(self, ws, service):
        service.spreadsheets().values().get().execute.return_value = {
            "values": [["Name", "Phone"], ["Ana", "555-1234"], ["Total", "x"]]
        }

        assert ws.find("Total") == (3, 1)
        assert ws.find("Tot") is None  # exact match, like gspread
        assert ws.find(re.compile(r"\d{3}-\d{4}")) == (2, 2)
        assert ws.findall(re.compile(r"^[A-Z]")) == [(1, 1), (1, 2), (2, 1), (3, 1)]


class TestWorksheets:
    def test_added_worksheet_is_linked(self, ws, service):
        service.spreadsheets().batchUpdate().execute.return_value = {
            "replies": [{"addSheet": {"properties": {"sheetId": 9, "title": "New", "index": 1}}}]
        }

        new = ws._spreadsheet.add_worksheet("New")
        new.update("A1", [["ok"]])  # used to raise "not linked to spreadsheet"

        assert value_call(service, "update")["range"] == "'New'!A1"

    def test_duplicate(self, ws, service):
        service.spreadsheets().batchUpdate().execute.return_value = {
            "replies": [
                {"duplicateSheet": {"properties": {"sheetId": 11, "title": "Copy", "index": 1}}}
            ]
        }

        copy = ws._spreadsheet.duplicate_worksheet(ws, "Copy")

        assert copy.id == 11 and copy._spreadsheet is ws._spreadsheet
        assert requests(service)[0]["duplicateSheet"] == {
            "sourceSheetId": 5,
            "newSheetName": "Copy",
        }

    def test_rename(self, ws, service):
        ws.rename("Renamed")
        assert ws.title == "Renamed"
        assert requests(service)[0]["updateSheetProperties"]["fields"] == "title"

    def test_unlinked_worksheet(self):
        with pytest.raises(RuntimeError, match="not linked"):
            Worksheet(id=0, title="x", index=0).get_all_values()


class TestDataFrames:
    pd = pytest.importorskip("pandas")

    def test_to_dataframe(self, ws, service):
        service.spreadsheets().values().get().execute.return_value = {
            "values": [["title"], ["name", "age"], ["Ana", "30"], ["Bo"]]
        }

        df = ws.to_dataframe(header_row=2)

        assert list(df.columns) == ["name", "age"]
        assert df.to_dict("records") == [{"name": "Ana", "age": "30"}, {"name": "Bo", "age": ""}]

    def test_to_dataframe_names_extra_columns(self, ws, service):
        service.spreadsheets().values().get().execute.return_value = {"values": [["a"], ["1", "2"]]}
        assert list(ws.to_dataframe().columns) == ["a", "column_2"]

    def test_from_dataframe(self, ws, service):
        from datetime import date

        df = self.pd.DataFrame(
            {
                "name": ["Ana", None],
                "score": [1.5, float("nan")],
                "when": [self.pd.Timestamp("2026-01-02"), self.pd.NaT],
                "day": [date(2026, 1, 3), date(2026, 1, 4)],
            }
        )

        ws.from_dataframe(df, start="B2", clear=True)

        call = value_call(service, "update")
        assert call["range"] == "'Pablo''s 2024'!B2"
        assert call["body"]["values"] == [
            ["name", "score", "when", "day"],
            ["Ana", 1.5, "2026-01-02T00:00:00", "2026-01-03"],
            ["", "", "", "2026-01-04"],
        ]
        service.spreadsheets().values().clear.assert_called()

    def test_from_dataframe_with_index(self, ws, service):
        df = self.pd.DataFrame({"v": [10]}, index=self.pd.Index(["r1"], name="row"))

        ws.from_dataframe(df, include_index=True, include_header=False)

        assert value_call(service, "update")["body"]["values"] == [["r1", 10]]


def test_missing_pandas_message(ws):
    with (
        patch.dict("sys.modules", {"pandas": None}),
        pytest.raises(ImportError, match=r"gsuite-sdk\[pandas\]"),
    ):
        ws.to_dataframe()


class TestReadingHelpers:
    @pytest.fixture
    def values(self, service):
        def set_values(rows):
            service.spreadsheets().values().get().execute.return_value = {"values": rows}

        return set_values

    def test_records(self, ws, values):
        values([["name", "age"], ["Ana", "30"], ["Bo"]])
        assert ws.get_all_records() == [{"name": "Ana", "age": "30"}, {"name": "Bo", "age": ""}]

    def test_records_empty(self, ws, values):
        values([])
        assert ws.get_all_records() == []

    def test_row_col_cell(self, ws, values, service):
        values([["x", "y"]])
        assert ws.row_values(1) == ["x", "y"]
        assert value_call(service, "get")["range"] == "'Pablo''s 2024'!1:1"

        values([["a"], [], ["c"]])
        assert ws.col_values(28) == ["a", "", "c"]
        assert value_call(service, "get")["range"] == "'Pablo''s 2024'!AB:AB"

        values([])
        assert ws.cell(2, 3) == ""

    def test_append_row_and_update_cell(self, ws, service):
        ws.append_row(["a", 1])
        assert value_call(service, "append")["range"] == "'Pablo''s 2024'!A1"
        ws.update_cell(3, 2, "v")
        assert value_call(service, "update")["range"] == "'Pablo''s 2024'!B3"

    def test_url(self, ws):
        assert ws.url == "u#gid=5"
        assert Worksheet(id=1, title="x", index=0).url is None


class TestSpreadsheetLookups:
    def test_lookups(self, ws):
        doc = ws._spreadsheet
        assert doc.sheet1 is ws
        assert doc.worksheet("Pablo's 2024") is ws
        assert doc.worksheet("nope") is None
        assert doc.get_worksheet(0) is ws
        assert doc.get_worksheet(3) is None

    def test_empty_spreadsheet(self):
        assert Spreadsheet(id="s", title="t", url="u").sheet1 is None

    def test_del_worksheet_removes_it(self, ws, service):
        doc = ws._spreadsheet
        assert doc.del_worksheet(ws) is True
        assert doc.worksheets == []

    def test_share(self, ws, service):
        service.permissions().create().execute.return_value = {"id": "p"}
        assert ws._spreadsheet.share("a@x.com", role="writer") is True

    @pytest.mark.parametrize("method", ["add_worksheet", "share"])
    def test_unlinked(self, method):
        doc = Spreadsheet(id="s", title="t", url="u")
        with pytest.raises(RuntimeError, match="not linked"):
            getattr(doc, method)("x")
