"""Tests de la caché de lecturas con invalidación (``infrastructure.cache``)."""

import pandas as pd
import pytest
from gspreadmanager import CellFormat, Color, ExportFormat, SheetManager
from gspreadmanager.testing import InMemoryBackend


@pytest.fixture
def seeded():
    backend = InMemoryBackend()
    ss = backend.add_spreadsheet("Doc", {"H": [["a", "b"], ["1", "2"]]})
    return backend, ss


class TestReadCache:
    def test_reads_are_cached_until_write(self, seeded):
        backend, ss = seeded
        mgr = SheetManager("Doc", sheets_client=backend.client, cache=True)
        ws = mgr.worksheet("H")
        assert ws.read() == [["a", "b"], ["1", "2"]]

        # Mutación directa de la grilla (saltea la caché): la lectura sigue sirviendo lo viejo.
        ss.worksheets[0].grid.set(2, 1, "MUT")
        assert ws.read() == [["a", "b"], ["1", "2"]]

    def test_write_invalidates(self, seeded):
        backend, ss = seeded
        mgr = SheetManager("Doc", sheets_client=backend.client, cache=True)
        ws = mgr.worksheet("H")
        ws.read()  # cachea
        ss.worksheets[0].grid.set(2, 2, "MUT")  # cambio externo
        ws.update_cell(1, 1, "Z")  # escritura propia -> invalida
        assert ws.read() == [["Z", "b"], ["1", "MUT"]]

    def test_append_invalidates(self, seeded):
        backend, _ = seeded
        mgr = SheetManager("Doc", sheets_client=backend.client, cache=True)
        ws = mgr.worksheet("H")
        ws.read()
        ws.append([["3", "4"]])
        assert ws.read()[-1] == ["3", "4"]

    def test_clear_cache_forces_refresh(self, seeded):
        backend, ss = seeded
        mgr = SheetManager("Doc", sheets_client=backend.client, cache=True)
        ws = mgr.worksheet("H")
        ws.read()
        ss.worksheets[0].grid.set(1, 1, "EXT")
        assert ws.read()[0][0] == "a"  # aún cacheado
        mgr.clear_cache()
        assert ws.read()[0][0] == "EXT"

    def test_cache_shared_across_worksheet_handles(self, seeded):
        backend, ss = seeded
        mgr = SheetManager("Doc", sheets_client=backend.client, cache=True)
        mgr.worksheet("H").read()  # cachea con un handle
        ss.worksheets[0].grid.set(1, 1, "EXT")
        # Otro handle del mismo doc comparte la caché -> sigue viendo lo viejo
        assert mgr.worksheet("H").read()[0][0] == "a"

    def test_document_write_invalidates_worksheet_read(self, seeded):
        backend, ss = seeded
        mgr = SheetManager("Doc", sheets_client=backend.client, cache=True)
        ws = mgr.worksheet("H")
        ws.read()
        ss.worksheets[0].grid.set(3, 1, "row3")
        # Escritura ruteada por el documento (insert_rows -> spreadsheet.batch_update) invalida.
        ws.insert_rows(1, 1)
        assert ws.read()[-1] == ["row3", ""]


class TestNoCache:
    def test_disabled_by_default(self, seeded):
        backend, ss = seeded
        mgr = SheetManager("Doc", sheets_client=backend.client)
        ws = mgr.worksheet("H")
        ws.read()
        ss.worksheets[0].grid.set(1, 1, "EXT")
        assert ws.read()[0][0] == "EXT"  # sin caché: siempre fresco

    def test_clear_cache_is_noop_without_cache(self, seeded):
        backend, _ = seeded
        SheetManager("Doc", sheets_client=backend.client).clear_cache()


class TestDelegationThroughCache:
    """Ejercita los pasa-directo de los wrappers con ``cache=True`` (sin romper nada)."""

    @pytest.fixture
    def mgr(self):
        backend = InMemoryBackend()
        backend.add_spreadsheet("Doc", {"H": [["a", "b"], ["1", "2"]]})
        self.color = Color(red=1.0)
        self.cell_format = CellFormat(background_color=self.color)
        return SheetManager("Doc", sheets_client=backend.client, cache=True)

    def test_worksheet_read_paths(self, mgr):
        ws = mgr.worksheet("H")
        assert ws.read_range(1, 1, "A", "B") == [{"fila": 1, "values": ["a", "b"]}]
        assert ws.find("1").value == "1"
        assert ws.row_with_empty_in_column("A")[1] is None

    def test_worksheet_write_paths(self, mgr):
        ws = mgr.worksheet("H")
        ws.set_background("A1", self.color)
        ws.freeze(rows=1)
        ws.merge("A1:B1")
        ws.batch_update([{"range": "A3", "values": [["x"]]}])
        assert ws.read()[2][0] == "x"

    def test_sheet_lifecycle(self, mgr):
        mgr.create_sheet("Nueva")
        assert mgr.worksheet("Nueva").title == "Nueva"
        mgr.delete_sheet("Nueva")

    def test_default_sheet1(self, mgr):
        assert mgr.worksheet().title == "H"

    def test_document_and_sharing(self, mgr):
        created = mgr.create_spreadsheet("Otro")
        assert any(f["name"] == "Otro" for f in mgr.list_spreadsheets())
        mgr.copy_spreadsheet(created.id, title="Copia")
        mgr.delete_spreadsheet(created.id)
        mgr.share("x@y.com", role="writer")
        assert mgr.list_permissions()[0]["emailAddress"] == "x@y.com"
        assert mgr.remove_permission("x@y.com", role="writer") != []

    def test_export(self, mgr):
        assert mgr.export(ExportFormat.CSV) == b"a,b\n1,2"

    def test_clear_and_insert_and_anchor(self, mgr):
        ws = mgr.worksheet("H")
        ws.insert([["9", "9"]], fila=3)  # values_append
        assert ws.read()[2] == ["9", "9"]
        ws.batch_update([{"range": "D1", "values": [["k"]]}])
        ws.clear("D1:D1")  # batch_clear
        assert ws.read()[0][:2] == ["a", "b"]
        ws.clear()  # clear whole sheet
        assert ws.read() == []

    def test_row_values_via_empty_lookup(self, mgr):
        ws = mgr.worksheet("H")
        ws.update_cell(3, 2, "solo-b")  # A3 vacío, B3 con dato
        row, index = ws.row_with_empty_in_column("A")
        assert index == 3
        assert row == ["", "solo-b"]

    def test_write_dataframe_anchor(self, mgr):
        ws = mgr.worksheet("H")
        ws.write_dataframe(pd.DataFrame([["z"]], columns=["c"]), clear=False, start_cell="E1")
        assert ws.read()[0][4] == "c"


class TestMetadataCache:
    def test_metadata_read_cached_and_invalidated(self, seeded):
        backend, _ = seeded
        mgr = SheetManager("Doc", sheets_client=backend.client, cache=True)
        ws = mgr.worksheet("H")
        ws.define_named_range("R1", "A1:B1")
        assert len(mgr.list_named_ranges()) == 1
        # Otra escritura (named range) invalida la metadata cacheada.
        ws.define_named_range("R2", "A2:B2")
        assert len(mgr.list_named_ranges()) == 2
