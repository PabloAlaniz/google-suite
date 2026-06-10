"""Tests del Sprint 8 (v2.7): charts, pivot tables, banding y developer metadata.

Los value objects se validan contra la forma exacta de las peticiones de la API v4; el
backend en memoria registra las requests (``spreadsheet.requests``) para verificar el
cableado de la facade.
"""

from typing import Any

import pytest
from gspreadmanager import Color, GSpreadManagerError
from gspreadmanager.domain.values import (
    BandingSpec,
    ChartSpec,
    DeveloperMetadataEntry,
    GridRange,
    PivotField,
    PivotTableSpec,
    PivotValue,
)
from gspreadmanager.testing import InMemoryBackend


@pytest.fixture
def backend():
    b = InMemoryBackend()
    b.add_spreadsheet("Doc", {"H": [["mes", "ventas"], ["ene", "10"], ["feb", "20"]]})
    return b


@pytest.fixture
def ws(backend):
    return backend.manager("Doc").worksheet("H")


def requests_of(backend: InMemoryBackend) -> list[dict[str, Any]]:
    return backend.client.spreadsheet_by_key("doc0").requests


class TestChartSpec:
    def test_basic_chart_request_shape(self):
        spec = ChartSpec("COLUMN", title="Ventas")
        request = spec.to_request(
            GridRange.from_a1("A1:A3", 0),
            [GridRange.from_a1("B1:B3", 0)],
            GridRange.from_a1("D2", 0),
        )
        chart = request["addChart"]["chart"]
        assert chart["spec"]["title"] == "Ventas"
        basic = chart["spec"]["basicChart"]
        assert basic["chartType"] == "COLUMN"
        assert basic["domains"][0]["domain"]["sourceRange"]["sources"][0]["startColumnIndex"] == 0
        assert basic["series"][0]["series"]["sourceRange"]["sources"][0]["startColumnIndex"] == 1
        anchor = chart["position"]["overlayPosition"]["anchorCell"]
        assert anchor == {"sheetId": 0, "rowIndex": 1, "columnIndex": 3}

    def test_pie_chart_uses_pie_spec(self):
        request = ChartSpec("PIE").to_request(
            GridRange.from_a1("A1:A3", 0),
            [GridRange.from_a1("B1:B3", 0)],
            GridRange.from_a1("D1", 0),
        )
        spec = request["addChart"]["chart"]["spec"]
        assert "pieChart" in spec
        assert "basicChart" not in spec

    def test_invalid_chart_type_raises(self):
        with pytest.raises(GSpreadManagerError, match="Tipo de gráfico inválido"):
            ChartSpec("RADAR")


class TestPivotTableSpec:
    def test_request_shape(self):
        spec = PivotTableSpec(
            rows=(PivotField(0),),
            values=(PivotValue(1, "SUM"),),
            columns=(PivotField(2, sort_order="DESCENDING"),),
        )
        request = spec.to_request(GridRange.from_a1("A1:C100", 7), GridRange.from_a1("E1", 7))
        update = request["updateCells"]
        pivot = update["rows"][0]["values"][0]["pivotTable"]
        assert pivot["source"]["sheetId"] == 7
        assert pivot["rows"] == [
            {"sourceColumnOffset": 0, "sortOrder": "ASCENDING", "showTotals": True}
        ]
        assert pivot["values"] == [{"sourceColumnOffset": 1, "summarizeFunction": "SUM"}]
        assert pivot["columns"][0]["sortOrder"] == "DESCENDING"
        assert update["start"] == {"sheetId": 7, "rowIndex": 0, "columnIndex": 4}
        assert update["fields"] == "pivotTable"

    def test_invalid_function_raises(self):
        with pytest.raises(GSpreadManagerError, match="Función de pivot inválida"):
            PivotValue(0, "PRODUCT")


