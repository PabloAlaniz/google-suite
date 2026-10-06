"""Tests del mapeo de filas a modelos tipados (``domain.schema``)."""

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional

import pytest
from gspreadmanager.domain.errors import SchemaError
from gspreadmanager.domain.schema import models_to_rows, rows_to_models


@dataclass
class Person:
    nombre: str
    edad: int
    activo: bool
    puntaje: float
    email: Optional[str] = None


class TestRowsToModels:
    def test_basic_coercion(self):
        header = ["nombre", "edad", "activo", "puntaje", "email"]
        rows = [["Ana", "30", "TRUE", "9.5", "ana@x.com"]]
        (person,) = rows_to_models(Person, header, rows)
        assert person == Person("Ana", 30, True, 9.5, "ana@x.com")

    def test_optional_empty_becomes_none(self):
        header = ["nombre", "edad", "activo", "puntaje", "email"]
        rows = [["Bob", "25", "FALSE", "0", ""]]
        (person,) = rows_to_models(Person, header, rows)
        assert person.email is None
        assert person.activo is False

    def test_bool_variants(self):
        header = ["nombre", "edad", "activo", "puntaje"]
        rows = [["A", "1", "si", "1"], ["B", "2", "0", "2"]]
        a, b = rows_to_models(Person, header, rows)
        assert a.activo is True
        assert b.activo is False

    def test_missing_cells_treated_as_empty(self):
        header = ["nombre", "edad", "activo", "puntaje", "email"]
        rows = [["Ana", "30", "TRUE", "9.5"]]  # falta email
        (person,) = rows_to_models(Person, header, rows)
        assert person.email is None

    def test_column_order_independent(self):
        header = ["puntaje", "email", "activo", "edad", "nombre"]
        rows = [["9.5", "ana@x.com", "TRUE", "30", "Ana"]]
        (person,) = rows_to_models(Person, header, rows)
        assert person == Person("Ana", 30, True, 9.5, "ana@x.com")

    def test_missing_column_raises(self):
        header = ["nombre", "edad", "activo"]  # falta puntaje
        with pytest.raises(SchemaError, match="puntaje"):
            rows_to_models(Person, header, [["Ana", "30", "TRUE"]])

    def test_invalid_int_raises(self):
        header = ["nombre", "edad", "activo", "puntaje"]
        with pytest.raises(SchemaError, match="edad"):
            rows_to_models(Person, header, [["Ana", "x", "TRUE", "1"]])

    def test_invalid_bool_raises(self):
        header = ["nombre", "edad", "activo", "puntaje"]
        with pytest.raises(SchemaError, match="activo"):
            rows_to_models(Person, header, [["Ana", "1", "quizás", "1"]])

    def test_non_dataclass_raises(self):
        with pytest.raises(SchemaError, match="dataclass"):
            rows_to_models(dict, ["a"], [["1"]])


class TestColumnOverrideAndDates:
    def test_metadata_column_and_dates(self):
        @dataclass
        class Evento:
            titulo: str = field(metadata={"column": "Título"})
            dia: date = field(metadata={"column": "Fecha"})
            creado: datetime = field(metadata={"column": "Creado"})

        header = ["Título", "Fecha", "Creado"]
        rows = [["Lanzamiento", "2026-06-09", "2026-06-09T10:30:00"]]
        (evento,) = rows_to_models(Evento, header, rows)
        assert evento.titulo == "Lanzamiento"
        assert evento.dia == date(2026, 6, 9)
        assert evento.creado == datetime(2026, 6, 9, 10, 30)

    def test_invalid_date_raises(self):
        @dataclass
        class Evento:
            dia: date

        with pytest.raises(SchemaError, match="dia"):
            rows_to_models(Evento, ["dia"], [["no-fecha"]])


class TestModelsToRows:
    def test_header_and_rows(self):
        models = [Person("Ana", 30, True, 9.5, "ana@x.com")]
        header, rows = models_to_rows(models)
        assert header == ["nombre", "edad", "activo", "puntaje", "email"]
        assert rows == [["Ana", 30, "TRUE", 9.5, "ana@x.com"]]

    def test_none_and_bool_and_date_formatting(self):
        @dataclass
        class Row:
            flag: bool
            when: date
            note: Optional[str]

        header, rows = models_to_rows([Row(False, date(2026, 1, 2), None)])
        assert header == ["flag", "when", "note"]
        assert rows == [["FALSE", "2026-01-02", ""]]

    def test_column_override_in_header(self):
        @dataclass
        class Evento:
            titulo: str = field(metadata={"column": "Título"})

        header, _ = models_to_rows([Evento("X")])
        assert header == ["Título"]

    def test_empty_models(self):
        assert models_to_rows([]) == ([], [])
