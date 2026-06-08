"""Shim de compatibilidad: el modelo de formato vive ahora en ``domain.values``.

Re-exporta los value objects públicos para mantener estable el módulo
``gspreadmanager.formatting``. El código nuevo debería importar desde el paquete raíz
(``from gspreadmanager import CellFormat``) o desde ``gspreadmanager.domain.values``.
"""

from __future__ import annotations

from .domain.values.border import Border, Borders
from .domain.values.cell_format import CellFormat
from .domain.values.color import Color
from .domain.values.number_format import NumberFormat
from .domain.values.text_format import TextFormat

__all__ = ["Border", "Borders", "CellFormat", "Color", "NumberFormat", "TextFormat"]
