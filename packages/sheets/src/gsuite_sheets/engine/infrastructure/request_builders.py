"""Construcción de peticiones para ``spreadsheets.batchUpdate``.

Aísla del dominio la dependencia de gspread para convertir rangos A1 a ``GridRange``
(``a1_range_to_grid_range``) y arma las peticiones a partir de los value objects del
dominio (``DataValidationRule``, ``ConditionalFormatRule``). El dominio define la *forma*
de la petición; este módulo aporta el id de la hoja y el transporte de la conversión.
"""

from __future__ import annotations

from typing import Any

from gspread.utils import a1_range_to_grid_range

from gspreadmanager.domain.values import (
    ConditionalFormatRule,
    DataValidationRule,
    GridRange,
)


def grid_range(range_name: str, sheet_id: int) -> GridRange:
    """Convierte un rango A1 en un ``GridRange`` del dominio para ``sheet_id``."""
    return GridRange.from_dict(a1_range_to_grid_range(range_name, sheet_id))


def data_validation_request(
    rule: DataValidationRule, range_name: str, sheet_id: int
) -> dict[str, Any]:
    """Arma la petición ``setDataValidation`` para ``range_name`` en ``sheet_id``."""
    return rule.to_request(grid_range(range_name, sheet_id))


def conditional_format_request(
    rule: ConditionalFormatRule, range_name: str, sheet_id: int
) -> dict[str, Any]:
    """Arma la petición ``addConditionalFormatRule`` para ``range_name`` en ``sheet_id``."""
    return rule.to_request(grid_range(range_name, sheet_id))
