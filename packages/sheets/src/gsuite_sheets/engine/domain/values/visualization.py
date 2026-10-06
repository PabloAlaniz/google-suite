"""Value objects: charts, pivot tables, banding y developer metadata.

Modelan las peticiones ``addChart``, ``updateCells`` (pivotTable), ``addBanding`` y
``createDeveloperMetadata`` de la Sheets API v4. ``to_request`` recibe los ``GridRange``
ya resueltos (la conversión A1 -> GridRange depende del id de la hoja).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from gspreadmanager.domain.errors import GSpreadManagerError

from .color import Color
from .ranges import GridRange

CHART_TYPES = ("LINE", "BAR", "COLUMN", "AREA", "SCATTER", "PIE")
PIVOT_FUNCTIONS = ("SUM", "COUNTA", "COUNT", "AVERAGE", "MAX", "MIN", "MEDIAN")


def _anchor_dict(anchor: GridRange) -> dict[str, int]:
    """Celda ancla (esquina superior izquierda) de un ``GridRange`` de una celda."""
    return {
        "sheetId": anchor.sheet_id,
        "rowIndex": anchor.start_row_index or 0,
        "columnIndex": anchor.start_column_index or 0,
    }


@dataclass(frozen=True)
class ChartSpec:
    """Gráfico básico embebido: línea, barra, columna, área, dispersión o torta."""

    chart_type: str
    title: str | None = None
    legend_position: str = "BOTTOM_LEGEND"

    def __post_init__(self) -> None:
        """Valida el tipo de gráfico."""
        if self.chart_type not in CHART_TYPES:
            raise GSpreadManagerError(
                f"Tipo de gráfico inválido: {self.chart_type!r} (usá uno de {CHART_TYPES})."
            )

    def to_request(
        self, domain: GridRange, series: list[GridRange], anchor: GridRange
    ) -> dict[str, Any]:
        """Petición ``addChart``: ``domain`` es el eje de etiquetas; ``series``, los datos."""
        spec: dict[str, Any] = {}
        if self.title is not None:
            spec["title"] = self.title
        if self.chart_type == "PIE":
            spec["pieChart"] = {
                "legendPosition": self.legend_position,
                "domain": _source(domain),
                "series": _source(series[0]),
            }
        else:
            spec["basicChart"] = {
                "chartType": self.chart_type,
                "legendPosition": self.legend_position,
                "domains": [{"domain": _source(domain)}],
                "series": [{"series": _source(grid)} for grid in series],
            }
        return {
            "addChart": {
                "chart": {
                    "spec": spec,
                    "position": {"overlayPosition": {"anchorCell": _anchor_dict(anchor)}},
                }
            }
        }


def _source(grid: GridRange) -> dict[str, Any]:
    return {"sourceRange": {"sources": [grid.to_dict()]}}


@dataclass(frozen=True)
class PivotField:
    """Agrupación de un pivot (fila o columna): offset 0-based dentro del rango fuente."""

    source_column: int
    sort_order: str = "ASCENDING"
    show_totals: bool = True

    def to_dict(self) -> dict[str, Any]:
        """Serializa al objeto ``PivotGroup``."""
        return {
            "sourceColumnOffset": self.source_column,
            "sortOrder": self.sort_order,
            "showTotals": self.show_totals,
        }


@dataclass(frozen=True)
class PivotValue:
    """Valor agregado de un pivot: offset 0-based + función de agregación."""

    source_column: int
    function: str = "SUM"

    def __post_init__(self) -> None:
        """Valida la función de agregación."""
        if self.function not in PIVOT_FUNCTIONS:
            raise GSpreadManagerError(
                f"Función de pivot inválida: {self.function!r} (usá una de {PIVOT_FUNCTIONS})."
            )

    def to_dict(self) -> dict[str, Any]:
        """Serializa al objeto ``PivotValue``."""
        return {
            "sourceColumnOffset": self.source_column,
            "summarizeFunction": self.function,
        }


@dataclass(frozen=True)
class PivotTableSpec:
    """Pivot table sobre un rango fuente, anclada en una celda."""

    rows: tuple[PivotField, ...]
    values: tuple[PivotValue, ...]
    columns: tuple[PivotField, ...] = ()

    def to_request(self, source: GridRange, anchor: GridRange) -> dict[str, Any]:
        """Petición ``updateCells`` que escribe la pivot table en la celda ancla."""
        pivot: dict[str, Any] = {
            "source": source.to_dict(),
            "rows": [field.to_dict() for field in self.rows],
            "values": [value.to_dict() for value in self.values],
        }
        if self.columns:
            pivot["columns"] = [field.to_dict() for field in self.columns]
        return {
            "updateCells": {
                "rows": [{"values": [{"pivotTable": pivot}]}],
                "start": _anchor_dict(anchor),
                "fields": "pivotTable",
            }
        }


@dataclass(frozen=True)
class BandingSpec:
    """Bandas de color alternadas por fila (con banda de encabezado opcional)."""

    first_color: Color
    second_color: Color
    header_color: Color | None = None

    def to_request(self, grid_range: GridRange) -> dict[str, Any]:
        """Petición ``addBanding`` para ``grid_range``."""
        properties: dict[str, Any] = {
            "firstBandColor": self.first_color.to_dict(),
            "secondBandColor": self.second_color.to_dict(),
        }
        if self.header_color is not None:
            properties["headerColor"] = self.header_color.to_dict()
        return {
            "addBanding": {
                "bandedRange": {
                    "range": grid_range.to_dict(),
                    "rowProperties": properties,
                }
            }
        }


@dataclass(frozen=True)
class DeveloperMetadataEntry:
    """Par clave/valor de developer metadata, anclado al documento o a una hoja."""

    key: str
    value: str
    visibility: str = "DOCUMENT"

    def __post_init__(self) -> None:
        """Valida clave y visibilidad."""
        if not self.key.strip():
            raise GSpreadManagerError("La clave de developer metadata no puede estar vacía.")
        if self.visibility not in ("DOCUMENT", "PROJECT"):
            raise GSpreadManagerError(
                f"Visibilidad inválida: {self.visibility!r} (usá 'DOCUMENT' o 'PROJECT')."
            )

    def to_request(self, sheet_id: int | None) -> dict[str, Any]:
        """Petición ``createDeveloperMetadata`` (``sheet_id=None`` ancla al documento)."""
        location: dict[str, Any] = (
            {"spreadsheet": True} if sheet_id is None else {"sheetId": sheet_id}
        )
        return {
            "createDeveloperMetadata": {
                "developerMetadata": {
                    "metadataKey": self.key,
                    "metadataValue": self.value,
                    "location": location,
                    "visibility": self.visibility,
                }
            }
        }
