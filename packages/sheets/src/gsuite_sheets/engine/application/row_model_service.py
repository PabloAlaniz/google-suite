"""Servicio de modelos de fila tipados.

Lee/escribe filas de una hoja como instancias de un ``@dataclass``, delegando el mapeo y la
coerción de tipos en el dominio (``domain.schema``). Opera sobre ``WorksheetPort``.
"""

from __future__ import annotations

from typing import Any

from gspreadmanager.domain.schema import models_to_rows, rows_to_models
from gspreadmanager.ports.sheets import WorksheetPort


class RowModelService:
    """Casos de uso de lectura/escritura de filas tipadas."""

    def read(self, worksheet: WorksheetPort, model: type, skiprows: int) -> list[Any]:
        """Lee la hoja como una lista de instancias de ``model`` (encabezado en la 1ª fila)."""
        values = worksheet.get_all_values()[skiprows:]
        if not values:
            return []
        return rows_to_models(model, values[0], values[1:])

    def append(self, worksheet: WorksheetPort, models: list[Any], value_input_option: str) -> Any:
        """Añade los modelos como filas al final (sin encabezado)."""
        if not models:
            return None
        _, rows = models_to_rows(models)
        return worksheet.append_rows(rows, value_input_option)

    def write(
        self,
        worksheet: WorksheetPort,
        models: list[Any],
        include_header: bool,
        clear: bool,
        value_input_option: str,
    ) -> Any:
        """Escribe los modelos desde A1 (encabezado opcional), limpiando antes si ``clear``."""
        header, rows = models_to_rows(models)
        values = ([header] if include_header and header else []) + rows
        if clear:
            worksheet.clear()
        return worksheet.update(values, value_input_option)
