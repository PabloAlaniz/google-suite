"""Tests del backend en memoria (``gspreadmanager.testing``) vía el API público."""

import pytest
from gspreadmanager import Color, ExportFormat, GSpreadManagerError, SheetManager
from gspreadmanager.testing import InMemoryBackend, InMemoryClient, InMemorySpreadsheet


@pytest.fixture
def backend():
    b = InMemoryBackend()
    b.add_spreadsheet("MiDoc", {"Hoja1": [["nombre", "email"], ["Ana", "ana@x.com"]]})
    return b


@pytest.fixture
def mgr(backend):
    return backend.manager("MiDoc")


class TestRoundTrip:
    def test_read_list_and_dict(self, mgr):
        ws = mgr.worksheet("Hoja1")
        assert ws.read() == [["nombre", "email"], ["Ana", "ana@x.com"]]
        assert ws.read(output_format="dict") == [{"nombre": "Ana", "email": "ana@x.com"}]

    def test_append_then_read(self, mgr):
        ws = mgr.worksheet("Hoja1")
        ws.append([["Bob", "bob@x.com"]])
        assert ws.read()[-1] == ["Bob", "bob@x.com"]
        assert ws.last_row() == 3

    def test_update_cell_and_row(self, mgr):
        ws = mgr.worksheet("Hoja1")
        ws.update_cell(2, 1, "Ana2")
        ws.update_row(2, ["Cora", "cora@x.com"])
        assert ws.read()[1] == ["Cora", "cora@x.com"]

    def test_clear(self, mgr):
        ws = mgr.worksheet("Hoja1")
        ws.clear()
        assert ws.read() == []

    def test_clear_range(self, mgr):
        ws = mgr.worksheet("Hoja1")
        ws.clear("A2:B2")
        assert ws.read() == [["nombre", "email"]]

    def test_rows_where_column_equals(self, mgr):
        ws = mgr.worksheet("Hoja1")
        ws.append([["Ana", "otra@x.com"]])
        assert ws.rows_where_column_equals(0, "Ana") == [
            (2, ["Ana", "ana@x.com"]),
            (3, ["Ana", "otra@x.com"]),
        ]

    def test_row_with_empty_in_column(self, mgr):
        ws = mgr.worksheet("Hoja1")
        ws.update_cell(3, 2, "solo-col-b")
        row, index = ws.row_with_empty_in_column("A")
        assert index == 3
        assert row == ["", "solo-col-b"]

    def test_find(self, mgr):
        cell = mgr.worksheet("Hoja1").find("Ana")
        assert (cell.row, cell.col, cell.value) == (2, 1, "Ana")

    def test_find_missing_returns_none(self, mgr):
        assert mgr.worksheet("Hoja1").find("zzz") is None

    def test_read_range(self, mgr):
        rows = mgr.worksheet("Hoja1").read_range(1, 2, "A", "B")
        assert rows == [
            {"fila": 1, "values": ["nombre", "email"]},
            {"fila": 2, "values": ["Ana", "ana@x.com"]},
        ]

    def test_default_worksheet_is_sheet1(self, mgr):
        assert mgr.worksheet().title == "Hoja1"


class TestStructural:
    def test_insert_and_delete_rows_shift_grid(self, mgr):
        ws = mgr.worksheet("Hoja1")
        ws.insert_rows(2, 1)
        assert ws.read() == [["nombre", "email"], ["", ""], ["Ana", "ana@x.com"]]
        ws.delete_rows(2)
        assert ws.read() == [["nombre", "email"], ["Ana", "ana@x.com"]]

    def test_insert_cols_shift_grid(self, mgr):
        ws = mgr.worksheet("Hoja1")
        ws.insert_cols(1, 1)
        assert ws.read()[0] == ["", "nombre", "email"]

    def test_anchored_write(self, mgr):
        ws = mgr.worksheet("Hoja1")
        ws.batch_update([{"range": "Hoja1!D1", "values": [["x"]]}])
        assert ws.read()[0][3] == "x"

    def test_create_and_delete_sheet(self, mgr):
        mgr.create_sheet("Otra", rows=5, cols=3)
        assert mgr.worksheet("Otra").title == "Otra"
        mgr.delete_sheet("Otra")
        with pytest.raises(GSpreadManagerError, match="Otra"):
            mgr.worksheet("Otra")


