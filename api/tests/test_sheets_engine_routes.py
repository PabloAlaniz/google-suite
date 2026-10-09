"""Engine-backed Sheets routes, end to end against the in-memory emulator."""

import pytest

from gsuite_api import dependencies
from gsuite_sheets.engine.testing import InMemoryBackend
from gsuite_sheets.engine.testing.google_api_fake import fake_sheets


@pytest.fixture
def backend():
    backend = InMemoryBackend()
    backend.add_spreadsheet("Budget", {"Data": [["name", "total"], ["Ana", "10"]]})
    return backend


@pytest.fixture
def api(client, backend):
    """The authenticated client, with Sheets routed to the emulator."""
    client.app.dependency_overrides[dependencies.get_sheets] = lambda: fake_sheets(backend.client)
    return client


def requests_of(backend):
    return [next(iter(r)) for r in backend.client.open("Budget").requests]


SID, WID = "doc0", 0
BASE = f"/sheets/{SID}/worksheets/{WID}"


def test_upsert(api, backend):
    response = api.post(
        f"{BASE}/upsert",
        json={"rows": [{"name": "Ana", "total": 20}, {"name": "Bo", "total": 5}], "key": "name"},
    )

    assert response.json() == {"id": 0, "updated": 1, "appended": 1}
    assert backend.client.open("Budget").worksheet("Data").get_all_values()[-1] == ["Bo", "5"]


def test_upsert_unknown_key_is_422(api):
    response = api.post(f"{BASE}/upsert", json={"rows": [{"x": 1}], "key": "missing"})
    assert response.status_code == 422
    assert response.headers["content-type"] == "application/problem+json"


def test_validation_and_formatting(api, backend):
    assert (
        api.post(f"{BASE}/dropdown", json={"range": "C2:C9", "values": ["ok", "no"]}).status_code
        == 200
    )
    assert api.post(f"{BASE}/checkbox", json={"range": "D2:D9"}).status_code == 200
    body = {
        "range": "B2:B9",
        "condition_type": "NUMBER_LESS",
        "values": [0],
        "background": "#F4CCCC",
        "bold": True,
    }
    assert api.post(f"{BASE}/conditional-format", json=body).status_code == 200
    assert requests_of(backend) == [
        "setDataValidation",
        "setDataValidation",
        "addConditionalFormatRule",
    ]


def test_bad_color_is_422(api):
    body = {
        "range": "B2",
        "condition_type": "NUMBER_LESS",
        "values": [0],
        "background": "not-a-color",
    }
    assert api.post(f"{BASE}/conditional-format", json=body).status_code == 422


def test_merge_sort_dimensions(api, backend):
    api.post(f"{BASE}/merge", json={"range": "A1:B1"})
    api.post(f"{BASE}/unmerge", json={"range": "A1:B1"})
    api.post(f"{BASE}/sort", json={"range": "A2:B9", "by": [[2, "desc"]]})
    api.post(f"{BASE}/dimensions:insert", json={"dimension": "rows", "start": 2, "count": 2})

    assert backend.client.open("Budget").worksheet("Data").get_all_values()[3] == ["Ana", "10"]
    api.post(f"{BASE}/dimensions:delete", json={"dimension": "rows", "start": 2, "count": 2})
    assert backend.client.open("Budget").worksheet("Data").get_all_values()[1] == ["Ana", "10"]
    assert {"mergeCells", "unmergeCells", "sortRange"} <= set(requests_of(backend))


def test_sort_validates_direction(api):
    assert api.post(f"{BASE}/sort", json={"range": "A1", "by": [[1, "up"]]}).status_code == 422


def test_export(api):
    response = api.get(f"/sheets/{SID}/export", params={"format": "csv"})

    assert response.content == b"name,total\nAna,10"
    assert response.headers["content-type"].startswith("text/csv")
    assert 'filename="Budget.csv"' in response.headers["content-disposition"]


def test_missing_worksheet_is_404(api):
    assert (
        api.post(f"/sheets/{SID}/worksheets/99/checkbox", json={"range": "A1"}).status_code == 404
    )


def test_missing_spreadsheet_is_404(api):
    # SpreadsheetNotFoundError from the engine maps to 404
    response = api.post("/sheets/nope/worksheets/0/checkbox", json={"range": "A1"})
    assert response.status_code == 404


def _engine_errors():
    from gsuite_sheets.engine.domain import errors as e

    return [
        (e.SpreadsheetNotFoundError("x", 404), 404),
        (e.WorksheetNotFoundError("x", 404), 404),
        (e.SchemaError("x"), 422),
        (e.InvalidRangeError("x"), 422),
        (e.GSpreadManagerError("x"), 422),
        (e.ApiError("x", 500), 502),
    ]


@pytest.mark.parametrize(("error", "status"), _engine_errors(), ids=lambda v: type(v).__name__)
def test_engine_error_statuses(client, services, error, status):
    services["sheets"].open_by_key.side_effect = error
    assert client.get("/sheets/sid/export").status_code == status
