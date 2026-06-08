"""Servicio de gestión de hojas: crear, eliminar, limpiar y buscar.

Opera sobre hoja/documento duck-typed. El efecto de "activar" la hoja recién creada
(mutar la hoja activa del conector) queda en el conector, no aquí.
"""

from __future__ import annotations

from typing import Any


class WorksheetService:
    """Casos de uso de gestión de hojas (worksheets) y limpieza/búsqueda."""

    def create(self, spreadsheet: Any, title: str, rows: int, cols: int, index: int | None) -> Any:
        """Crea una nueva hoja en el documento y la devuelve."""
        return spreadsheet.add_worksheet(title, rows=rows, cols=cols, index=index)

    def delete(self, spreadsheet: Any, title: str) -> None:
        """Elimina la hoja con el nombre dado del documento."""
        worksheet = spreadsheet.worksheet(title)
        spreadsheet.del_worksheet(worksheet)

    def clear(self, worksheet: Any, ranges: str | list[str] | None) -> None:
        """Limpia uno o más rangos, o toda la hoja si ``ranges`` es None."""
        if ranges is None:
            worksheet.clear()
            return
        targets = [ranges] if isinstance(ranges, str) else ranges
        worksheet.batch_clear(targets)

    def find(self, worksheet: Any, query: str, case_sensitive: bool) -> Any:
        """Busca la primera celda cuyo valor coincide con ``query``; None si no hay."""
        return worksheet.find(query, case_sensitive=case_sensitive)
