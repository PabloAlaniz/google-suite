"""Value object: color RGBA."""

from __future__ import annotations

from dataclasses import dataclass

from gspreadmanager.domain.errors import InvalidColorError

# Longitud esperada de un color hexadecimal sin prefijo (RRGGBB).
_HEX_RGB_LENGTH = 6


@dataclass(frozen=True)
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
            raise InvalidColorError(f"Color hex inválido: {hex_color!r} (se espera RRGGBB).")
        r, g, b = (int(h[i : i + 2], 16) / 255 for i in (0, 2, 4))
        return cls(red=r, green=g, blue=b)
