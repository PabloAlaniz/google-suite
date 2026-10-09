"""Sheets worksheet, formatting and find/replace routes."""

import pytest

from gsuite_sheets.worksheet import Worksheet


@pytest.fixture
def sheets(services):
    return services["sheets"]


def test_raw_value_input(client, sheets):
    sheets.update_values.return_value = {}

    client.put(
        "/sheets/sid/values/A1",
        json={"range": "A1", "values": [["=HYPERLINK(...)"]]},
        params={"value_input": "RAW"},
    )

    assert sheets.update_values.call_args.args[-1] == "RAW"


def test_invalid_value_input(client):
    response = client.put(
        "/sheets/sid/values/A1",
        json={"range": "A1", "values": [[1]]},
        params={"value_input": "EVAL"},
    )
    assert response.status_code == 422


def test_append_quotes_sheet_name(client, sheets):
    sheets.append_values.return_value = {}

    client.post("/sheets/sid/values/Q1 Budget:append", json={"values": [[1]]})

    assert sheets.append_values.call_args.args[1] == "'Q1 Budget'"


def test_batch_get(client, sheets):
    sheets.batch_get_values.return_value = [[["a"]], []]

    response = client.get(
        "/sheets/sid/values:batchGet", params=[("ranges", "S!A1"), ("ranges", "S!B:B")]
    )

    assert response.json()["value_ranges"] == [
        {"range": "S!A1", "values": [["a"]]},
        {"range": "S!B:B", "values": []},
    ]


def test_find_replace(client, sheets):
    sheets.find_replace.return_value = 4

    response = client.post(
        "/sheets/sid:findReplace", json={"find": "a", "replacement": "b", "regex": True}
    )

    assert response.json() == {"spreadsheet_id": "sid", "occurrences_changed": 4}
    assert sheets.find_replace.call_args.kwargs["regex"] is True


class TestWorksheets:
    def test_add(self, client, sheets):
        sheets.add_worksheet.return_value = Worksheet(id=3, title="New", index=1)

        response = client.post("/sheets/sid/worksheets", json={"title": "New", "rows": 10})

        assert response.json()["id"] == 3
        sheets.add_worksheet.assert_called_once_with("sid", "New", 10, 26)

    def test_rename(self, client, sheets):
        assert client.patch("/sheets/sid/worksheets/3", json={"title": "R"}).status_code == 200
        sheets.rename_worksheet.assert_called_once_with("sid", 3, "R")

    def test_delete_missing(self, client, sheets):
        sheets.delete_worksheet.return_value = False
        assert client.delete("/sheets/sid/worksheets/3").status_code == 404

    def test_sheet_id_must_be_int(self, client):
        assert client.delete("/sheets/sid/worksheets/abc").status_code == 422

    def test_duplicate(self, client, sheets):
        sheets.duplicate_worksheet.return_value = Worksheet(id=9, title="Copy", index=2)
        assert client.post("/sheets/sid/worksheets/3/duplicate", json={}).json()["title"] == "Copy"

    def test_format(self, client, sheets):
        body = {"range": "A1:Z1", "format": {"textFormat": {"bold": True}}}
        assert client.post("/sheets/sid/worksheets/3/format", json=body).status_code == 200
        sheets.format_range.assert_called_once_with(
            "sid", 3, "A1:Z1", {"textFormat": {"bold": True}}
        )

    def test_format_bad_range_is_422(self, client, sheets):
        from gsuite_core.exceptions import ValidationError

        sheets.format_range.side_effect = ValidationError("range", "invalid A1 range 'A1:'")

        response = client.post(
            "/sheets/sid/worksheets/3/format", json={"range": "A1:", "format": {"x": 1}}
        )

        assert response.status_code == 422
        assert response.json()["field"] == "range"

    def test_freeze(self, client, sheets):
        client.post("/sheets/sid/worksheets/3/freeze", json={"rows": 1})
        sheets.freeze.assert_called_once_with("sid", 3, 1, None)

    def test_negative_freeze_rejected(self, client):
        assert client.post("/sheets/sid/worksheets/3/freeze", json={"rows": -1}).status_code == 422

    def test_protect(self, client, sheets):
        sheets.protect_range.return_value = 77

        response = client.post(
            "/sheets/sid/worksheets/3/protect",
            json={"range": "A1:A5", "editors": ["a@example.com"]},
        )

        assert response.json()["protected_range_id"] == 77
        assert sheets.protect_range.call_args.args[4] == ["a@example.com"]
