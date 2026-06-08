"""Servicio de gestión de hojas: crear, eliminar, limpiar y buscar.

Opera sobre ``SpreadsheetPort`` / ``WorksheetPort``. Qué hacer con la hoja recién creada
(envolverla en un handle) queda en el facade, no aquí.
"""

from __future__ import annotations

from typing import Any

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
