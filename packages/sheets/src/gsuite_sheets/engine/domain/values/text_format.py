"""Value object: formato de texto."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ._serialization import compact
from .color import Color


@dataclass(frozen=True)
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
        return compact(
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
