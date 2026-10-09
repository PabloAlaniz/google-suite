"""The engine's features through the public API (Sheets / Spreadsheet / Worksheet).

Runs end to end: Worksheet -> engine -> engine_adapter -> fake googleapiclient
service -> in-memory emulator.
"""

import inspect
import io
from dataclasses import dataclass, fields
from datetime import date

import pytest

from gsuite_sheets import (
    CellFormat,
    Color,
    SchemaError,
    Sheets,
    Spreadsheet,
    TextFormat,
    Worksheet,
)
from gsuite_sheets.engine.facade import SheetManager, WorksheetContext
from gsuite_sheets.engine.testing import InMemoryBackend
from gsuite_sheets.engine.testing.google_api_fake import fake_sheets


@pytest.fixture
def backend():
    backend = InMemoryBackend()
    backend.add_spreadsheet(
        "Budget",
        {
            "Data": [["name", "total", "when"], ["Ana", "10", "2026-01-02"], ["Bo", "5", ""]],
            "Q 1": [["x"]],
        },
    )
    return backend


@pytest.fixture
def sheets(backend):
    return fake_sheets(backend.client)


@pytest.fixture
def doc(sheets):
    return sheets.open("Budget")


@pytest.fixture
def ws(doc):
    return doc.worksheet("Data")


def emulator(backend):
    return backend.client.open("Budget")


def request_kinds(backend):
    return [next(iter(r)) for r in emulator(backend).requests]


@dataclass
class Row:
    name: str
    total: int
    when: date | None = None


class TestTables:
    def test_upsert(self, ws):
        result = ws.upsert([{"name": "Ana", "total": 20}, {"name": "Cy", "total": 1}], key="name")

        assert result == {"updated": 1, "appended": 1}
        assert ws.get_all_values()[1][:2] == ["Ana", "20"]
        assert ws.last_row() == 4

    def test_update_and_delete_where(self, ws):
        assert ws.update_where({"name": "Bo"}, {"total": 7}) == 1
        assert ws.delete_where(lambda row: row["name"] == "Ana") == 1
        assert [r[0] for r in ws.get_all_values()] == ["name", "Bo"]

    def test_streaming(self, ws):
        assert list(ws.iter_rows(page_size=1))[1][0] == "Ana"
        assert [r["name"] for r in ws.iter_records(page_size=1)] == ["Ana", "Bo"]

    def test_insert_shifts_rows(self, ws):
        # GSpreadManager's insert(fila=2) appended at the end instead
        ws.insert([["Zed", "0", ""]], row=2)
        assert [r[0] for r in ws.get_all_values()] == ["name", "Zed", "Ana", "Bo"]

    def test_insert_without_row_appends(self, ws):
        ws.insert([["Zed", "0", ""]])
        assert ws.get_all_values()[-1][0] == "Zed"

    def test_update_row_and_find_empty(self, ws):
        ws.update_row(3, ["2026-02-01"], start_column=3)
        assert ws.row_with_empty_in_column("C") == (None, None)

    def test_rows_where(self, ws):
        assert ws.rows_where_column_equals(0, "Bo") == [(3, ["Bo", "5", ""])]

    def test_import_csv(self, ws):
        ws.import_csv(io.StringIO("a,b\n1,2\n"))
        assert ws.get_all_values() == [["a", "b"], ["1", "2"]]

    def test_batch_update_quotes_title(self, doc):
        tab = doc.worksheet("Q 1")
        tab.batch_update([{"range": "A1", "values": [["y"]]}])
        assert tab.get_all_values() == [["y"]]


class TestTypedRows:
    def test_read_as_converts_types(self, ws):
        rows = ws.read_as(Row)
        assert rows[0] == Row(name="Ana", total=10, when=date(2026, 1, 2))
        assert rows[1].when is None

    def test_write_and_upsert_models(self, doc):
        tab = doc.add_worksheet("Models")
        tab.write_models([Row("Ana", 1)])
        tab.append_models([Row("Bo", 2)])
        assert tab.upsert_models([Row("Ana", 3)], key="name") == {"updated": 1, "appended": 0}
        assert [r.total for r in tab.read_as(Row)] == [3, 2]

    def test_ensure_schema_detects_drift(self, doc):
        tab = doc.add_worksheet("Drift")
        tab.append_row(["name", "other"])
        with pytest.raises(SchemaError) as exc_info:
            tab.ensure_schema(Row, strict=True)
        assert set(exc_info.value.missing_columns) == {"total", "when"}


