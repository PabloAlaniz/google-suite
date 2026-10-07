"""Tests del Sprint 10 (v3.0): ``AsyncSheetManager`` sobre el backend en memoria async.

Verifican que la facade async cubre el flujo de datos completo (lectura, escritura,
streaming, tabla, modelos, esquema, CSV, documento) reutilizando la lógica pura del
paquete, sin red.
"""

import asyncio
import io
from dataclasses import dataclass
from typing import Any

import pytest
from gspreadmanager import AsyncSheetManager, GSpreadManagerError, WorksheetNotFoundError
from gspreadmanager.testing import AsyncInMemoryBackend


def run(coro: Any) -> Any:
    return asyncio.run(coro)


@dataclass
class Persona:
    id: int
    nombre: str


@pytest.fixture
def backend():
    b = AsyncInMemoryBackend()
    b.add_spreadsheet(
        "Doc",
        {"Tabla": [["id", "nombre"], ["1", "Ana"], ["2", "Luis"]], "Vacia": []},
    )
    return b


@pytest.fixture
def mgr(backend):
    return backend.manager("Doc")


class TestAsyncManager:
    def test_requires_name_or_key(self):
        with pytest.raises(GSpreadManagerError, match="doc_name"):
            AsyncSheetManager()

    def test_read_list_and_dict(self, mgr):
        async def scenario() -> None:
            ws = await mgr.worksheet("Tabla")
            assert await ws.read() == [["id", "nombre"], ["1", "Ana"], ["2", "Luis"]]
            records = await ws.read(output_format="dict", numericise=True)
            assert records == [{"id": 1, "nombre": "Ana"}, {"id": 2, "nombre": "Luis"}]

        run(scenario())

    def test_pandas_output_rejected(self, mgr):
        async def scenario() -> None:
            ws = await mgr.worksheet("Tabla")
            with pytest.raises(GSpreadManagerError, match="pandas"):
                await ws.read(output_format="pandas")

        run(scenario())

    def test_append_update_clear_find(self, mgr):
        async def scenario() -> None:
            ws = await mgr.worksheet("Tabla")
            await ws.append([["3", "Eva"]])
            await ws.update_cell(2, 2, "Ana María")
            rows = await ws.read()
            assert rows[-1] == ["3", "Eva"]
            assert rows[1][1] == "Ana María"
            celda = await ws.find("Eva")
            assert celda.row == 4
            await ws.clear()
            assert await ws.read() == []

        run(scenario())

    def test_worksheet_or_create_and_listing(self, mgr):
        async def scenario() -> None:
            ws = await mgr.worksheet_or_create("Nueva")
            assert ws.title == "Nueva"
            titles = [p["title"] for p in await mgr.list_worksheets()]
            assert titles == ["Tabla", "Vacia", "Nueva"]
            with pytest.raises(WorksheetNotFoundError):
                await mgr.worksheet("NoExiste")

        run(scenario())

    def test_document_operations(self, backend, mgr):
        async def scenario() -> None:
            await mgr.update_title("Renombrado")
            await mgr.share("x@y.com", role="writer")
            permisos = await mgr.list_permissions()
            assert permisos
            assert permisos[0]["emailAddress"] == "x@y.com"

        run(scenario())
        requests = backend.client.spreadsheet_by_key("doc0").requests
        assert {"updateSpreadsheetProperties": {"properties": {"title": "Renombrado"}, "fields": "title"}} in requests


class TestAsyncStreamingAndTable:
    def test_iter_rows_and_records(self, mgr):
        async def scenario() -> None:
            ws = await mgr.worksheet("Tabla")
            rows = [row async for row in ws.iter_rows(page_size=1)]
            assert rows == [["id", "nombre"], ["1", "Ana"], ["2", "Luis"]]
            records = [r async for r in ws.iter_records(page_size=1)]
            assert records[0] == {"id": "1", "nombre": "Ana"}

        run(scenario())

    def test_iter_as_models(self, mgr):
        async def scenario() -> None:
            ws = await mgr.worksheet("Tabla")
            personas = [p async for p in ws.iter_as(Persona, page_size=1)]
            assert personas == [Persona(1, "Ana"), Persona(2, "Luis")]

        run(scenario())

    def test_upsert_and_where(self, mgr):
        async def scenario() -> None:
            ws = await mgr.worksheet("Tabla")
            result = await ws.upsert(
                [{"id": "2", "nombre": "Luisa"}, {"id": "9", "nombre": "Nuevo"}], key="id"
            )
            assert result == {"updated": 1, "appended": 1}
            count = await ws.update_where({"nombre": "Luisa"}, {"nombre": "L."})
            assert count == 1
            deleted = await ws.delete_where(lambda r: r["id"] == "9")
            assert deleted == 1
            assert [r[0] for r in await ws.read()] == ["id", "1", "2"]

        run(scenario())

    def test_upsert_models(self, mgr):
        async def scenario() -> None:
            ws = await mgr.worksheet("Tabla")
            result = await ws.upsert_models([Persona(1, "Ana B."), Persona(7, "Zoe")], key="id")
            assert result == {"updated": 1, "appended": 1}
            assert (await ws.read())[1] == ["1", "Ana B."]

        run(scenario())


class TestAsyncModelsAndCsv:
    def test_read_write_models_and_schema(self, mgr):
        async def scenario() -> None:
            ws = await mgr.worksheet("Vacia")
            creado = await ws.ensure_schema(Persona)
            assert creado == {"created": True, "missing": [], "extra": []}
            await ws.append_models([Persona(1, "Ana")])
            personas = await ws.read_as(Persona)
            assert personas == [Persona(1, "Ana")]
            await ws.write_models([Persona(5, "Eva")])
            assert await ws.read() == [["id", "nombre"], ["5", "Eva"]]

        run(scenario())

    def test_import_csv_and_find_replace(self, mgr):
        async def scenario() -> None:
            ws = await mgr.worksheet("Tabla")
            await ws.import_csv(io.StringIO("col\nuno\ndos"))
            assert await ws.read() == [["col"], ["uno"], ["dos"]]
            await ws.find_replace("uno", "UNO")
            assert (await ws.read())[1] == ["UNO"]

        run(scenario())

    def test_copy_to_other_document(self, backend, mgr):
        backend.add_spreadsheet("Destino", {"Base": [["b"]]})  # se registra como doc1

        async def scenario() -> None:
            ws = await mgr.worksheet("Tabla")
            result = await ws.copy_to("doc1")
            assert result["title"] == "Copia de Tabla"

        run(scenario())
        destino = backend.client.spreadsheet_by_key("doc1")
        assert [w.title for w in destino.worksheets] == ["Base", "Copia de Tabla"]

    def test_chunked_append(self, backend):
        mgr = backend.manager("Doc", batch_cell_limit=2)

        async def scenario() -> None:
            ws = await mgr.worksheet("Tabla")
            results = await ws.append([["a", "b"]] * 3)  # 6 celdas -> 3 chunks
            assert isinstance(results, list)
            assert len(results) == 3
            assert len(await ws.read()) == 3 + 3

        run(scenario())
