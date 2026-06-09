"""Value objects: rangos e identificadores de Google Sheets.

Modelan el direccionamiento (rango A1, GridRange, id de documento, referencia a
pestaña) como objetos inmutables. La conversión A1 -> GridRange depende del id de la
hoja y de gspread, por lo que vive en la capa de infraestructura; aquí ``GridRange``
es un contenedor tipado con ``to_dict()`` / ``from_dict()``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from gspreadmanager.domain.errors import InvalidIdentifierError, InvalidRangeError

# Ancla A1: una celda (A1), una columna (A) o una fila (1).
_A1_ANCHOR = r"(?:[A-Za-z]{1,3}[1-9][0-9]*|[A-Za-z]{1,3}|[1-9][0-9]*)"
_A1_PATTERN = re.compile(rf"{_A1_ANCHOR}(?::{_A1_ANCHOR})?")


@dataclass(frozen=True)
class A1Range:
    """Rango en notación A1 sin prefijo de pestaña (ej. 'A1', 'A1:C10', 'A:A', '1:1')."""

    value: str

    def __post_init__(self) -> None:
        """Valida que ``value`` tenga forma de rango A1."""
        if not _A1_PATTERN.fullmatch(self.value):
            raise InvalidRangeError(f"Rango A1 inválido: {self.value!r}.")

    def with_sheet(self, sheet_name: str) -> str:
        """Antepone el nombre de pestaña: ``'Hoja1!A1:C10'``."""
        return f"{sheet_name}!{self.value}"

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
