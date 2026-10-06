"""Tests de inferencia de tipos (``domain.numericise``)."""

import pytest
from gspreadmanager.domain.numericise import numericise, numericise_all, numericise_records


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
    ],
)
def test_numericise(value, expected):
    assert numericise(value) == expected


def test_empty_to_zero():
    assert numericise("", empty_to_zero=True) == 0


def test_default_blank():
    assert numericise("", default_blank=None) is None


def test_numericise_all():
    assert numericise_all([["1", "x"], ["2.5", "007"]]) == [[1, "x"], [2.5, "007"]]


def test_numericise_records_keeps_keys():
    records = [{"edad": "30", "nombre": "Ana"}]
    assert numericise_records(records) == [{"edad": 30, "nombre": "Ana"}]
