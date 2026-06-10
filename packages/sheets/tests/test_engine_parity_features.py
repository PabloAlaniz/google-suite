"""Tests de las features de paridad del Sprint 4 (v2.3), sobre el backend en memoria.

Cubren: import CSV, propiedades del documento (title/locale/timezone), listado y apertura
de pestañas por índice/id, find/replace y copy_to entre documentos. Los render options se
prueban contra los adaptadores (el fake no modela fórmulas).
"""

import io

import pytest
from gspreadmanager import GSpreadManagerError, SpreadsheetNotFoundError, WorksheetNotFoundError
from gspreadmanager.domain.csv_data import rows_from_csv
from gspreadmanager.testing import InMemoryBackend


@pytest.fixture
def backend():
    b = InMemoryBackend()
    b.add_spreadsheet(
        "MiDoc", {"Hoja1": [["nombre", "email"], ["Ana", "ana@x.com"]], "Hoja2": [["z"]]}
    )
    return b


@pytest.fixture
def mgr(backend):
    return backend.manager("MiDoc")


class TestRowsFromCsv:
    def test_parses_quotes_and_embedded_delimiters(self):
        text = 'a,b\n"x, con coma","línea\npartida"\n'
        assert rows_from_csv(text) == [["a", "b"], ["x, con coma", "línea\npartida"]]

    def test_custom_delimiter(self):
        assert rows_from_csv("a;b\n1;2", delimiter=";") == [["a", "b"], ["1", "2"]]


class TestImportCsv:
    def test_import_from_file_like_clears_and_writes(self, mgr):
        ws = mgr.worksheet("Hoja1")
        ws.import_csv(io.StringIO("col\nvalor1\nvalor2"))
        assert ws.read() == [["col"], ["valor1"], ["valor2"]]

    def test_import_without_clear_overlays(self, mgr):
        ws = mgr.worksheet("Hoja1")
        ws.import_csv(io.StringIO("x"), clear=False)
        # Sobrescribe A1 pero conserva el resto de la fila/hoja.
        assert ws.read()[0] == ["x", "email"]

    def test_import_from_path(self, mgr, tmp_path):
        csv_file = tmp_path / "datos.csv"
        csv_file.write_text("a,b\n1,2", encoding="utf-8")
        ws = mgr.worksheet("Hoja1")
        ws.import_csv(csv_file)
        assert ws.read() == [["a", "b"], ["1", "2"]]


class TestDocumentProperties:
    def test_update_title_locale_timezone_send_requests(self, backend, mgr):
        mgr.update_title("Nuevo nombre")
        mgr.update_locale("es_AR")
        mgr.update_timezone("America/Argentina/Buenos_Aires")

        requests = backend.client.spreadsheet_by_key("doc0").requests
        updates = [r["updateSpreadsheetProperties"] for r in requests]
        assert {"properties": {"title": "Nuevo nombre"}, "fields": "title"} in updates
        assert {"properties": {"locale": "es_AR"}, "fields": "locale"} in updates
        assert {
            "properties": {"timeZone": "America/Argentina/Buenos_Aires"},
            "fields": "timeZone",
        } in updates


class TestWorksheetListing:
    def test_list_worksheets_returns_properties(self, mgr):
        props = mgr.list_worksheets()
        assert [p["title"] for p in props] == ["Hoja1", "Hoja2"]
        assert props[0]["index"] == 0
        assert "sheetId" in props[0]

    def test_worksheet_by_index(self, mgr):
        assert mgr.worksheet_by_index(1).title == "Hoja2"

    def test_worksheet_by_id(self, mgr):
        sheet_id = mgr.list_worksheets()[1]["sheetId"]
        assert mgr.worksheet_by_id(sheet_id).title == "Hoja2"

    def test_missing_index_and_id_raise(self, mgr):
        with pytest.raises(WorksheetNotFoundError):
            mgr.worksheet_by_index(99)
        with pytest.raises(WorksheetNotFoundError):
            mgr.worksheet_by_id(999)


class TestFindReplace:
    def test_replaces_substring_case_insensitive_by_default(self, mgr):
        ws = mgr.worksheet("Hoja1")
        ws.find_replace("ANA", "Luisa")
        assert ws.read()[1][0] == "Luisa"

    def test_match_case(self, mgr):
        ws = mgr.worksheet("Hoja1")
        ws.find_replace("ANA", "Luisa", match_case=True)
        assert ws.read()[1][0] == "Ana"  # sin cambios

    def test_match_entire_cell(self, mgr):
        ws = mgr.worksheet("Hoja1")
        ws.find_replace("ana", "x", match_entire_cell=True)
        # 'Ana' matchea entera (case-insensitive); 'ana@x.com' no.
        assert ws.read()[1] == ["x", "ana@x.com"]


class TestCopyTo:
    def test_copies_sheet_with_data_to_other_document(self, backend, mgr):
        backend.add_spreadsheet("Destino", {"Base": [["b"]]})
        destino_key = backend.client.spreadsheet_by_key("doc1").id

        result = mgr.worksheet("Hoja1").copy_to(destino_key)

        assert result["title"] == "Copia de Hoja1"
        dest_mgr = backend.manager("Destino")
        assert dest_mgr.worksheet("Copia de Hoja1").read() == [
            ["nombre", "email"],
            ["Ana", "ana@x.com"],
        ]

    def test_copy_to_unknown_document_raises(self, mgr):
        with pytest.raises(SpreadsheetNotFoundError):
            mgr.worksheet("Hoja1").copy_to("inexistente")


class TestRenderOptions:
    def test_invalid_render_raises(self, mgr):
        with pytest.raises(GSpreadManagerError, match="render inválido"):
            mgr.worksheet("Hoja1").read(render="raw")

    def test_render_accepted_by_in_memory(self, mgr):
        # El fake acepta el parámetro por contrato (y devuelve el valor almacenado).
        assert mgr.worksheet("Hoja1").read(render="formula")[0] == ["nombre", "email"]
