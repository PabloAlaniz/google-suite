"""Servicio de datos: lectura, escritura, append, inserción y consultas.

Opera sobre ``WorksheetPort`` / ``SpreadsheetPort`` (no conoce gspread). Aquí vive la
orquestación y la lógica de transformación, testeable con fakes de los puertos.
"""

from __future__ import annotations

from typing import Any

from gspreadmanager.config import DEFAULT_VALUE_INPUT_OPTION
from gspreadmanager.domain.errors import InsertError
from gspreadmanager.domain.values import rowcol_to_a1
from gspreadmanager.ports.sheets import SpreadsheetPort, WorksheetPort


class DataService:
    """Casos de uso de lectura/escritura de datos sobre una hoja."""

    def update_cell(self, worksheet: WorksheetPort, row: int, col: int, value: Any) -> None:
        """Actualiza una celda (índices 1-based)."""
        worksheet.update_cell(row, col, value)

    def update_row(
        self, worksheet: WorksheetPort, row: int, data: list[Any], start_column: int | None = None
    ) -> None:
        """Actualiza una fila celda por celda desde ``start_column`` (o la primera)."""
        for index, value in enumerate(data, start=(start_column or 1)):
            worksheet.update_cell(row, index, value)

    def read_values(
        self,
        worksheet: WorksheetPort,
        skiprows: int = 0,
        value_render_option: str | None = None,
    ) -> list[list[str]]:
        """Devuelve todas las filas de la hoja, omitiendo las primeras ``skiprows``.

        ``value_render_option``: ``"FORMATTED_VALUE"``, ``"UNFORMATTED_VALUE"`` o
        ``"FORMULA"`` (None usa el default de la API: formateado).
        """
        return worksheet.get_all_values(value_render_option)[skiprows:]

    def read_page(self, worksheet: WorksheetPort, start_row: int, end_row: int) -> list[list[str]]:
        """Lee las filas ``[start_row, end_row]`` (1-based, inclusivo) vía ``values_get``.

        Es la pieza de paginación de ``iter_rows``: la API omite las filas vacías al final
        del rango, así que una página corta indica el fin de los datos.
        """
        a1 = f"{worksheet.title}!{start_row}:{end_row}"
        data = worksheet.spreadsheet.values_get(a1)
        rows: list[list[str]] = data.get("values", []) if isinstance(data, dict) else []
        return rows

    def import_rows(self, worksheet: WorksheetPort, rows: list[list[str]], clear: bool) -> Any:
        """Vuelca ``rows`` (ej. parseadas de un CSV) desde A1, limpiando antes si ``clear``."""
        if clear:
            worksheet.clear()
        return worksheet.update(rows, "RAW")

    def as_dicts(self, rows: list[list[str]]) -> list[dict[str, str]]:
        """Convierte filas (con encabezado en la primera) en lista de diccionarios."""
        if not rows:
            return []
        headers = rows[0]
        return [dict(zip(headers, row)) for row in rows[1:]]

    def last_row(self, worksheet: WorksheetPort) -> int:
        """Devuelve el índice (1-based) de la última fila con datos; 0 si está vacía."""
        return len(worksheet.get_all_values())

    def rows_where_column_equals(
        self, worksheet: WorksheetPort, column: int, value: Any
    ) -> list[tuple[int, list[str]]]:
        """Devuelve ``(nro_fila, fila)`` para las filas cuya columna ``column`` es ``value``."""
        result: list[tuple[int, list[str]]] = []
        for index, row in enumerate(worksheet.get_all_values(), start=1):
            if len(row) > column and row[column] == value:
                result.append((index, row))
        return result

    def append(
        self, worksheet: WorksheetPort, data: list[list[Any]], value_input_option: str
    ) -> Any:
        """Añade filas al final de la hoja."""
        return worksheet.append_rows(data, value_input_option)

    def batch_update(
        self, worksheet: WorksheetPort, range_data: list[dict[str, Any]], value_input_option: str
    ) -> None:
        """Actualiza varios rangos en una sola petición."""
        worksheet.batch_update(range_data, value_input_option)

    def read_range(
        self, spreadsheet: SpreadsheetPort, a1_range: str, first_row: int
    ) -> list[dict[str, Any]]:
        """Lee un rango A1 y devuelve ``{'fila': nro, 'values': [...]}`` por fila."""
        data = spreadsheet.values_get(a1_range)
        content: list[dict[str, Any]] = []
        if "values" in data:
            row_number = first_row
            for row_values in data["values"]:
                content.append({"fila": row_number, "values": row_values})
                row_number += 1
        return content

    def row_with_empty_in_column(
        self, worksheet: WorksheetPort, column_letter: str
    ) -> tuple[list[Any] | None, int | None]:
        """Encuentra la primera fila con celda vacía en una columna; ``(None, None)`` si no hay."""
        total_rows = len(worksheet.col_values(1))
        cells = worksheet.range(f"{column_letter}1:{column_letter}{total_rows}")
        column_values = [cell.value for cell in cells]
        try:
            empty_index = column_values.index("") + 1
        except ValueError:
            return None, None
        return worksheet.row_values(empty_index), empty_index

    def insert(
        self,
        worksheet: WorksheetPort,
        worksheet_name: str,
        data: list[list[Any]],
        first_row: int | None = None,
    ) -> Any:
        """Inserta ``data`` en ``first_row`` (o al final), validando lista de listas homogénea."""
        if not all(isinstance(row, list) for row in data):
            raise ValueError("Los datos deben ser una lista de listas.")
        if not all(len(row) == len(data[0]) for row in data):
            raise ValueError("Todas las filas de datos deben tener la misma longitud.")

        # Si no se especifica la fila, insertar al final.
        if first_row is None:
            first_row = len(worksheet.get_all_values()) + 1
        last = first_row + len(data) - 1
        num_cols = len(data[0])
        # rowcol_to_a1 soporta correctamente más de 26 columnas (más allá de Z).
        a1_range = f"{worksheet_name}!{rowcol_to_a1(first_row, 1)}:{rowcol_to_a1(last, num_cols)}"

        try:
            params = {"valueInputOption": DEFAULT_VALUE_INPUT_OPTION}
            return worksheet.spreadsheet.values_append(a1_range, params, {"values": data})
        except Exception as exc:
            raise InsertError(f"Error al insertar datos en {worksheet_name}: {exc}") from exc
