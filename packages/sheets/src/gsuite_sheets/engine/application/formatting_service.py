"""Servicio de formato: aplicar formato, congelar e combinar celdas.

Las operaciones de transporte (``format``/``freeze``/``merge_cells``) operan sobre una
hoja duck-typed; los builders devuelven value objects ``CellFormat`` del dominio.
"""

from __future__ import annotations

from typing import Any

from gspreadmanager.domain.values import CellFormat, Color, NumberFormat, TextFormat


class FormattingService:
    """Casos de uso de formato de celdas sobre una hoja."""

    def apply(self, worksheet: Any, ranges: str | list[str], cell_format: CellFormat) -> Any:
        """Aplica ``cell_format`` a uno o más rangos."""
        return worksheet.format(ranges, cell_format.to_dict())

    def freeze(self, worksheet: Any, rows: int | None, cols: int | None) -> Any:
        """Congela ``rows`` filas y/o ``cols`` columnas."""
        return worksheet.freeze(rows=rows, cols=cols)

    def merge(self, worksheet: Any, range_name: str, merge_type: str) -> Any:
        """Combina las celdas de un rango (``MERGE_ALL``/``MERGE_COLUMNS``/``MERGE_ROWS``)."""
        return worksheet.merge_cells(range_name, merge_type=merge_type)

    def header_format(self, background_hex: str | None) -> CellFormat:
        """Construye el formato de encabezado (negrita + color de fondo opcional)."""
        return CellFormat(
            text_format=TextFormat(bold=True),
            background_color=Color.from_hex(background_hex) if background_hex else None,
        )

    def text_format(
        self,
        *,
        bold: bool | None = None,
        italic: bool | None = None,
        font_size: int | None = None,
        color: Color | None = None,
    ) -> CellFormat:
        """Construye un formato de texto (negrita, itálica, tamaño, color)."""
        text = TextFormat(bold=bold, italic=italic, font_size=font_size, foreground_color=color)
        return CellFormat(text_format=text)

    def number_format(self, pattern: str, number_type: str) -> CellFormat:
        """Construye un formato numérico (patrón + tipo)."""
        return CellFormat(number_format=NumberFormat(type=number_type, pattern=pattern))