class TestFormattingAndValidation:
    def test_format_accepts_cellformat(self, ws, backend):
        ws.format("A1:C1", CellFormat(text_format=TextFormat(bold=True)))
        repeat = emulator(backend).requests[-1]["repeatCell"]
        assert repeat["cell"]["userEnteredFormat"] == {"textFormat": {"bold": True}}

    def test_format_dict_still_works(self, ws, backend):
        ws.format(["A1", "B1"], {"textFormat": {"italic": True}})
        assert request_kinds(backend) == ["repeatCell", "repeatCell"]

    def test_validation_and_conditional(self, ws, backend):
        ws.add_dropdown("D2:D10", ["ok", "no"])
        ws.add_checkbox("E2:E10")
        ws.add_conditional_format(
            "B2:B10", "NUMBER_LESS", [0], CellFormat(background_color=Color(red=1.0))
        )
        assert request_kinds(backend) == [
            "setDataValidation",
            "setDataValidation",
            "addConditionalFormatRule",
        ]

    def test_text_number_header(self, ws, backend):
        ws.format_header()
        ws.set_text_format("A2:A10", bold=True, color=Color.from_hex("#FF0000"))
        ws.set_number_format("B2:B10", "#,##0.00", "CURRENCY")
        ws.set_background("A1", Color(blue=1.0))
        assert request_kinds(backend).count("repeatCell") == 4

    def test_merge_and_tab_color(self, ws, backend):
        ws.merge("A1:C1")
        ws.unmerge("A1:C1")
        ws.set_tab_color(Color(green=1.0))
        ws.clear_tab_color()
        assert "unmergeCells" in request_kinds(backend)
        assert request_kinds(backend).count("updateSheetProperties") == 2


class TestStructure:
    def test_rows_and_cols(self, ws):
        ws.insert_rows(2, 2)
        assert ws.get_all_values()[1] == []  # the API returns empty rows as []
        ws.delete_rows(2, 3)
        assert ws.get_all_values()[1][0] == "Ana"

    def test_sort_filter_resize_hide(self, ws, backend):
        ws.sort_range("A2:C3", (2, "desc"))
        ws.set_basic_filter()
        ws.clear_basic_filter()
        ws.resize_cols(1, 2, 120)
        ws.hide_rows(3)
        ws.unhide_rows(3)
        kinds = request_kinds(backend)
        assert {
            "sortRange",
            "setBasicFilter",
            "clearBasicFilter",
            "updateDimensionProperties",
        } <= set(kinds)


class TestMetadata:
    def test_notes(self, ws):
        ws.update_note("B2", "check")
        assert ws.get_note("B2") == "check"
        ws.clear_note("B2")
        assert ws.get_note("B2") == ""

    def test_named_and_protected_ranges(self, doc, ws):
        ws.define_named_range("Totals", "B2:B3")
        named = doc.list_named_ranges()
        assert named[0]["name"] == "Totals"
        doc.delete_named_range(named[0]["namedRangeId"])
        assert doc.list_named_ranges() == []

        ws.protect("A1:A3", description="ids")
        (protected,) = ws.list_protected_ranges()
        ws.delete_protected_range(protected["protectedRangeId"])
        assert ws.list_protected_ranges() == []

    def test_developer_metadata(self, doc, backend):
        doc.set_developer_metadata("source", "erp")
        doc.delete_developer_metadata("source")
        assert request_kinds(backend) == ["createDeveloperMetadata", "deleteDeveloperMetadata"]


class TestVisualization:
    def test_chart_pivot_banding(self, ws, backend):
        ws.add_chart("COLUMN", "A1:A3", ["B1:B3"], title="Totals", anchor_cell="E1")
        ws.add_pivot_table("A1:B3", "G1", rows=[1], values=[(2, "SUM")])
        ws.set_banding("A1:C3", first_color=Color(red=1.0), second_color=Color(green=1.0))
        assert {"addChart", "updateCells", "addBanding"} <= set(request_kinds(backend))


