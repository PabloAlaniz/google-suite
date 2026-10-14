"""Value object: color RGBA."""

from __future__ import annotations

import re
from dataclasses import dataclass

from gsuite_sheets.engine.domain.errors import InvalidColorError

# '#RRGGBB' o 'RRGGBB', solo dígitos hexadecimales ASCII (sin signos, espacios ni '#' repetidos).
_HEX_RGB = re.compile(r"#?([0-9A-Fa-f]{6})")


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
        """Crea un Color desde un hex tipo '#RRGGBB' o 'RRGGBB'.

        Cualquier otra forma (dígitos no hexadecimales o no ASCII, signos, espacios,
        varios '#') lanza ``InvalidColorError``.
        """
        match = _HEX_RGB.fullmatch(hex_color)
        if match is None:
            raise InvalidColorError(f"Color hex inválido: {hex_color!r} (se espera RRGGBB).")
        h = match.group(1)
        r, g, b = (int(h[i : i + 2], 16) / 255 for i in (0, 2, 4))
        return cls(red=r, green=g, blue=b)
