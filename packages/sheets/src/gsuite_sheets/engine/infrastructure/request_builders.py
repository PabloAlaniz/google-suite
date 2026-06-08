"""Conversión de rangos A1 a ``GridRange`` del dominio.

Aísla la dependencia de gspread (``a1_range_to_grid_range``) para resolver un rango A1
a su ``GridRange`` (con el id de la hoja). El armado de las peticiones de validación /
formato condicional lo hacen los value objects del dominio (``to_request``).
"""

from __future__ import annotations

from gspread.utils import a1_range_to_grid_range

from gspreadmanager.domain.values import GridRange


def grid_range(range_name: str, sheet_id: int) -> GridRange:
    """Convierte un rango A1 en un ``GridRange`` del dominio para ``sheet_id``."""
    return GridRange.from_dict(a1_range_to_grid_range(range_name, sheet_id))
