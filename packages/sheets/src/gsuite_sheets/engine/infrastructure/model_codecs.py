"""Codecs de modelos: dataclasses (dominio puro) y Pydantic v2 (extra opcional).

Implementan el puerto ``ModelCodec``. El de dataclasses delega en ``domain.schema``; el de
Pydantic importa la librería de forma diferida (``pip install "GSpreadManager[pydantic]"``)
y aprovecha su validación/coerción nativa, traduciendo los errores a ``SchemaError``.
"""

from __future__ import annotations

import dataclasses
import importlib.util
from typing import Any

from gspreadmanager.domain.errors import SchemaError
from gspreadmanager.domain.schema import format_cell, model_header, models_to_rows, rows_to_models
from gspreadmanager.ports.model_codec import ModelCodec

PYDANTIC_MISSING_MESSAGE = (
    "Los modelos Pydantic requieren el paquete 'pydantic' (es un extra opcional). "
    'Instalalo con pip install "GSpreadManager[pydantic]".'
)


class DataclassModelCodec:
    """``ModelCodec`` para ``@dataclass`` (mapeo puro de ``domain.schema``)."""

    def supports(self, model: type) -> bool:
        """True si ``model`` es un dataclass."""
        return dataclasses.is_dataclass(model)

    def header(self, model: type) -> list[str]:
        """Encabezado según los campos del dataclass (con override por metadata)."""
        return model_header(model)

    def to_models(self, model: type, header: list[str], rows: list[list[str]]) -> list[Any]:
        """Filas -> instancias, con coerción de tipos del dominio."""
        return rows_to_models(model, header, rows)

    def to_rows(self, models: list[Any]) -> tuple[list[str], list[list[Any]]]:
        """Instancias -> (encabezado, filas) serializadas."""
        return models_to_rows(models)


class PydanticModelCodec:
    """``ModelCodec`` para modelos Pydantic v2 (validación/coerción nativa de Pydantic).

    El nombre de columna es el ``alias`` del campo si está definido, o el nombre del campo.
    Las celdas vacías se tratan como ausentes (aplican defaults; si el campo es requerido,
    la validación falla con ``SchemaError``).
    """

    def supports(self, model: type) -> bool:
        """True si pydantic está instalado y ``model`` es un ``BaseModel``."""
        base = _base_model()
        return base is not None and isinstance(model, type) and issubclass(model, base)

    def header(self, model: type) -> list[str]:
        """Encabezado según los campos del modelo (alias o nombre)."""
        return [alias for _, alias in self._fields(model)]

    def to_models(self, model: type, header: list[str], rows: list[list[str]]) -> list[Any]:
        """Filas -> instancias validadas por Pydantic (errores como ``SchemaError``)."""
        validation_error = _validation_error()
        index_of = {name: position for position, name in enumerate(header)}
        columns = [alias for _, alias in self._fields(model)]

        result: list[Any] = []
        for row in rows:
            # Pydantic valida por alias: el payload se arma con el nombre de columna.
            payload: dict[str, Any] = {}
            for column in columns:
                position = index_of.get(column)
                if position is None:
                    continue  # columna ausente: que decida la validación (default/required)
                value = row[position] if position < len(row) else ""
                if value != "":
                    payload[column] = value
            try:
                result.append(model.model_validate(payload))  # type: ignore[attr-defined]
            except validation_error as exc:
                raise SchemaError(f"Fila inválida para {model.__name__}: {exc}") from exc
        return result

    def to_rows(self, models: list[Any]) -> tuple[list[str], list[list[Any]]]:
        """Instancias -> (encabezado, filas) serializadas con el formato del dominio."""
        if not models:
            return [], []
        model = type(models[0])
        fields = self._fields(model)
        header = [alias for _, alias in fields]
        rows = [
            [format_cell(getattr(item, name)) for name, _ in fields]
            for item in models
        ]
        return header, rows

    @staticmethod
    def _fields(model: type) -> list[tuple[str, str]]:
        """Pares ``(nombre_de_campo, nombre_de_columna)`` del modelo."""
        model_fields: dict[str, Any] = model.model_fields  # type: ignore[attr-defined]
        return [(name, field.alias or name) for name, field in model_fields.items()]


def _base_model() -> type | None:
    """``pydantic.BaseModel`` si pydantic está instalado, o None."""
    if importlib.util.find_spec("pydantic") is None:
        return None
    from pydantic import BaseModel  # noqa: PLC0415

    return BaseModel


def _validation_error() -> type[Exception]:
    try:
        from pydantic import ValidationError  # noqa: PLC0415
    except ImportError as exc:
        raise SchemaError(PYDANTIC_MISSING_MESSAGE) from exc
    return ValidationError


DEFAULT_CODECS: tuple[ModelCodec, ...] = (PydanticModelCodec(), DataclassModelCodec())
