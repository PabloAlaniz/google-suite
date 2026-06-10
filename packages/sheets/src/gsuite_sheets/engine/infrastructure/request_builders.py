"""Conversión de rangos A1 a ``GridRange`` del dominio.

Resuelve un rango A1 a su ``GridRange`` (con el id de la hoja) usando la conversión pura
del dominio — sin gspread. El armado de las peticiones de validación / formato condicional
lo hacen los value objects del dominio (``to_request``).
"""

from __future__ import annotations

from gspreadmanager.domain.values import GridRange


def grid_range(range_name: str, sheet_id: int) -> GridRange:
    """Convierte un rango A1 en un ``GridRange`` del dominio para ``sheet_id``."""
    return GridRange.from_a1(range_name, sheet_id)
