"""gsuite_sheets.engine_async_adapter: port surface and the REST requests it sends."""

import json
from typing import Any

import httpx
import pytest

from gsuite_core.aio import AsyncGoogleClient
from gsuite_sheets.engine.domain.errors import SpreadsheetNotFoundError
from gsuite_sheets.engine.ports.async_sheets import (
    AsyncClientPort,
    AsyncSpreadsheetPort,
    AsyncWorksheetPort,
)
from gsuite_sheets.engine.testing import AsyncInMemoryBackend
from gsuite_sheets.engine.testing.rest_fake import FakeCredentials
from gsuite_sheets.engine_async_adapter import (
    AsyncGoogleApiClient,
    AsyncGoogleApiSpreadsheet,
    AsyncGoogleApiWorksheet,
)


def _members(protocol: type) -> list[str]:
    return sorted(n for n in vars(protocol) if not n.startswith("_"))


def _http(handler=lambda r: httpx.Response(200, json={})) -> AsyncGoogleClient:
    return AsyncGoogleClient(FakeCredentials(), transport=httpx.MockTransport(handler))


def _memory():
    backend = AsyncInMemoryBackend()
    backend.add_spreadsheet("doc", {"Hoja1": [["a"]]})
    return backend


CONTRACT = [
    (AsyncClientPort, lambda: _memory().async_client),
    (AsyncClientPort, lambda: AsyncGoogleApiClient(_http())),
    (AsyncSpreadsheetPort, lambda: AsyncGoogleApiSpreadsheet(_http(), "sid", [("Hoja1", 0)])),
    (
        AsyncWorksheetPort,
        lambda: AsyncGoogleApiWorksheet(
            AsyncGoogleApiSpreadsheet(_http(), "sid", [("Hoja1", 0)]), "Hoja1", 0
        ),
    ),
]


@pytest.mark.parametrize(("port", "make"), CONTRACT, ids=lambda v: getattr(v, "__name__", ""))
def test_implements_full_port_surface(port: type, make: Any) -> None:
    implementation = make()
    missing = [m for m in _members(port) if not hasattr(implementation, m)]
    assert not missing, f"{type(implementation).__name__} lacks {missing}"


class Recorder:
    """Transport that records requests and answers from a {path suffix: response} map."""

    def __init__(self, answers: dict[str, Any] | None = None) -> None:
        self.requests: list[httpx.Request] = []
        self.answers = answers or {}

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        for suffix, answer in self.answers.items():
            if request.url.raw_path.decode().split("?")[0].endswith(suffix):
                return (
                    answer
                    if isinstance(answer, httpx.Response)
                    else httpx.Response(200, json=answer)
                )
        return httpx.Response(200, json={})

    @property
    def paths(self) -> list[str]:
        return [r.url.raw_path.decode().split("?")[0] for r in self.requests]


@pytest.fixture
def recorder():
    return Recorder()


@pytest.fixture
def ws(recorder):
    ss = AsyncGoogleApiSpreadsheet(_http(recorder), "sid", [("Pablo's 2024", 7)])
    return AsyncGoogleApiWorksheet(ss, "Pablo's 2024", 7)


async def test_titles_are_quoted_and_encoded(ws, recorder):
    await ws.update_cell(2, 3, "v")
    assert recorder.paths[-1] == "/v4/spreadsheets/sid/values/%27Pablo%27%27s%202024%27%21C2"


async def test_range_includes_empty_cells(ws, recorder):
    recorder.answers = {"%21B1%3AB4": {"values": [["x"], [], ["z"]]}}
    cells = await ws.range("B1:B4")
    assert [c.value for c in cells] == ["x", "", "z", ""]


async def test_append_and_batch_update(ws, recorder):
    await ws.append_rows([["a"]], "RAW")
    await ws.batch_update([{"range": "A1", "values": [[1]]}], "RAW")

    append, batch = recorder.requests
    assert append.url.params["insertDataOption"] == "INSERT_ROWS"
    assert json.loads(batch.content)["data"][0]["range"] == "'Pablo''s 2024'!A1"


async def test_open_escapes_title():
    recorder = Recorder(
        {
            "/drive/v3/files": {"files": [{"id": "k"}]},
            "/spreadsheets/k": {"properties": {"title": "T"}, "sheets": []},
        }
    )
    ss = await AsyncGoogleApiClient(_http(recorder)).open("Pablo's budget")
    assert recorder.requests[0].url.params["q"].startswith("mimeType = ")
    assert "name = 'Pablo\\'s budget'" in recorder.requests[0].url.params["q"]
    assert ss.title == "T"


async def test_open_missing():
    recorder = Recorder({"/drive/v3/files": {"files": []}})
    with pytest.raises(SpreadsheetNotFoundError):
        await AsyncGoogleApiClient(_http(recorder)).open("nope")


async def test_open_by_key_404_maps_to_not_found():
    recorder = Recorder(
        {"/spreadsheets/gone": httpx.Response(404, json={"error": {"code": 404, "message": "x"}})}
    )
    with pytest.raises(SpreadsheetNotFoundError):
        await AsyncGoogleApiClient(_http(recorder)).open_by_key("gone")


async def test_domain_share_keeps_domain(recorder):
    ss = AsyncGoogleApiSpreadsheet(_http(recorder), "sid", [])
    await ss.share("example.com", "domain", "reader", False, None, True)
    request = recorder.requests[0]
    assert json.loads(request.content) == {
        "type": "domain",
        "role": "reader",
        "domain": "example.com",
        "allowFileDiscovery": False,
    }
    assert "sendNotificationEmail" not in request.url.params


async def test_export_returns_bytes():
    recorder = Recorder({"/export": httpx.Response(200, content=b"%PDF")})
    assert (
        await AsyncGoogleApiSpreadsheet(_http(recorder), "sid", []).export("application/pdf")
        == b"%PDF"
    )
