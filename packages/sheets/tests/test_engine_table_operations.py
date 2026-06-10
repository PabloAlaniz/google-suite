"""Tests de las operaciones de alto nivel del Sprint 5 (v2.4): la hoja como tabla.

Cubren upsert (dicts, listas y modelos), update_where/delete_where (filtros y predicados),
worksheet_or_create y el chunking automático de escrituras, todo sobre el backend en memoria.
"""

from dataclasses import dataclass

import pytest
from gspreadmanager import GSpreadManagerError
from gspreadmanager.domain.batching import split_range_data, split_rows
from gspreadmanager.testing import InMemoryBackend

HEADER = ["id", "nombre", "estado"]
DATA = [
    ["1", "Ana", "pendiente"],
    ["2", "Luis", "hecho"],
    ["3", "Eva", "pendiente"],
]


@pytest.fixture
def backend():
    b = InMemoryBackend()
    b.add_spreadsheet("MiDoc", {"Tabla": [HEADER, *DATA], "Vacia": []})
    return b


@pytest.fixture
def ws(backend):
    return backend.manager("MiDoc").worksheet("Tabla")


class TestUpsert:
    def test_updates_existing_and_appends_new(self, ws):
        result = ws.upsert(
            [
                {"id": "2", "nombre": "Luisa", "estado": "revisado"},
                {"id": "9", "nombre": "Nuevo", "estado": "pendiente"},
            ],
            key="id",
        )
        assert result == {"updated": 1, "appended": 1}
        rows = ws.read()
        assert rows[2] == ["2", "Luisa", "revisado"]
        assert rows[-1] == ["9", "Nuevo", "pendiente"]

    def test_partial_dict_updates_only_given_columns(self, ws):
        ws.upsert([{"id": "1", "estado": "hecho"}], key="id")
        assert ws.read()[1] == ["1", "Ana", "hecho"]  # nombre intacto

    def test_list_rows_aligned_to_header(self, ws):
        result = ws.upsert([["3", "Eva María", "hecho"]], key="id")
        assert result == {"updated": 1, "appended": 0}
        assert ws.read()[3] == ["3", "Eva María", "hecho"]

    def test_new_keys_deduplicated_last_wins(self, ws):
        result = ws.upsert(
            [{"id": "7", "nombre": "a"}, {"id": "7", "nombre": "b"}], key="id"
        )
        assert result["appended"] == 1
        assert ws.read()[-1][1] == "b"

    def test_missing_key_column_in_row_raises(self, ws):
        with pytest.raises(GSpreadManagerError, match="columna clave"):
            ws.upsert([{"nombre": "sin id"}], key="id")

    def test_unknown_key_column_raises(self, ws):
        with pytest.raises(GSpreadManagerError, match="no está en el encabezado"):
            ws.upsert([{"id": "1"}], key="uuid")

    def test_empty_sheet_raises(self, backend):
        ws = backend.manager("MiDoc").worksheet("Vacia")
        with pytest.raises(GSpreadManagerError, match="encabezado"):
            ws.upsert([{"id": "1"}], key="id")

    def test_upsert_is_idempotent(self, ws):
        rows = [{"id": "2", "estado": "x"}, {"id": "9", "nombre": "n", "estado": "y"}]
        ws.upsert(rows, key="id")
        result = ws.upsert(rows, key="id")
        assert result == {"updated": 2, "appended": 0}


class TestUpsertModels:
    def test_upserts_dataclasses_by_key(self, ws):
        @dataclass
        class Fila:
            id: int
            nombre: str
            estado: str

        result = ws.upsert_models(
            [Fila(2, "Luisa", "ok"), Fila(10, "Diego", "pendiente")], key="id"
        )
        assert result == {"updated": 1, "appended": 1}
        rows = ws.read()
        assert rows[2] == ["2", "Luisa", "ok"]
        assert rows[-1] == ["10", "Diego", "pendiente"]


