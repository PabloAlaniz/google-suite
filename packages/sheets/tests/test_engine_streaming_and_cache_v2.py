"""Tests del Sprint 6 (v2.5): streaming para hojas grandes y caché v2.

Cubren ``iter_rows``/``iter_records``/``iter_as`` (paginación perezosa) y la caché con
TTL, límite LRU e invalidación selectiva por hoja/rango.
"""

from dataclasses import dataclass
from typing import Any

import pytest
from gspreadmanager import GSpreadManagerError, SheetManager
from gspreadmanager.infrastructure.cache import _Cache
from gspreadmanager.testing import InMemoryBackend

ROWS = [["id", "nombre"]] + [[str(i), f"p{i}"] for i in range(1, 6)]  # encabezado + 5 filas


@pytest.fixture
def backend():
    b = InMemoryBackend()
    b.add_spreadsheet("Doc", {"H": ROWS, "Otra": [["x"], ["y"]]})
    return b


@pytest.fixture
def mgr(backend):
    return backend.manager("Doc")


def count_pages(backend: InMemoryBackend, monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Instala un contador de llamadas a values_get sobre el documento en memoria."""
    ss = backend.client.spreadsheet_by_key("doc0")
    calls: list[str] = []
    original = ss.values_get

    def spy(a1_range: str) -> Any:
        calls.append(a1_range)
        return original(a1_range)

    monkeypatch.setattr(ss, "values_get", spy)
    return calls


class TestIterRows:
    def test_yields_all_rows_across_pages(self, mgr):
        rows = list(mgr.worksheet("H").iter_rows(page_size=2))
        assert rows == ROWS

    def test_is_lazy_one_request_per_page(self, backend, mgr, monkeypatch):
        calls = count_pages(backend, monkeypatch)
        iterator = mgr.worksheet("H").iter_rows(page_size=2)
        assert calls == []  # nada hasta consumir
        next(iterator)
        assert len(calls) == 1
        list(iterator)
        # 6 filas en páginas de 2: 3 páginas llenas + 1 vacía para detectar el final.
        assert len(calls) == 4

    def test_skiprows(self, mgr):
        rows = list(mgr.worksheet("H").iter_rows(page_size=10, skiprows=1))
        assert rows == ROWS[1:]

    def test_empty_sheet_yields_nothing(self, backend, mgr):
        backend.client.spreadsheet_by_key("doc0").seed("Vacia")
        assert list(mgr.worksheet("Vacia").iter_rows()) == []

    def test_invalid_page_size_raises(self, mgr):
        with pytest.raises(GSpreadManagerError, match="page_size"):
            list(mgr.worksheet("H").iter_rows(page_size=0))


class TestIterRecords:
    def test_maps_header_to_dicts(self, mgr):
        records = list(mgr.worksheet("H").iter_records(page_size=2))
        assert records[0] == {"id": "1", "nombre": "p1"}
        assert len(records) == 5

    def test_pads_short_rows(self, backend, mgr):
        backend.client.spreadsheet_by_key("doc0").seed("Corta", [["a", "b"], ["1"]])
        records = list(mgr.worksheet("Corta").iter_records())
        assert records == [{"a": "1", "b": ""}]


class TestIterAs:
    def test_yields_models_per_page(self, mgr):
        @dataclass
        class Persona:
            id: int
            nombre: str

        personas = list(mgr.worksheet("H").iter_as(Persona, page_size=2))
        assert len(personas) == 5
        assert personas[0] == Persona(1, "p1")
        assert personas[-1].id == 5


class TestCacheTtl:
    def test_entry_expires_after_ttl(self):
        clock = {"now": 0.0}
        cache = _Cache(ttl=10, clock=lambda: clock["now"])
        loads: list[int] = []

        def loader() -> int:
            loads.append(1)
            return len(loads)

        assert cache.load("k", loader) == 1
        clock["now"] = 5.0
        assert cache.load("k", loader) == 1  # vigente
        clock["now"] = 15.0
        assert cache.load("k", loader) == 2  # expirada -> recarga

    def test_manager_level_ttl_enables_cache(self, backend):
        mgr = SheetManager("Doc", sheets_client=backend.client, cache_ttl=3600)
        ws = mgr.worksheet("H")
        ws.read()
        backend.client.spreadsheet_by_key("doc0").worksheets[0].grid.set(2, 2, "MUT")
        assert ws.read()[1][1] == "p1"  # sirve del caché (TTL aún vigente)


class TestCacheLru:
    def test_evicts_least_recently_used(self):
        cache = _Cache(max_entries=2)
        cache.load("a", lambda: 1)
        cache.load("b", lambda: 2)
        cache.load("a", lambda: 0)  # hit: 'a' pasa a reciente
        cache.load("c", lambda: 3)  # desaloja 'b'
        loads: list[int] = []

        def reload() -> int:
            loads.append(1)
            return 9

        cache.load("b", reload)
        assert loads  # 'b' fue desalojada y se recargó


class TestSelectiveInvalidation:
    def test_cell_write_keeps_non_overlapping_cached_range(self, backend):
        mgr = SheetManager("Doc", sheets_client=backend.client, cache=True)
        ws = mgr.worksheet("H")
        # Cachear la página de filas 4:6 vía iter_rows (values_get por rango).
        page = list(ws.iter_rows(page_size=3, skiprows=3))
        assert page == ROWS[3:]
        # Mutación externa dentro de esa página (la caché no lo ve).
        backend.client.spreadsheet_by_key("doc0").worksheets[0].grid.set(5, 2, "MUT")
        # Escritura propia en A1: NO se superpone con 4:6 -> la página sigue cacheada.
        ws.update_cell(1, 1, "id2")
        assert list(ws.iter_rows(page_size=3, skiprows=3)) == ROWS[3:]
        # Escritura propia dentro de la página -> ahora sí se invalida y ve la mutación.
        ws.update_cell(4, 1, "3bis")
        refreshed = list(ws.iter_rows(page_size=3, skiprows=3))
        assert refreshed[1][1] == "MUT"

    def test_write_in_one_sheet_keeps_other_sheet_cached(self, backend):
        mgr = SheetManager("Doc", sheets_client=backend.client, cache=True)
        h, otra = mgr.worksheet("H"), mgr.worksheet("Otra")
        otra.read()  # cachea "Otra"
        backend.client.spreadsheet_by_key("doc0").worksheets[1].grid.set(1, 1, "MUT")
        h.update_cell(1, 1, "z")  # escribe en H
        assert otra.read() == [["x"], ["y"]]  # "Otra" sigue sirviendo del caché

    def test_append_invalidates_whole_sheet(self, backend):
        mgr = SheetManager("Doc", sheets_client=backend.client, cache=True)
        ws = mgr.worksheet("H")
        ws.read()
        ws.append([["9", "p9"]])
        assert ws.read()[-1] == ["9", "p9"]

    def test_batch_clear_invalidates_only_overlapping(self, backend):
        mgr = SheetManager("Doc", sheets_client=backend.client, cache=True)
        ws = mgr.worksheet("H")
        page = list(ws.iter_rows(page_size=3, skiprows=3))  # cachea "H!4:6"
        assert page == ROWS[3:]
        backend.client.spreadsheet_by_key("doc0").worksheets[0].grid.set(5, 2, "MUT")
        ws.clear("A1:B2")  # batch_clear de un rango que no se superpone con 4:6
        assert list(ws.iter_rows(page_size=3, skiprows=3)) == ROWS[3:]  # sigue cacheada
