"""Servicio de gestión de hojas: crear, eliminar, limpiar y buscar.

Opera sobre ``SpreadsheetPort`` / ``WorksheetPort``. Qué hacer con la hoja recién creada
(envolverla en un handle) queda en el facade, no aquí.
"""

from __future__ import annotations

from typing import Any

from gspreadmanager.domain.values import Color, GridRange
from gspreadmanager.ports.sheets import SpreadsheetPort, WorksheetPort


class WorksheetService:
    """Casos de uso de gestión de hojas (worksheets) y limpieza/búsqueda."""

    def create(
        self, spreadsheet: SpreadsheetPort, title: str, rows: int, cols: int, index: int | None
    ) -> WorksheetPort:
        """Crea una nueva hoja en el documento y la devuelve."""
        return spreadsheet.add_worksheet(title, rows, cols, index)

    def delete(self, spreadsheet: SpreadsheetPort, title: str) -> None:
        """Elimina la hoja con el nombre dado del documento."""
        spreadsheet.delete_worksheet(title)

    def clear(self, worksheet: WorksheetPort, ranges: str | list[str] | None) -> None:
        """Limpia uno o más rangos, o toda la hoja si ``ranges`` es None."""
        if ranges is None:
            worksheet.clear()
            return
        targets = [ranges] if isinstance(ranges, str) else ranges
        worksheet.batch_clear(targets)

    def find(self, worksheet: WorksheetPort, query: str, case_sensitive: bool) -> Any:
        """Busca la primera celda cuyo valor coincide con ``query``; None si no hay."""
        return worksheet.find(query, case_sensitive)

    # ------------------------------------------------------------------
    # Manipulación de dimensiones (filas / columnas) vía batchUpdate.
    # ``dimension`` es "ROWS" o "COLUMNS"; los índices son 0-based, fin exclusivo.
    # ------------------------------------------------------------------

    def _apply(self, worksheet: WorksheetPort, request: dict[str, Any]) -> None:
        worksheet.spreadsheet.batch_update({"requests": [request]})

    def insert_dimension(
        self,
        worksheet: WorksheetPort,
        dimension: str,
        start: int,
        end: int,
        inherit_from_before: bool,
    ) -> None:
        """Inserta filas/columnas en blanco en ``[start, end)`` (``insertDimension``)."""
        self._apply(
            worksheet,
            {
                "insertDimension": {
                    "range": {
                        "sheetId": worksheet.id,
                        "dimension": dimension,
                        "startIndex": start,
                        "endIndex": end,
                    },
                    "inheritFromBefore": inherit_from_before,
                }
            },
        )

    def delete_dimension(
        self, worksheet: WorksheetPort, dimension: str, start: int, end: int
    ) -> None:
        """Elimina filas/columnas en ``[start, end)`` (``deleteDimension``)."""
        self._apply(
            worksheet,
            {
                "deleteDimension": {
                    "range": {
                        "sheetId": worksheet.id,
                        "dimension": dimension,
                        "startIndex": start,
                        "endIndex": end,
                    }
                }
            },
        )

    def append_dimension(self, worksheet: WorksheetPort, dimension: str, length: int) -> None:
        """Agrega ``length`` filas/columnas al final (``appendDimension``)."""
        self._apply(
            worksheet,
            {
                "appendDimension": {
                    "sheetId": worksheet.id,
                    "dimension": dimension,
                    "length": length,
                }
            },
        )

    def update_dimension(
        self,
        worksheet: WorksheetPort,
        dimension: str,
        start: int,
        end: int,
        properties: dict[str, Any],
        fields: str,
    ) -> None:
        """Actualiza propiedades de dimensión (tamaño/oculto) en ``[start, end)``."""
        self._apply(
            worksheet,
            {
                "updateDimensionProperties": {
                    "range": {
                        "sheetId": worksheet.id,
                        "dimension": dimension,
                        "startIndex": start,
                        "endIndex": end,
                    },
                    "properties": properties,
                    "fields": fields,
                }
            },
        )

    # ------------------------------------------------------------------
    # Orden / filtro / merge / color de pestaña (vía batchUpdate)
    # ------------------------------------------------------------------

    def sort_range(
        self, worksheet: WorksheetPort, grid_range: GridRange, sort_specs: list[dict[str, Any]]
    ) -> None:
        """Ordena un rango según ``sort_specs`` (``sortRange``)."""
        self._apply(
            worksheet, {"sortRange": {"range": grid_range.to_dict(), "sortSpecs": sort_specs}}
        )

    def set_basic_filter(self, worksheet: WorksheetPort, grid_range: GridRange | None) -> None:
        """Activa un filtro básico sobre un rango (o toda la hoja si ``grid_range`` es None)."""
        filter_range = grid_range.to_dict() if grid_range else {"sheetId": worksheet.id}
        self._apply(worksheet, {"setBasicFilter": {"filter": {"range": filter_range}}})

    def clear_basic_filter(self, worksheet: WorksheetPort) -> None:
        """Quita el filtro básico de la hoja."""
        self._apply(worksheet, {"clearBasicFilter": {"sheetId": worksheet.id}})

    def unmerge(self, worksheet: WorksheetPort, grid_range: GridRange) -> None:
        """Deshace la combinación de celdas de un rango (``unmergeCells``)."""
        self._apply(worksheet, {"unmergeCells": {"range": grid_range.to_dict()}})

    def set_tab_color(self, worksheet: WorksheetPort, color: Color) -> None:
        """Fija el color de la pestaña (``updateSheetProperties`` campo ``tabColor``)."""
        self._apply(
            worksheet,
            {
                "updateSheetProperties": {
                    "properties": {"sheetId": worksheet.id, "tabColor": color.to_dict()},
                    "fields": "tabColor",
                }
            },
        )

    def clear_tab_color(self, worksheet: WorksheetPort) -> None:
        """Quita el color de la pestaña."""
        self._apply(
            worksheet,
            {
                "updateSheetProperties": {
                    "properties": {"sheetId": worksheet.id},
                    "fields": "tabColor",
                }
            },
        )
