"""Servicio de visualización: charts, pivot tables y banding.

Construye las peticiones desde los value objects del dominio (``ChartSpec``,
``PivotTableSpec``, ``BandingSpec``) y las envía por ``spreadsheets:batchUpdate``.
Opera sobre ``WorksheetPort``; los rangos A1 se resuelven aquí con el id de la hoja.
"""

from __future__ import annotations

from typing import Any

from gspreadmanager.domain.values import (
    BandingSpec,
    ChartSpec,
    GridRange,
    PivotField,
    PivotTableSpec,
    PivotValue,
)
from gspreadmanager.ports.sheets import WorksheetPort


class VisualizationService:
    """Casos de uso de gráficos, pivots y bandas de color."""

    def add_chart(
        self,
        worksheet: WorksheetPort,
        spec: ChartSpec,
        domain: str,
        series: list[str],
        anchor_cell: str,
    ) -> int | None:
        """Agrega un gráfico embebido; devuelve su ``chartId`` (None si el backend no lo da)."""
        request = spec.to_request(
            GridRange.from_a1(domain, worksheet.id),
            [GridRange.from_a1(rng, worksheet.id) for rng in series],
            GridRange.from_a1(anchor_cell, worksheet.id),
        )
        reply = self._apply(worksheet, request)
        chart_id = reply.get("addChart", {}).get("chart", {}).get("chartId")
        return int(chart_id) if chart_id is not None else None

    def delete_chart(self, worksheet: WorksheetPort, chart_id: int) -> None:
        """Elimina un gráfico embebido por su id."""
        self._apply(worksheet, {"deleteEmbeddedObject": {"objectId": chart_id}})

    def add_pivot_table(
        self,
        worksheet: WorksheetPort,
        source: str,
        anchor_cell: str,
        rows: list[int],
        values: list[tuple[int, str]],
        columns: list[int],
    ) -> None:
        """Escribe una pivot table en ``anchor_cell``.

        ``rows``/``columns`` son offsets 0-based de columnas del rango fuente;
        ``values``, pares ``(offset, función)`` (SUM/COUNT/AVERAGE/...).
        """
        spec = PivotTableSpec(
            rows=tuple(PivotField(offset) for offset in rows),
            values=tuple(PivotValue(offset, function) for offset, function in values),
            columns=tuple(PivotField(offset) for offset in columns),
        )
        request = spec.to_request(
            GridRange.from_a1(source, worksheet.id),
            GridRange.from_a1(anchor_cell, worksheet.id),
        )
        self._apply(worksheet, request)

    def set_banding(
        self, worksheet: WorksheetPort, spec: BandingSpec, range_name: str
    ) -> int | None:
        """Aplica bandas alternadas al rango; devuelve el ``bandedRangeId`` (si el backend lo da)."""
        reply = self._apply(
            worksheet, spec.to_request(GridRange.from_a1(range_name, worksheet.id))
        )
        banded_id = reply.get("addBanding", {}).get("bandedRange", {}).get("bandedRangeId")
        return int(banded_id) if banded_id is not None else None

    def delete_banding(self, worksheet: WorksheetPort, banded_range_id: int) -> None:
        """Quita las bandas alternadas por su id."""
        self._apply(worksheet, {"deleteBanding": {"bandedRangeId": banded_range_id}})

    def _apply(self, worksheet: WorksheetPort, request: dict[str, Any]) -> dict[str, Any]:
        """Envía la request y devuelve su reply (dict vacío si el backend no responde)."""
        result = worksheet.spreadsheet.batch_update({"requests": [request]})
        if isinstance(result, dict):
            replies = result.get("replies") or []
            if replies and isinstance(replies[0], dict):
                first: dict[str, Any] = replies[0]
                return first
        return {}