class TestUpdateWhere:
    def test_dict_filter_updates_matching_rows(self, ws):
        count = ws.update_where({"estado": "pendiente"}, {"estado": "en curso"})
        assert count == 2
        rows = ws.read(output_format="dict")
        assert [r["estado"] for r in rows] == ["en curso", "hecho", "en curso"]

    def test_callable_predicate(self, ws):
        count = ws.update_where(lambda r: r["nombre"].startswith("L"), {"estado": "vip"})
        assert count == 1
        assert ws.read()[2][2] == "vip"

    def test_unknown_update_column_raises(self, ws):
        with pytest.raises(GSpreadManagerError, match="no está en el encabezado"):
            ws.update_where({"estado": "pendiente"}, {"prioridad": "alta"})

    def test_no_matches_returns_zero(self, ws):
        assert ws.update_where({"estado": "inexistente"}, {"estado": "x"}) == 0


class TestDeleteWhere:
    def test_deletes_matching_rows_and_shifts(self, ws):
        count = ws.delete_where({"estado": "pendiente"})
        assert count == 2
        assert ws.read() == [HEADER, ["2", "Luis", "hecho"]]

    def test_deletes_contiguous_block(self, ws):
        ws.append([["4", "Zoe", "pendiente"]])
        count = ws.delete_where(lambda r: r["id"] in {"2", "3"})
        assert count == 2
        assert [r[0] for r in ws.read()[1:]] == ["1", "4"]

    def test_no_matches_deletes_nothing(self, ws):
        assert ws.delete_where({"id": "99"}) == 0
        assert len(ws.read()) == 4


class TestWorksheetOrCreate:
    def test_returns_existing_sheet(self, backend):
        mgr = backend.manager("MiDoc")
        ws = mgr.worksheet_or_create("Tabla")
        assert ws.title == "Tabla"
        assert len(mgr.list_worksheets()) == 2

    def test_creates_missing_sheet(self, backend):
        mgr = backend.manager("MiDoc")
        ws = mgr.worksheet_or_create("Reporte")
        assert ws.title == "Reporte"
        assert [p["title"] for p in mgr.list_worksheets()] == ["Tabla", "Vacia", "Reporte"]


class TestBatchingDomain:
    def test_split_rows_respects_cell_budget(self):
        rows = [["a", "b"]] * 5  # 10 celdas
        chunks = split_rows(rows, 4)
        assert [len(c) for c in chunks] == [2, 2, 1]

    def test_split_rows_never_splits_one_row(self):
        rows = [["x"] * 10]
        assert split_rows(rows, 3) == [rows]

    def test_split_rows_none_disables(self):
        rows = [["a"]] * 100
        assert split_rows(rows, None) == [rows]

    def test_split_range_data_groups_by_cells(self):
        items = [{"range": f"A{i}", "values": [["x", "y"]]} for i in range(1, 5)]  # 2 c/u
        chunks = split_range_data(items, 4)
        assert [len(c) for c in chunks] == [2, 2]

    def test_split_range_data_within_budget_single_chunk(self):
        items = [{"range": "A1", "values": [["x"]]}]
        assert split_range_data(items, 100) == [items]


class TestFacadeChunking:
    def test_append_chunks_and_returns_list(self, backend):
        mgr = backend.manager("MiDoc", batch_cell_limit=6)
        ws = mgr.worksheet("Tabla")
        results = ws.append([["a", "b", "c"]] * 4)  # 12 celdas -> 2 chunks
        assert isinstance(results, list)
        assert len(results) == 2
        assert len(ws.read()) == 4 + 4  # 4 previas + 4 nuevas

    def test_append_small_returns_single_response(self, ws):
        result = ws.append([["x", "y", "z"]])
        assert isinstance(result, dict)

    def test_batch_update_chunks_apply_all(self, backend):
        mgr = backend.manager("MiDoc", batch_cell_limit=1)
        ws = mgr.worksheet("Tabla")
        ws.batch_update(
            [
                {"range": "B2", "values": [["AnaMod"]]},
                {"range": "B3", "values": [["LuisMod"]]},
            ]
        )
        rows = ws.read()
        assert rows[1][1] == "AnaMod"
        assert rows[2][1] == "LuisMod"