class TestNotesAndRanges:
    def test_note_round_trip(self, mgr):
        ws = mgr.worksheet("Hoja1")
        ws.update_note("A1", "revisar")
        assert ws.get_note("A1") == "revisar"
        ws.clear_note("A1")
        assert ws.get_note("A1") == ""

    def test_named_range_round_trip(self, mgr):
        ws = mgr.worksheet("Hoja1")
        ws.define_named_range("Datos", "A1:B2")
        named = mgr.list_named_ranges()
        assert named[0]["name"] == "Datos"
        mgr.delete_named_range(named[0]["namedRangeId"])
        assert mgr.list_named_ranges() == []

    def test_protected_range_round_trip(self, mgr):
        ws = mgr.worksheet("Hoja1")
        ws.add_protected_range("A1:A2", description="solo lectura")
        protected = ws.list_protected_ranges()
        assert protected[0]["description"] == "solo lectura"
        ws.delete_protected_range(protected[0]["protectedRangeId"])
        assert ws.list_protected_ranges() == []


class TestCapturedRequests:
    def test_formatting_and_sort_are_logged_not_applied(self, backend, mgr):
        ws = mgr.worksheet("Hoja1")
        ws.set_background("A1", Color(red=1.0))
        ws.sort_range("A2:B2", (1, "asc"))
        ws.set_tab_color(Color(red=0.5))
        ss = backend.client.open("MiDoc")
        kinds = {next(iter(r)) for r in ss.requests}
        assert "sortRange" in kinds
        assert "updateSheetProperties" in kinds
        assert any("format" in r for r in ss.requests)


class TestDocumentAndDataframe:
    def test_export_csv(self, mgr):
        assert mgr.export(ExportFormat.CSV) == b"nombre,email\nAna,ana@x.com"

    def test_export_other_format_is_placeholder(self, mgr):
        assert mgr.export(ExportFormat.PDF).startswith(b"in-memory-export:")

    def test_share_and_permissions(self, mgr):
        mgr.share("x@y.com", role="writer")
        assert mgr.list_permissions()[0]["emailAddress"] == "x@y.com"
        removed = mgr.remove_permission("x@y.com", role="writer")
        assert len(removed) == 1
        assert mgr.list_permissions() == []

    def test_dataframe_round_trip(self, mgr):
        ws = mgr.worksheet("Hoja1")
        df = ws.read_dataframe()
        assert list(df.columns) == ["nombre", "email"]
        ws.write_dataframe(df, start_cell="D1", clear=False)
        assert ws.read()[0][3:] == ["nombre", "email"]

    def test_create_copy_delete_spreadsheet(self, mgr):
        created = mgr.create_spreadsheet("Nuevo")
        assert {"id": created.id, "name": "Nuevo"} in mgr.list_spreadsheets()
        mgr.copy_spreadsheet(created.id, title="Copia")
        names = {f["name"] for f in mgr.list_spreadsheets()}
        assert {"Nuevo", "Copia"} <= names
        mgr.delete_spreadsheet(created.id)
        assert "Nuevo" not in {f["name"] for f in mgr.list_spreadsheets()}


class TestWiringAndErrors:
    def test_open_unknown_doc_raises(self):
        mgr = SheetManager("Inexistente", sheets_client=InMemoryClient())
        with pytest.raises(GSpreadManagerError, match="No se encontró"):
            mgr.worksheet("Hoja1")

    def test_open_by_key(self):
        client = InMemoryClient()
        ss = InMemorySpreadsheet("Doc", "KEY1")
        ss.seed("Hoja1", [["a"]])
        client.register(ss)
        mgr = SheetManager.open_by_key("KEY1", sheets_client=client)
        assert mgr.worksheet("Hoja1").read() == [["a"]]

    def test_handles_are_independent(self, backend):
        backend.add_spreadsheet("Otro", {"H": [["z"]]})
        mgr = backend.manager("MiDoc")
        other = backend.manager("Otro")
        mgr.worksheet("Hoja1").append([["new", "row"]])
        assert other.worksheet("H").read() == [["z"]]
