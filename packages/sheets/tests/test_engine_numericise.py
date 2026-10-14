"""Tests de inferencia de tipos (``domain.numericise``)."""

import pytest

from gsuite_sheets.engine.domain.numericise import numericise, numericise_all, numericise_records


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("3", 3),
        ("-7", -7),
        ("1.5", 1.5),
        ("abc", "abc"),
        ("", ""),
        ("007", "007"),  # preserva ceros a la izquierda
        ("0", 0),
        ("3.0", 3.0),
        (42, 42),  # no-string pasa igual
        (" 7 ", 7),  # se toleran espacios alrededor
        ("1e3", 1000.0),
        ("-0", 0),
    ],
)
def test_numericise(value, expected):
    assert numericise(value) == expected


@pytest.mark.parametrize(
    "value",
    [
        "-007",  # ceros a la izquierda con signo
        "+007",
        " 007",  # ceros a la izquierda con espacios
        "00",
        "1_000",  # Python acepta guiones bajos; Sheets no
        "\u0663",  # dígito arábigo-índico: no ASCII
        "\uff11\uff12",  # dígitos de ancho completo
        "nan",
        "-inf",
        "Infinity",
        "1e999",  # desborda a infinito
    ],
)
def test_non_canonical_numbers_stay_text(value):
    assert numericise(value) is value


def test_empty_to_zero():
    assert numericise("", empty_to_zero=True) == 0


def test_default_blank():
    assert numericise("", default_blank=None) is None


def test_numericise_all():
    assert numericise_all([["1", "x"], ["2.5", "007"]]) == [[1, "x"], [2.5, "007"]]


def test_numericise_records_keeps_keys():
    records = [{"edad": "30", "nombre": "Ana"}]
    assert numericise_records(records) == [{"edad": 30, "nombre": "Ana"}]
