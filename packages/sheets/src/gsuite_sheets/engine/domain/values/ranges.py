"""Value objects: rangos e identificadores de Google Sheets.

Modelan el direccionamiento (rango A1, GridRange, id de documento, referencia a
pestaña) como objetos inmutables, junto con las conversiones puras de notación A1
(``rowcol_to_a1``, ``column_to_letter``, ``GridRange.from_a1``) — lógica de dominio
sin dependencias de infraestructura.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from gsuite_core.exceptions import ValidationError
from gsuite_sheets import a1 as _a1
from gsuite_sheets.engine.domain.errors import InvalidIdentifierError, InvalidRangeError

# Ancla A1: una celda (A1), una columna (A) o una fila (1).
_A1_ANCHOR = r"(?:[A-Za-z]{1,3}[1-9][0-9]*|[A-Za-z]{1,3}|[1-9][0-9]*)"
_A1_PATTERN = re.compile(rf"{_A1_ANCHOR}(?::{_A1_ANCHOR})?")

_A1_CELL = re.compile(r"^([A-Za-z]*)([0-9]*)$")


def column_to_letter(col: int) -> str:
    """Convierte un índice de columna 1-based a letras ('A', 'Z', 'AA', ...)."""
    if col < 1:
        raise InvalidRangeError(f"Columna inválida: {col} (debe ser >= 1).")
    return _a1.column_letter(col - 1)


def letter_to_column(letters: str) -> int:
    """Convierte letras de columna ('A', 'AA') a su índice 1-based."""
    return _a1.column_index(letters) + 1


def rowcol_to_a1(row: int, col: int) -> str:
    """Convierte (fila, columna) 1-based a notación A1 (ej. (2, 3) -> 'C2')."""
    if row < 1:
        raise InvalidRangeError(f"Fila inválida: {row} (debe ser >= 1).")
    return f"{column_to_letter(col)}{row}"


@dataclass(frozen=True)
class A1Range:
    """Rango en notación A1 sin prefijo de pestaña (ej. 'A1', 'A1:C10', 'A:A', '1:1')."""

    value: str

    def __post_init__(self) -> None:
        """Valida que ``value`` tenga forma de rango A1."""
        if not _A1_PATTERN.fullmatch(self.value):
            raise InvalidRangeError(f"Rango A1 inválido: {self.value!r}.")

    def with_sheet(self, sheet_name: str) -> str:
        """Antepone el nombre de pestaña, entre comillas: ``"'Hoja 1'!A1:C10"``."""
        return _a1.a1(sheet_name, self.value)

    def __str__(self) -> str:
        """Devuelve la notación A1 cruda."""
        return self.value


@dataclass(frozen=True)
class GridRange:
    """GridRange de la Sheets API: índices 0-based, fin exclusivo, sobre ``sheet_id``."""

    sheet_id: int
    start_row_index: int | None = None
    end_row_index: int | None = None
    start_column_index: int | None = None
    end_column_index: int | None = None

    def to_dict(self) -> dict[str, int]:
        """Serializa al objeto ``GridRange`` (omite los límites ausentes)."""
        data: dict[str, int] = {"sheetId": self.sheet_id}
        if self.start_row_index is not None:
            data["startRowIndex"] = self.start_row_index
        if self.end_row_index is not None:
            data["endRowIndex"] = self.end_row_index
        if self.start_column_index is not None:
            data["startColumnIndex"] = self.start_column_index
        if self.end_column_index is not None:
            data["endColumnIndex"] = self.end_column_index
        return data

    @classmethod
    def from_dict(cls, data: dict[str, int]) -> GridRange:
        """Construye desde un dict ``GridRange`` (ej. el que devuelve gspread)."""
        return cls(
            sheet_id=data["sheetId"],
            start_row_index=data.get("startRowIndex"),
            end_row_index=data.get("endRowIndex"),
            start_column_index=data.get("startColumnIndex"),
            end_column_index=data.get("endColumnIndex"),
        )

    def overlaps(self, other: GridRange) -> bool:
        """True si ambos rangos se intersecan (límites ``None`` = sin tope en ese eje).

        Compara solo la geometría: ignora ``sheet_id`` (quien compara decide si las hojas
        coinciden).
        """

        def axis(s1: int | None, e1: int | None, s2: int | None, e2: int | None) -> bool:
            start1, start2 = s1 or 0, s2 or 0
            return (e2 is None or start1 < e2) and (e1 is None or start2 < e1)

        rows = axis(
            self.start_row_index, self.end_row_index, other.start_row_index, other.end_row_index
        )
        cols = axis(
            self.start_column_index,
            self.end_column_index,
            other.start_column_index,
            other.end_column_index,
        )
        return rows and cols

    @classmethod
    def from_a1(cls, a1_range: str, sheet_id: int) -> GridRange:
        """Convierte un rango A1 en un ``GridRange`` (0-based, fin exclusivo) para ``sheet_id``.

        Soporta celdas ('A1'), rangos ('A1:C10'), columnas ('A:C'), filas ('1:5') y rangos
        abiertos ('A2:C'); ignora el prefijo de pestaña, también entre comillas. Delega en
        ``gsuite_sheets.a1.grid_range``, la única implementación de A1 de la suite.
        """
        try:
            return cls.from_dict(_a1.grid_range(a1_range, sheet_id))
        except ValidationError as exc:
            raise InvalidRangeError(f"Rango A1 inválido: {a1_range!r}.") from exc


_URL_KEY_PATTERN = re.compile(r"/spreadsheets/d/([a-zA-Z0-9-_]+)")


@dataclass(frozen=True)
class SpreadsheetId:
    """Identificador (fileId de Drive) de un documento de Google Sheets."""

    value: str

    def __post_init__(self) -> None:
        """Valida que el identificador no esté vacío."""
        if not self.value.strip():
            raise InvalidIdentifierError("SpreadsheetId no puede estar vacío.")

    @classmethod
    def from_url(cls, url: str) -> SpreadsheetId:
        """Extrae el id de una URL tipo ``https://docs.google.com/spreadsheets/d/<id>/edit``."""
        match = _URL_KEY_PATTERN.search(url)
        if not match:
            raise InvalidIdentifierError(f"No se pudo extraer el id de la URL: {url!r}.")
        return cls(match.group(1))

    def __str__(self) -> str:
        """Devuelve el identificador crudo."""
        return self.value


@dataclass(frozen=True)
class WorksheetRef:
    """Referencia inmutable a una pestaña: nombre de documento + pestaña opcional."""

    doc_name: str
    tab_name: str | None = None

    def __post_init__(self) -> None:
        """Valida que el nombre de documento no esté vacío."""
        if not self.doc_name.strip():
            raise InvalidIdentifierError("doc_name no puede estar vacío.")
