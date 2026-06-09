"""Servicio de integración con DataFrames.

Orquesta la lectura/escritura de DataFrames usando un ``DataFramePort`` inyectado (sin
conocer pandas) y una hoja duck-typed para el transporte.
"""

from __future__ import annotations

from typing import Any

from gspreadmanager.domain.dataframe import prune_empty
from gspreadmanager.ports.dataframe import DataFramePort
from gspreadmanager.ports.sheets import WorksheetPort


class DataframeService:
    """Casos de uso de lectura/escritura de DataFrames."""

    def __init__(self, frames: DataFramePort) -> None:
        """Recibe el adaptador de DataFrame (puerto) a usar."""
        self._frames = frames

    def from_rows(
        self,
        header: list[str],
        rows: list[list[Any]],
        *,
        index_col: str | None = None,
        drop_empty_rows: bool = False,
        drop_empty_cols: bool = False,
    ) -> Any:
        """Construye un DataFrame, limpiando filas/columnas vacías si se pide."""
        header, rows = prune_empty(
            header, rows, drop_empty_rows=drop_empty_rows, drop_empty_cols=drop_empty_cols
        )
        return self._frames.from_rows(header, rows, index_col=index_col)

    def write(
        self,
        worksheet: WorksheetPort,
        df: Any,
        include_header: bool,
        clear: bool,
        value_input_option: str,
        *,
        include_index: bool = False,
        start_cell: str | None = None,
    ) -> Any:
        """Escribe ``df`` en la hoja (desde A1 o ``start_cell``), limpiándola antes si ``clear``."""
        values = self._frames.to_rows(df, include_header, include_index=include_index)
        if clear:
            worksheet.clear()
        return worksheet.update(values, value_input_option, range_name=start_cell)
