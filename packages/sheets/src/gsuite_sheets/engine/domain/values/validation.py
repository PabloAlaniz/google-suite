"""Value objects: reglas de validación de datos y formato condicional.

Modelan las peticiones ``setDataValidation`` y ``addConditionalFormatRule`` de la
Sheets API. ``to_request`` recibe el ``GridRange`` ya resuelto (la conversión A1 ->
GridRange depende del id de la hoja y vive en infraestructura).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from .cell_format import CellFormat
from .ranges import GridRange


@dataclass(frozen=True)
class Condition:
    """Condición booleana de la Sheets API: tipo + valores opcionales.

    Ej. ``ONE_OF_LIST``, ``BOOLEAN``, ``NUMBER_BETWEEN``, ``TEXT_CONTAINS``, …
    """

    type: str
    values: tuple[Any, ...] | None = None

    @classmethod
    def of(cls, condition_type: str, values: Sequence[Any] | None = None) -> Condition:
        """Crea una condición normalizando ``values`` (cualquier secuencia) a tupla."""
        return cls(type=condition_type, values=None if values is None else tuple(values))

    def to_dict(self) -> dict[str, Any]:
        """Serializa al objeto ``BooleanCondition`` (incluye ``values`` solo si los hay)."""
        data: dict[str, Any] = {"type": self.type}
        if self.values is not None:
            data["values"] = [{"userEnteredValue": str(v)} for v in self.values]
        return data


@dataclass(frozen=True)
class DataValidationRule:
    """Regla de validación de datos aplicable a un rango."""

    condition: Condition
    strict: bool = True
    show_custom_ui: bool = True

    def to_rule_dict(self) -> dict[str, Any]:
        """Serializa al objeto ``DataValidationRule`` de la Sheets API."""
        return {
            "condition": self.condition.to_dict(),
            "strict": self.strict,
            "showCustomUi": self.show_custom_ui,
        }

    def to_request(self, grid_range: GridRange) -> dict[str, Any]:
        """Construye la petición ``setDataValidation`` para ``grid_range``."""
        return {
            "setDataValidation": {
                "range": grid_range.to_dict(),
                "rule": self.to_rule_dict(),
            }
        }


@dataclass(frozen=True)
class ConditionalFormatRule:
    """Regla de formato condicional booleana aplicable a un rango."""

    condition: Condition
    cell_format: CellFormat
    index: int = 0

    def to_request(self, grid_range: GridRange) -> dict[str, Any]:
        """Construye la petición ``addConditionalFormatRule`` para ``grid_range``."""
        return {
            "addConditionalFormatRule": {
                "rule": {
                    "ranges": [grid_range.to_dict()],
                    "booleanRule": {
                        "condition": self.condition.to_dict(),
                        "format": self.cell_format.to_dict(),
                    },
                },
                "index": self.index,
            }
        }
