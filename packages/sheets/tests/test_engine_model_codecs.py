"""Tests del Sprint 7 (v2.6): codecs de modelos (dataclasses + Pydantic) y ensure_schema.

Cubren las coerciones nuevas del dominio (Decimal/Enum/Literal), el codec de Pydantic v2
(lectura validada, escritura, alias, upsert e iteración) y la validación/creación de
esquema con reporte de drift.
"""

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Literal, Optional

import pytest
from gspreadmanager import SchemaError
from gspreadmanager.domain.schema import format_cell, rows_to_models
from gspreadmanager.infrastructure.model_codecs import (
    DataclassModelCodec,
    PydanticModelCodec,
)
from gspreadmanager.testing import InMemoryBackend
from pydantic import BaseModel, Field


class Estado(Enum):
    PENDIENTE = "pendiente"
    HECHO = "hecho"


@dataclass
class FilaDc:
    id: int
    monto: Decimal
    estado: Estado
    prioridad: Literal["alta", "baja"]
    nota: Optional[str] = None


class FilaPyd(BaseModel):
    id: int
    nombre: str = Field(alias="nombre completo")
    activo: bool = True


@pytest.fixture
def backend():
    b = InMemoryBackend()
    b.add_spreadsheet(
        "Doc",
        {
            "Pyd": [
                ["id", "nombre completo", "activo"],
                ["1", "Ana García", "true"],
                ["2", "Luis Paz", ""],
            ],
            "Vacia": [],
        },
    )
    return b


@pytest.fixture
def mgr(backend):
    return backend.manager("Doc")


HEADER_DC = ["id", "monto", "estado", "prioridad", "nota"]


class TestDomainCoercions:

    def test_decimal_enum_literal_roundtrip(self):
        models = rows_to_models(FilaDc, HEADER_DC, [["1", "10.50", "hecho", "alta", ""]])
        fila = models[0]
        assert fila.monto == Decimal("10.50")
        assert fila.estado is Estado.HECHO
        assert fila.prioridad == "alta"
        assert fila.nota is None
        # Serialización de vuelta a celdas
        assert format_cell(fila.monto) == "10.50"
        assert format_cell(fila.estado) == "hecho"

    def test_enum_fallback_by_name(self):
        models = rows_to_models(FilaDc, HEADER_DC, [["1", "0", "PENDIENTE", "baja", ""]])
        assert models[0].estado is Estado.PENDIENTE

    def test_invalid_decimal_raises(self):
        with pytest.raises(SchemaError, match="Decimal inválido"):
            rows_to_models(FilaDc, HEADER_DC, [["1", "diez", "hecho", "alta", ""]])

    def test_invalid_enum_raises_with_options(self):
        with pytest.raises(SchemaError, match="esperaba uno de"):
            rows_to_models(FilaDc, HEADER_DC, [["1", "0", "otro", "alta", ""]])

    def test_invalid_literal_raises(self):
        with pytest.raises(SchemaError, match="esperaba uno de"):
            rows_to_models(FilaDc, HEADER_DC, [["1", "0", "hecho", "media", ""]])


class TestPydanticCodec:
    def test_supports_detection(self):
        assert PydanticModelCodec().supports(FilaPyd)
        assert not PydanticModelCodec().supports(FilaDc)
        assert DataclassModelCodec().supports(FilaDc)
        assert not DataclassModelCodec().supports(FilaPyd)

    def test_read_as_validates_and_coerces(self, mgr):
        filas = mgr.worksheet("Pyd").read_as(FilaPyd)
        assert filas[0] == FilaPyd.model_validate({"id": 1, "nombre completo": "Ana García", "activo": True})
        assert filas[1].activo is True  # celda vacía -> default

    def test_alias_maps_column_name(self, mgr):
        filas = mgr.worksheet("Pyd").read_as(FilaPyd)
        assert filas[0].nombre == "Ana García"

    def test_validation_error_becomes_schema_error(self, backend, mgr):
        backend.client.spreadsheet_by_key("doc0").seed(
            "Mala", [["id", "nombre completo"], ["no-numero", "X"]]
        )
        with pytest.raises(SchemaError, match="Fila inválida"):
            mgr.worksheet("Mala").read_as(FilaPyd)

    def test_write_and_append_models(self, backend, mgr):
        ws = mgr.worksheet("Pyd")
        ws.write_models([FilaPyd.model_validate({"id": 9, "nombre completo": "Eva", "activo": False})])
        assert ws.read() == [["id", "nombre completo", "activo"], ["9", "Eva", "FALSE"]]
        ws.append_models([FilaPyd.model_validate({"id": 10, "nombre completo": "Zoe"})])
        assert ws.read()[-1] == ["10", "Zoe", "TRUE"]

    def test_upsert_models_pydantic(self, mgr):
        ws = mgr.worksheet("Pyd")
        result = ws.upsert_models(
            [FilaPyd.model_validate({"id": 2, "nombre completo": "Luis P.", "activo": False})],
            key="id",
        )
        assert result == {"updated": 1, "appended": 0}
        assert ws.read()[2] == ["2", "Luis P.", "FALSE"]

    def test_iter_as_pydantic(self, mgr):
        filas = list(mgr.worksheet("Pyd").iter_as(FilaPyd, page_size=1))
        assert [f.id for f in filas] == [1, 2]

    def test_unsupported_model_raises(self, mgr):
        class Cualquiera:
            pass

        with pytest.raises(SchemaError, match="no es un dataclass ni un modelo Pydantic"):
            mgr.worksheet("Pyd").read_as(Cualquiera)


class TestEnsureSchema:
    def test_creates_header_on_empty_sheet(self, mgr):
        ws = mgr.worksheet("Vacia")
        result = ws.ensure_schema(FilaPyd)
        assert result == {"created": True, "missing": [], "extra": []}
        assert ws.read() == [["id", "nombre completo", "activo"]]

    def test_empty_sheet_without_create_raises(self, mgr):
        with pytest.raises(SchemaError, match="create=False") as exc_info:
            mgr.worksheet("Vacia").ensure_schema(FilaPyd, create=False)
        assert exc_info.value.missing_columns == ["id", "nombre completo", "activo"]

    def test_matching_header_reports_clean(self, mgr):
        result = mgr.worksheet("Pyd").ensure_schema(FilaPyd)
        assert result == {"created": False, "missing": [], "extra": []}

    def test_missing_columns_raise_with_detail(self, backend, mgr):
        backend.client.spreadsheet_by_key("doc0").seed("Drift", [["id", "otra"]])
        with pytest.raises(SchemaError, match="faltan") as exc_info:
            mgr.worksheet("Drift").ensure_schema(FilaPyd)
        assert exc_info.value.missing_columns == ["nombre completo", "activo"]
        assert exc_info.value.extra_columns == ["otra"]

    def test_extra_columns_tolerated_unless_strict(self, backend, mgr):
        backend.client.spreadsheet_by_key("doc0").seed(
            "Extra", [["id", "nombre completo", "activo", "comentario"]]
        )
        result = mgr.worksheet("Extra").ensure_schema(FilaPyd)
        assert result["extra"] == ["comentario"]
        with pytest.raises(SchemaError, match="strict"):
            mgr.worksheet("Extra").ensure_schema(FilaPyd, strict=True)

    def test_dataclass_schema_with_column_metadata(self, mgr):
        @dataclass
        class ConAlias:
            id: int
            nombre: str

        ws = mgr.worksheet("Vacia")
        ws.ensure_schema(ConAlias)
        assert ws.read() == [["id", "nombre"]]
