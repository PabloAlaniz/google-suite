"""Modelo propio de formato de celdas para Google Sheets.

Implementación independiente (sin `gspread-formatting`): define dataclasses tipadas que
serializan a la forma JSON que espera la Google Sheets API (objeto ``CellFormat`` y afines).
El envío de las peticiones lo realiza el conector usando gspread como transporte.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Longitud esperada de un color hexadecimal sin prefijo (RRGGBB).
_HEX_RGB_LENGTH = 6


def _compact(data: dict[str, Any]) -> dict[str, Any]:
    """Elimina las claves con valor None (la API rechaza nulos en varios campos)."""
    return {k: v for k, v in data.items() if v is not None}


@dataclass
class Color:
    """Color RGBA con componentes en el rango 0.0-1.0."""

    red: float = 0.0
    green: float = 0.0
    blue: float = 0.0
    alpha: float = 1.0

    def to_dict(self) -> dict[str, float]:
        """Serializa a la forma JSON ``{red, green, blue, alpha}``."""
        return {"red": self.red, "green": self.green, "blue": self.blue, "alpha": self.alpha}

    @classmethod
    def from_hex(cls, hex_color: str) -> Color:
        """Crea un Color desde un hex tipo '#RRGGBB' o 'RRGGBB'."""
        h = hex_color.lstrip("#")
        if len(h) != _HEX_RGB_LENGTH:
            raise ValueError(f"Color hex inválido: {hex_color!r} (se espera RRGGBB).")
        r, g, b = (int(h[i : i + 2], 16) / 255 for i in (0, 2, 4))
        return cls(red=r, green=g, blue=b)


@dataclass
class TextFormat:
    """Formato de texto (negrita, itálica, tamaño, color, etc.)."""

    bold: bool | None = None
    italic: bool | None = None
    strikethrough: bool | None = None
    underline: bool | None = None
    font_size: int | None = None
    font_family: str | None = None
    foreground_color: Color | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serializa al objeto ``textFormat`` de la Sheets API (omite campos None)."""
        return _compact(
            {
                "bold": self.bold,
                "italic": self.italic,
                "strikethrough": self.strikethrough,
                "underline": self.underline,
                "fontSize": self.font_size,
                "fontFamily": self.font_family,
                "foregroundColor": self.foreground_color.to_dict()
                if self.foreground_color
                else None,
            }
        )


@dataclass
class NumberFormat:
    """Formato numérico. ``type`` puede ser NUMBER, CURRENCY, PERCENT, DATE, TIME, etc."""

    type: str
    pattern: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serializa al objeto ``numberFormat`` de la Sheets API."""
        return _compact({"type": self.type, "pattern": self.pattern})


@dataclass
class Border:
    """Borde de celda. ``style``: SOLID, SOLID_MEDIUM, SOLID_THICK, DOTTED, DASHED, DOUBLE."""

    style: str = "SOLID"
    color: Color | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serializa al objeto ``border`` de la Sheets API."""
        return _compact(
            {"style": self.style, "color": self.color.to_dict() if self.color else None}
        )


@dataclass
class Borders:
    """Conjunto de bordes (arriba, abajo, izquierda, derecha)."""

    top: Border | None = None
    bottom: Border | None = None
    left: Border | None = None
    right: Border | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serializa al conjunto de bordes de la Sheets API (omite los None)."""
        return _compact(
            {
                "top": self.top.to_dict() if self.top else None,
                "bottom": self.bottom.to_dict() if self.bottom else None,
                "left": self.left.to_dict() if self.left else None,
                "right": self.right.to_dict() if self.right else None,
            }
        )


@dataclass
class CellFormat:
    """Formato completo de una celda. Serializa al objeto CellFormat de la Sheets API."""

    background_color: Color | None = None
    text_format: TextFormat | None = None
    number_format: NumberFormat | None = None
    horizontal_alignment: str | None = None  # LEFT, CENTER, RIGHT
    vertical_alignment: str | None = None  # TOP, MIDDLE, BOTTOM
    wrap_strategy: str | None = None  # OVERFLOW_CELL, CLIP, WRAP
    borders: Borders | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serializa al objeto ``cellFormat`` de la Sheets API (omite campos None)."""
        return _compact(
            {
                "backgroundColor": self.background_color.to_dict()
                if self.background_color
                else None,
                "textFormat": self.text_format.to_dict() if self.text_format else None,
                "numberFormat": self.number_format.to_dict() if self.number_format else None,
                "horizontalAlignment": self.horizontal_alignment,
                "verticalAlignment": self.vertical_alignment,
                "wrapStrategy": self.wrap_strategy,
                "borders": self.borders.to_dict() if self.borders else None,
            }
        )
