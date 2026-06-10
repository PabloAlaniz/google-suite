"""Servicio de tabla: tratar la hoja como una tabla con encabezado y clave.

Operaciones de alto nivel sobre ``WorksheetPort``: upsert por columna clave, update y
delete condicionales. La fila 1 se asume encabezado; las filas se manipulan como
registros ``{columna: valor}``.

La **planificación** (qué rangos escribir / qué filas borrar) son funciones puras de
módulo (``plan_upsert``/``plan_update_where``/``plan_delete_requests``): las comparte la
facade async, que hace el IO con sus propios puertos. Las escrituras grandes se parten
con ``domain.batching`` (un rango/fila nunca se parte).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Union

from gspreadmanager.domain.batching import split_range_data, split_rows
from gspreadmanager.domain.errors import GSpreadManagerError
from gspreadmanager.domain.values import rowcol_to_a1
from gspreadmanager.ports.sheets import WorksheetPort

# Filtro de filas: dict de igualdades {columna: valor} o un predicado sobre el registro.
Where = Union[dict[str, Any], Callable[[dict[str, str]], bool]]

_MISSING = object()


def require_header(values: list[list[str]]) -> tuple[list[str], list[list[str]]]:
    """Separa ``values`` en (encabezado, datos); error de dominio si no hay encabezado."""
    if not values or not any(cell != "" for cell in values[0]):
        raise GSpreadManagerError("La hoja no tiene encabezado (fila 1) para operar como tabla.")
    return values[0], values[1:]


def column_position(header: list[str], column: str) -> int:
    """Posición 1-based de ``column`` en el encabezado (error de dominio si falta)."""
    try:
        return header.index(column) + 1
    except ValueError:
        raise GSpreadManagerError(
            f"La columna '{column}' no está en el encabezado: {header}."
        ) from None


def as_record(item: dict[str, Any] | list[Any], header: list[str]) -> dict[str, Any]:
    """Normaliza una fila de entrada a registro ``{columna: valor}``."""
    if isinstance(item, dict):
        for column in item:
            column_position(header, column)
        return item
    if len(item) > len(header):
        raise GSpreadManagerError(
            f"La fila tiene {len(item)} valores y el encabezado {len(header)} columnas."
        )
    return dict(zip(header, item))


def row_record(header: list[str], row: list[str]) -> dict[str, str]:
    """Registro ``{columna: valor}`` de una fila de la hoja (con padding al encabezado)."""
    padded = row + [""] * (len(header) - len(row))
    return dict(zip(header, padded))


def row_updates(
    record: dict[str, Any], header: list[str], row_number: int
) -> list[dict[str, Any]]:
    """Rangos de actualización para una fila.

    La fila completa (un solo rango) si el registro cubre todo el encabezado; una
    celda por columna presente si es parcial.
    """
    provided = [record.get(column, _MISSING) for column in header]
    if all(value is not _MISSING for value in provided):
        last = rowcol_to_a1(row_number, len(header))
        return [{"range": f"A{row_number}:{last}", "values": [provided]}]
    return [
        {"range": rowcol_to_a1(row_number, position), "values": [[value]]}
        for position, value in enumerate(provided, start=1)
        if value is not _MISSING
    ]


def build_predicate(where: Where, header: list[str]) -> Callable[[dict[str, str]], bool]:
    """Convierte ``where`` (dict de igualdades o callable) en un predicado de registro."""
    if callable(where):
        return where
    for column in where:
        column_position(header, column)
    filters = {column: str(value) for column, value in where.items()}
    return lambda record: all(record.get(c, "") == v for c, v in filters.items())


def contiguous_descending(rows: list[int]) -> list[tuple[int, int]]:
    """Agrupa números de fila en rangos ``(inicio, fin)`` inclusivos, de abajo hacia arriba."""
    groups: list[tuple[int, int]] = []
    start = end = rows[0]
    for number in rows[1:]:
        if number == end + 1:
            end = number
        else:
            groups.append((start, end))
            start = end = number
    groups.append((start, end))
    return sorted(groups, reverse=True)


def plan_upsert(
    header: list[str],
    values: list[list[str]],
    rows: list[dict[str, Any]] | list[list[Any]],
    key: str,
) -> tuple[list[dict[str, Any]], list[list[Any]], int]:
    """Planifica un upsert: devuelve ``(rangos_a_actualizar, filas_a_agregar, actualizadas)``."""
    key_pos = column_position(header, key)

    row_by_key: dict[str, int] = {}
    for number, row in enumerate(values, start=2):
        cell = row[key_pos - 1] if key_pos - 1 < len(row) else ""
        if cell != "" and cell not in row_by_key:
            row_by_key[cell] = number

    updates: list[dict[str, Any]] = []
    updated_rows = 0
    appends_by_key: dict[str, list[Any]] = {}
    for item in rows:
        record = as_record(item, header)
        if key not in record:
            raise GSpreadManagerError(f"La fila no trae la columna clave '{key}': {item!r}.")
        key_value = str(record[key])
        target = row_by_key.get(key_value)
        if target is None:
            appends_by_key[key_value] = [record.get(column, "") for column in header]
            continue
        updated_rows += 1
        updates.extend(row_updates(record, header, target))
    return updates, list(appends_by_key.values()), updated_rows


def plan_update_where(
    header: list[str],
    values: list[list[str]],
    where: Where,
    updates: dict[str, Any],
) -> tuple[list[dict[str, Any]], int]:
    """Planifica un update condicional: ``(rangos_a_actualizar, filas_afectadas)``."""
    for column in updates:
        column_position(header, column)
    predicate = build_predicate(where, header)

    range_updates: list[dict[str, Any]] = []
    count = 0
    for number, row in enumerate(values, start=2):
        if not predicate(row_record(header, row)):
            continue
        count += 1
        for column, value in updates.items():
            position = column_position(header, column)
            range_updates.append({"range": rowcol_to_a1(number, position), "values": [[value]]})
    return range_updates, count


def plan_delete_requests(
    header: list[str],
    values: list[list[str]],
    where: Where,
    sheet_id: int,
) -> tuple[list[dict[str, Any]], int]:
    """Planifica un delete condicional: ``(requests deleteDimension, filas_a_borrar)``.

    Los rangos van de abajo hacia arriba para que los índices no se corran entre requests.
    """
    predicate = build_predicate(where, header)
    targets = [
        number
        for number, row in enumerate(values, start=2)
        if predicate(row_record(header, row))
    ]
    if not targets:
        return [], 0
    requests = [
        {
            "deleteDimension": {
                "range": {
                    "sheetId": sheet_id,
                    "dimension": "ROWS",
                    "startIndex": start - 1,
                    "endIndex": end,
                }
            }
        }
        for start, end in contiguous_descending(targets)
    ]
    return requests, len(targets)


class TableService:
    """Casos de uso de la hoja como tabla (upsert, update/delete condicional)."""

    def upsert(
        self,
        worksheet: WorksheetPort,
        rows: list[dict[str, Any]] | list[list[Any]],
        key: str,
        value_input_option: str,
        max_cells: int | None = None,
    ) -> dict[str, int]:
        """Actualiza por clave las filas existentes y agrega las nuevas.

        ``rows`` puede ser una lista de dicts ``{columna: valor}`` (solo se actualizan las
        columnas presentes) o de listas alineadas al encabezado. La comparación de claves
        es por su representación de texto (como devuelve la API). Devuelve
        ``{"updated": n, "appended": m}``.
        """
        header, values = require_header(worksheet.get_all_values())
        updates, appends, updated_rows = plan_upsert(header, values, rows, key)
        for chunk in split_range_data(updates, max_cells):
            if chunk:
                worksheet.batch_update(chunk, value_input_option)
        for rows_chunk in split_rows(appends, max_cells):
            if rows_chunk:
                worksheet.append_rows(rows_chunk, value_input_option)
        return {"updated": updated_rows, "appended": len(appends)}

    def update_where(
        self,
        worksheet: WorksheetPort,
        where: Where,
        updates: dict[str, Any],
        value_input_option: str,
        max_cells: int | None = None,
    ) -> int:
        """Aplica ``updates`` (``{columna: valor}``) a las filas que cumplen ``where``.

        ``where`` es un dict de igualdades o un predicado sobre el registro de la fila.
        Devuelve la cantidad de filas afectadas.
        """
        header, values = require_header(worksheet.get_all_values())
        range_updates, count = plan_update_where(header, values, where, updates)
        for chunk in split_range_data(range_updates, max_cells):
            if chunk:
                worksheet.batch_update(chunk, value_input_option)
        return count

    def delete_where(self, worksheet: WorksheetPort, where: Where) -> int:
        """Elimina las filas que cumplen ``where`` (``deleteDimension``); devuelve cuántas."""
        header, values = require_header(worksheet.get_all_values())
        requests, count = plan_delete_requests(header, values, where, worksheet.id)
        if requests:
            worksheet.spreadsheet.batch_update({"requests": requests})
        return count
