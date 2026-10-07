"""AsyncSheets / AsyncSpreadsheet / AsyncWorksheet end to end over the REST fake."""

import io
from dataclasses import dataclass

import pytest

from gsuite_sheets.engine.testing import InMemoryBackend
from gsuite_sheets.engine.testing.rest_fake import fake_async_sheets


@dataclass
class Row:
    name: str
    total: int


@pytest.fixture
def backend():
    backend = InMemoryBackend()
    backend.add_spreadsheet("Budget", {"Data": [["name", "total"], ["Ana", "10"], ["Bo", "5"]]})
    return backend


@pytest.fixture
async def sheets(backend):
    async with fake_async_sheets(backend.client) as client:
        yield client


@pytest.fixture
async def doc(sheets):
    return await sheets.open("Budget")


@pytest.fixture
async def ws(doc):
    return doc.worksheet("Data")


def grid(backend):
    return backend.client.open("Budget").worksheet("Data").get_all_values()


async def test_open_and_tabs(doc):
    assert doc.title == "Budget"
    assert [w.title for w in doc.worksheets] == ["Data"]
    assert doc.sheet1.title == "Data"
    assert doc.worksheet("nope") is None


async def test_values(ws, backend):
    assert await ws.get("A2:B2") == [["Ana", "10"]]
    assert (await ws.get_all_records())[1] == {"name": "Bo", "total": "5"}
    await ws.update("B2", [[11]])
    await ws.update_cell(3, 2, 6)
    await ws.append_row(["Cy", 1])
    assert grid(backend)[1:] == [["Ana", "11"], ["Bo", "6"], ["Cy", "1"]]


async def test_tables(ws, backend):
    assert await ws.upsert(
        [{"name": "Ana", "total": 20}, {"name": "Dee", "total": 2}], key="name"
    ) == {"updated": 1, "appended": 1}
    assert await ws.update_where({"name": "Bo"}, {"total": 0}) == 1
    assert await ws.delete_where(lambda r: r["name"] == "Dee") == 1
    assert [r[0] for r in grid(backend)] == ["name", "Ana", "Bo"]


async def test_streaming(ws):
    assert [r async for r in ws.iter_rows(page_size=1)][1] == ["Ana", "10"]
    assert [r["name"] async for r in ws.iter_records(page_size=1)] == ["Ana", "Bo"]
    assert [r async for r in ws.iter_as(Row)] == [Row("Ana", 10), Row("Bo", 5)]


async def test_typed_rows(doc):
    tab = await doc.add_worksheet("Models")
    await tab.write_models([Row("Ana", 1)])
    await tab.append_models([Row("Bo", 2)])
    assert await tab.upsert_models([Row("Ana", 3)], key="name") == {"updated": 1, "appended": 0}
    assert await tab.read_as(Row) == [Row("Ana", 3), Row("Bo", 2)]


async def test_import_find_clear(ws, backend):
    await ws.import_csv(io.StringIO("a,b\n1,2\n"))
    assert (await ws.find("2")).col == 2
    await ws.clear()
    assert grid(backend) == []


async def test_worksheet_management(doc):
    tab = await doc.worksheet_or_create("Log")
    assert await doc.worksheet_or_create("Log") is not None
    await doc.del_worksheet(tab)
    assert doc.worksheet("Log") is None


async def test_document(sheets, doc):
    assert (await doc.export("csv")).startswith(b"name,total")
    await doc.share("ana@example.com", role="writer")
    assert (await doc.list_permissions())[0]["emailAddress"] == "ana@example.com"
    copy = await sheets.copy(doc.id, title="Budget copy")
    assert copy.worksheet("Data") is not None
    await sheets.delete(copy.id)
    assert "Budget copy" not in {f["name"] for f in await sheets.list_spreadsheets()}