class TestSpreadsheet:
    def test_tab_created_elsewhere_is_found(self, doc, backend):
        doc.worksheet("Data").last_row()  # engine caches the tab list
        tab = doc.add_worksheet("New")
        tab.append_row(["x"])
        assert tab.last_row() == 1

    def test_renamed_tab_keeps_working(self, ws):
        ws.last_row()
        ws.rename("Renamed")
        assert ws.last_row() == 3

    def test_worksheet_or_create_and_by_id(self, doc):
        created = doc.worksheet_or_create("Extra")
        assert doc.worksheet_or_create("Extra") is created
        assert doc.worksheet_by_id(created.id) is created

    def test_document_properties(self, doc):
        doc.update_title("Budget 2026")
        doc.update_locale("es_AR")
        doc.update_timezone("America/Argentina/Buenos_Aires")
        assert (doc.title, doc.locale) == ("Budget 2026", "es_AR")

    def test_export(self, doc):
        assert doc.export("csv").startswith(b"name,total,when")
        assert doc.export("pdf").startswith(b"in-memory-export:application/pdf")

    def test_permissions(self, doc):
        doc.share("ana@example.com", role="writer")
        assert doc.list_permissions()[0]["emailAddress"] == "ana@example.com"
        assert len(doc.remove_permission("ana@example.com")) == 1

    def test_copy_and_delete(self, sheets, doc):
        copy = sheets.copy(doc.id, title="Budget copy")
        assert copy.worksheet("Data").get_all_values()[1][0] == "Ana"
        sheets.delete(copy.id)
        assert "Budget copy" not in {f["name"] for f in sheets.list_spreadsheets()}


class TestOptions:
    def test_cache_serves_reads_and_direct_writes_invalidate(self, backend):
        sheets = fake_sheets(backend.client, cache=True)
        ws = sheets.open("Budget").worksheet("Data")
        assert ws.last_row() == 3

        # A change behind the client's back is not seen (cached)...
        emulator(backend).worksheet("Data").append_rows([["Cy", "1", ""]], "RAW")
        assert ws.last_row() == 3
        # ...a write through the client invalidates
        ws.update_cell(1, 1, "name")
        assert ws.last_row() == 4

    def test_polars_backend(self, backend):
        pl = pytest.importorskip("polars")
        ws = (
            fake_sheets(backend.client, dataframe_backend="polars").open("Budget").worksheet("Data")
        )
        df = ws.read_dataframe()
        assert isinstance(df, pl.DataFrame)
        assert df.columns == ["name", "total", "when"]


# Every public operation of GSpreadManager's facade has a home in the public API.
# Left side: GSM name; right side: (gsuite class, name).
SHEET_MANAGER_EQUIVALENTS = {
    "open_by_key": (Sheets, "open_by_key"),
    "open_by_url": (Sheets, "open_by_url"),
    "clear_cache": (Sheets, "clear_cache"),
    "worksheet": (Spreadsheet, "worksheet"),
    "list_worksheets": (Spreadsheet, "worksheets"),
    "worksheet_by_index": (Spreadsheet, "get_worksheet"),
    "worksheet_by_id": (Spreadsheet, "worksheet_by_id"),
    "create_sheet": (Spreadsheet, "add_worksheet"),
    "delete_sheet": (Spreadsheet, "del_worksheet"),
    "worksheet_or_create": (Spreadsheet, "worksheet_or_create"),
    "create_spreadsheet": (Sheets, "create"),
    "delete_spreadsheet": (Sheets, "delete"),
    "copy_spreadsheet": (Sheets, "copy"),
    "list_spreadsheets": (Sheets, "list_spreadsheets"),
    "share": (Spreadsheet, "share"),
    "export": (Spreadsheet, "export"),
}
WORKSHEET_CONTEXT_EQUIVALENTS = {
    "worksheet": None,  # the raw port; not part of the public API
    "read": (Worksheet, "get_all_values"),  # also get_all_records / read_dataframe
    "read_range": (Worksheet, "get"),
    "append": (Worksheet, "append_rows"),
    "format_range": (Worksheet, "format"),
    "add_protected_range": (Worksheet, "protect"),
    "find_replace": (Worksheet, "replace"),
}


def _public(cls: type) -> list[str]:
    return [n for n, _ in inspect.getmembers(cls) if not n.startswith("_") and n != "title"]


def _has(cls: type, name: str) -> bool:
    return hasattr(cls, name) or name in {f.name for f in fields(cls)}


@pytest.mark.parametrize("name", _public(SheetManager))
def test_sheet_manager_parity(name):
    owner, target = SHEET_MANAGER_EQUIVALENTS.get(name, (Spreadsheet, name))
    assert _has(owner, target), (
        f"GSM SheetManager.{name} has no equivalent ({owner.__name__}.{target})"
    )


@pytest.mark.parametrize("name", _public(WorksheetContext))
def test_worksheet_context_parity(name):
    mapped = WORKSHEET_CONTEXT_EQUIVALENTS.get(name, (Worksheet, name))
    if mapped is None:
        return
    owner, target = mapped
    assert _has(owner, target), (
        f"GSM WorksheetContext.{name} has no equivalent ({owner.__name__}.{target})"
    )