class TestBandingSpec:
    def test_request_shape_with_header(self):
        spec = BandingSpec(
            Color.from_hex("#FFFFFF"),
            Color.from_hex("#F3F3F3"),
            header_color=Color.from_hex("#D9EAD3"),
        )
        request = spec.to_request(GridRange.from_a1("A1:C10", 0))
        properties = request["addBanding"]["bandedRange"]["rowProperties"]
        assert set(properties) == {"firstBandColor", "secondBandColor", "headerColor"}

    def test_header_optional(self):
        spec = BandingSpec(Color.from_hex("#FFFFFF"), Color.from_hex("#EEEEEE"))
        properties = spec.to_request(GridRange.from_a1("A1:B2", 0))
        assert "headerColor" not in properties["addBanding"]["bandedRange"]["rowProperties"]


class TestDeveloperMetadataEntry:
    def test_sheet_scoped_request(self):
        request = DeveloperMetadataEntry("version", "42").to_request(sheet_id=3)
        meta = request["createDeveloperMetadata"]["developerMetadata"]
        assert meta == {
            "metadataKey": "version",
            "metadataValue": "42",
            "location": {"sheetId": 3},
            "visibility": "DOCUMENT",
        }

    def test_spreadsheet_scoped_request(self):
        request = DeveloperMetadataEntry("owner", "data-team").to_request(sheet_id=None)
        assert request["createDeveloperMetadata"]["developerMetadata"]["location"] == {
            "spreadsheet": True
        }

    def test_invalid_key_and_visibility_raise(self):
        with pytest.raises(GSpreadManagerError, match="clave"):
            DeveloperMetadataEntry("  ", "x")
        with pytest.raises(GSpreadManagerError, match="Visibilidad"):
            DeveloperMetadataEntry("k", "v", visibility="PUBLIC")


class TestFacadeWiring:
    def test_add_chart_records_request(self, backend, ws):
        ws.add_chart("LINE", "A1:A3", ["B1:B3"], title="Ventas", anchor_cell="D2")
        recorded = requests_of(backend)[-1]
        assert recorded["addChart"]["chart"]["spec"]["basicChart"]["chartType"] == "LINE"

    def test_add_pivot_table_records_request(self, backend, ws):
        ws.add_pivot_table("A1:B3", "D1", rows=[0], values=[(1, "SUM")])
        recorded = requests_of(backend)[-1]
        pivot = recorded["updateCells"]["rows"][0]["values"][0]["pivotTable"]
        assert pivot["values"] == [{"sourceColumnOffset": 1, "summarizeFunction": "SUM"}]

    def test_set_and_delete_banding(self, backend, ws):
        ws.set_banding(
            "A1:B3",
            first_color=Color.from_hex("#FFFFFF"),
            second_color=Color.from_hex("#EEEEEE"),
        )
        assert "addBanding" in requests_of(backend)[-1]
        ws.delete_banding(5)
        assert requests_of(backend)[-1] == {"deleteBanding": {"bandedRangeId": 5}}

    def test_delete_chart(self, backend, ws):
        ws.delete_chart(9)
        assert requests_of(backend)[-1] == {"deleteEmbeddedObject": {"objectId": 9}}

    def test_developer_metadata_sheet_and_document(self, backend, ws):
        mgr = backend.manager("Doc")
        ws.set_developer_metadata("version", "1")
        mgr.set_developer_metadata("owner", "data-team")
        mgr.delete_developer_metadata("version")
        recorded = requests_of(backend)
        sheet_meta = recorded[-3]["createDeveloperMetadata"]["developerMetadata"]
        assert sheet_meta["location"] == {"sheetId": 0}
        doc_meta = recorded[-2]["createDeveloperMetadata"]["developerMetadata"]
        assert doc_meta["location"] == {"spreadsheet": True}
        lookup = recorded[-1]["deleteDeveloperMetadata"]["dataFilter"]
        assert lookup == {"developerMetadataLookup": {"metadataKey": "version"}}
