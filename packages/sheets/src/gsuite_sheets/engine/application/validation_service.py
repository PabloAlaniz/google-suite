"""Servicio de validación de datos y formato condicional.

Construye las reglas (value objects del dominio) y las aplica vía
``spreadsheets.batchUpdate``. Recibe el ``GridRange`` ya resuelto (la conversión A1 ->
GridRange depende de gspread y vive en infraestructura/conector).
"""

from __future__ import annotations

from typing import Any

from gspreadmanager.domain.values import (
    CellFormat,
    Condition,
    ConditionalFormatRule,
    DataValidationRule,
    GridRange,
)


class ValidationService:
    """Casos de uso de validación de datos y formato condicional."""

    def set_data_validation(
        self,
        worksheet: Any,
        grid_range: GridRange,
        condition_type: str,
        values: list[Any] | None,
        strict: bool,
        show_custom_ui: bool,
    ) -> Any:
        """Aplica una regla de validación de datos sobre ``grid_range``."""
        rule = DataValidationRule(
            condition=Condition.of(condition_type, values),
            strict=strict,
            show_custom_ui=show_custom_ui,
        )
        return self._apply(worksheet, rule.to_request(grid_range))

    def add_conditional_format(
        self,
        worksheet: Any,
        grid_range: GridRange,
        condition_type: str,
        values: list[Any],
        cell_format: CellFormat,
        index: int,
    ) -> Any:
        """Agrega una regla de formato condicional booleana sobre ``grid_range``."""
        rule = ConditionalFormatRule(
            condition=Condition.of(condition_type, values),
            cell_format=cell_format,
            index=index,
        )
        return self._apply(worksheet, rule.to_request(grid_range))

    def _apply(self, worksheet: Any, request: dict[str, Any]) -> Any:
        """Envía una petición vía ``spreadsheets.batchUpdate``."""
        return worksheet.spreadsheet.batch_update({"requests": [request]})
