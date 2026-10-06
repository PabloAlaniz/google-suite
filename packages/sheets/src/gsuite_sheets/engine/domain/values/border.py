"""Value objects: bordes de celda."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ._serialization import compact
from .color import Color


@dataclass(frozen=True)
class Border:
    """Borde de celda. ``style``: SOLID, SOLID_MEDIUM, SOLID_THICK, DOTTED, DASHED, DOUBLE."""

    style: str = "SOLID"
    color: Color | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serializa al objeto ``border`` de la Sheets API."""
        return compact({"style": self.style, "color": self.color.to_dict() if self.color else None})


@dataclass(frozen=True)
class Borders:
    """Conjunto de bordes (arriba, abajo, izquierda, derecha)."""

    top: Border | None = None
    bottom: Border | None = None
    left: Border | None = None
    right: Border | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serializa al conjunto de bordes de la Sheets API (omite los None)."""
        return compact(
            {
                "top": self.top.to_dict() if self.top else None,
                "bottom": self.bottom.to_dict() if self.bottom else None,
                "left": self.left.to_dict() if self.left else None,
                "right": self.right.to_dict() if self.right else None,
            }
        )
