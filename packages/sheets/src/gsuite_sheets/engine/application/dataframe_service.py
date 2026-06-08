"""Servicio de integración con DataFrames.

Orquesta la lectura/escritura de DataFrames usando un ``DataFramePort`` inyectado (sin
conocer pandas) y una hoja duck-typed para el transporte.
"""

from __future__ import annotations

from typing import Any

from gspreadmanager.ports.dataframe import DataFramePort
from gspreadmanager.ports.sheets import WorksheetPort


class DataframeService:
    """Casos de uso de lectura/escritura de DataFrames."""

    def __init__(self, frames: DataFramePort) -> None:
        """Recibe el adaptador de DataFrame (puerto) a usar."""
        self._frames = frames

    def from_rows(self, header: list[str], rows: list[list[Any]]) -> Any:
        """Construye un DataFrame a partir de un encabezado y filas."""
        return self._frames.from_rows(header, rows)

    def write(
        self,
        worksheet: WorksheetPort,
        df: Any,
        include_header: bool,
        clear: bool,
        value_input_option: str,
    ) -> Any:
        """Escribe ``df`` en la hoja desde A1 (limpiándola antes si ``clear``)."""
        values = self._frames.to_rows(df, include_header)
        if clear:
            worksheet.clear()
        return worksheet.update(values, value_input_option)
