"""Value object: formato completo de una celda."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ._serialization import compact
from .border import Borders
from .color import Color
from .number_format import NumberFormat
from .text_format import TextFormat


@dataclass(frozen=True)
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
        return compact(
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
