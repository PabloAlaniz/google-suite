"""Servicio de tabla: tratar la hoja como una tabla con encabezado y clave.

Operaciones de alto nivel sobre ``WorksheetPort``: upsert por columna clave, update y
delete condicionales. La fila 1 se asume encabezado; las filas se manipulan como
registros ``{columna: valor}``. Las escrituras grandes se parten con los helpers de
``domain.batching`` (un rango/fila nunca se parte).
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
        header, values = self._header_and_values(worksheet)
        key_pos = self._column_position(header, key)

        row_by_key: dict[str, int] = {}
        for number, row in enumerate(values, start=2):
            cell = row[key_pos - 1] if key_pos - 1 < len(row) else ""
            if cell != "" and cell not in row_by_key:
                row_by_key[cell] = number

        updates: list[dict[str, Any]] = []
        updated_rows = 0
        appends_by_key: dict[str, list[Any]] = {}
        for item in rows:
            record = self._as_record(item, header)
            if key not in record:
                raise GSpreadManagerError(f"La fila no trae la columna clave '{key}': {item!r}.")
            key_value = str(record[key])
            target = row_by_key.get(key_value)
            if target is None:
                appends_by_key[key_value] = [record.get(column, "") for column in header]
                continue
            updated_rows += 1
            updates.extend(self._row_updates(record, header, target))

        for chunk in split_range_data(updates, max_cells):
            if chunk:
                worksheet.batch_update(chunk, value_input_option)
        appends = list(appends_by_key.values())
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
        header, values = self._header_and_values(worksheet)
        for column in updates:
            self._column_position(header, column)
        predicate = self._predicate(where, header)

        range_updates: list[dict[str, Any]] = []
        count = 0
        for number, row in enumerate(values, start=2):
            if not predicate(self._row_record(header, row)):
                continue
            count += 1
            for column, value in updates.items():
                position = self._column_position(header, column)
                range_updates.append(
                    {"range": rowcol_to_a1(number, position), "values": [[value]]}
                )
        for chunk in split_range_data(range_updates, max_cells):
            if chunk:
                worksheet.batch_update(chunk, value_input_option)
        return count

    def delete_where(self, worksheet: WorksheetPort, where: Where) -> int:
        """Elimina las filas que cumplen ``where`` (``deleteDimension``); devuelve cuántas.

        Las filas se agrupan en rangos contiguos y se eliminan de abajo hacia arriba para
        que los índices no se corran entre requests.
        """
        header, values = self._header_and_values(worksheet)
        predicate = self._predicate(where, header)
        targets = [
            number
            for number, row in enumerate(values, start=2)
            if predicate(self._row_record(header, row))
        ]
        if not targets:
            return 0

        requests = [
            {
                "deleteDimension": {
                    "range": {
                        "sheetId": worksheet.id,
                        "dimension": "ROWS",
                        "startIndex": start - 1,
                        "endIndex": end,
                    }
                }
            }
            for start, end in self._contiguous_descending(targets)
        ]
        worksheet.spreadsheet.batch_update({"requests": requests})
        return len(targets)

    # ------------------------------------------------------------------

    def _header_and_values(self, worksheet: WorksheetPort) -> tuple[list[str], list[list[str]]]:
        values = worksheet.get_all_values()
        if not values or not any(cell != "" for cell in values[0]):
            raise GSpreadManagerError(
                "La hoja no tiene encabezado (fila 1) para operar como tabla."
            )
        return values[0], values[1:]

    def _column_position(self, header: list[str], column: str) -> int:
        """Posición 1-based de ``column`` en el encabezado (error de dominio si falta)."""
        try:
            return header.index(column) + 1
        except ValueError:
            raise GSpreadManagerError(
                f"La columna '{column}' no está en el encabezado: {header}."
            ) from None

    def _as_record(
        self, item: dict[str, Any] | list[Any], header: list[str]
    ) -> dict[str, Any]:
        """Normaliza una fila de entrada a registro ``{columna: valor}``."""
        if isinstance(item, dict):
            for column in item:
                self._column_position(header, column)
            return item
        if len(item) > len(header):
            raise GSpreadManagerError(
                f"La fila tiene {len(item)} valores y el encabezado {len(header)} columnas."
            )
        return dict(zip(header, item))

    def _row_record(self, header: list[str], row: list[str]) -> dict[str, str]:
        padded = row + [""] * (len(header) - len(row))
        return dict(zip(header, padded))

    def _row_updates(
        self, record: dict[str, Any], header: list[str], row_number: int
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

    def _predicate(self, where: Where, header: list[str]) -> Callable[[dict[str, str]], bool]:
        if callable(where):
            return where
        for column in where:
            self._column_position(header, column)
        filters = {column: str(value) for column, value in where.items()}
        return lambda record: all(record.get(c, "") == v for c, v in filters.items())

    def _contiguous_descending(self, rows: list[int]) -> list[tuple[int, int]]:
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
