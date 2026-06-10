"""Mapeo entre filas de la hoja y modelos tipados (``@dataclass``).

Convierte filas (listas de strings) en instancias de un dataclass y viceversa, con coerción
de tipos (int/float/bool/date...) y validación. Es lógica pura del dominio: no conoce gspread
ni los puertos. El nombre de columna por defecto es el del campo; se puede sobreescribir con
``field(metadata={"column": "Otro nombre"})``.
"""

from __future__ import annotations

import dataclasses
import types
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Any, Literal, Union, get_args, get_origin, get_type_hints

from gspreadmanager.domain.errors import SchemaError

# Une ``typing.Union[...]`` y ``X | None`` (PEP 604, ``types.UnionType`` en 3.10+).
_UNION_ORIGINS: tuple[Any, ...] = (Union, getattr(types, "UnionType", Union))

_TRUE = {"true", "1", "yes", "verdadero", "si", "sí", "x"}
_FALSE = {"false", "0", "no", "falso", ""}


def _require_dataclass(model: type) -> None:
    if not dataclasses.is_dataclass(model):
        raise SchemaError(f"El modelo {getattr(model, '__name__', model)!r} no es un dataclass.")


def _column_name(field: dataclasses.Field[Any]) -> str:
    """Nombre de columna del campo (override por ``metadata['column']`` o el nombre del campo)."""
    column = field.metadata.get("column")
    return str(column) if column is not None else field.name


def _has_default(field: dataclasses.Field[Any]) -> bool:
    """True si el campo tiene valor por defecto (directo o factory)."""
    return (
        field.default is not dataclasses.MISSING or field.default_factory is not dataclasses.MISSING
    )


def _unwrap_optional(annotation: Any) -> tuple[Any, bool]:
    """Devuelve ``(tipo_interno, es_opcional)`` para ``Optional[T]`` / ``T | None``."""
    if get_origin(annotation) in _UNION_ORIGINS:
        args = [arg for arg in get_args(annotation) if arg is not type(None)]
        if len(args) == 1:
            return args[0], True
    return annotation, False


def _parse_bool(value: str, field_name: str) -> bool:
    normalized = value.strip().lower()
    if normalized in _TRUE:
        return True
    if normalized in _FALSE:
        return False
    raise SchemaError(f"Valor booleano inválido para '{field_name}': {value!r}.")


def _coerce(value: str, annotation: Any, field_name: str) -> Any:  # noqa: PLR0911
    """Convierte el texto de una celda al tipo anotado del campo (un return por tipo)."""
    inner, optional = _unwrap_optional(annotation)
    if optional and value == "":
        return None
    if inner is str:
        return value
    if inner is bool:
        return _parse_bool(value, field_name)
    if inner in (int, float):
        try:
            return inner(value)
        except ValueError as exc:
            raise SchemaError(
                f"No se pudo convertir {value!r} a {inner.__name__} en '{field_name}'."
            ) from exc
    if inner is Decimal:
        try:
            return Decimal(value)
        except InvalidOperation as exc:
            raise SchemaError(f"Decimal inválido en '{field_name}': {value!r}.") from exc
    if inner in (date, datetime):
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError as exc:
            raise SchemaError(f"Fecha inválida en '{field_name}': {value!r}.") from exc
        return parsed.date() if inner is date else parsed
    if isinstance(inner, type) and issubclass(inner, Enum):
        return _parse_enum(value, inner, field_name)
    if get_origin(inner) is Literal:
        return _parse_literal(value, get_args(inner), field_name)
    return inner(value)


def _parse_enum(value: str, enum_type: type[Enum], field_name: str) -> Enum:
    """Resuelve un Enum por su valor (o por nombre como fallback)."""
    for member in enum_type:
        if str(member.value) == value:
            return member
    try:
        return enum_type[value]
    except KeyError as exc:
        valid = [str(m.value) for m in enum_type]
        raise SchemaError(
            f"Valor inválido para '{field_name}': {value!r} (esperaba uno de {valid})."
        ) from exc


def _parse_literal(value: str, options: tuple[Any, ...], field_name: str) -> Any:
    """Matchea el texto de la celda contra las opciones de un ``Literal``."""
    for option in options:
        if str(option) == value:
            return option
    raise SchemaError(
        f"Valor inválido para '{field_name}': {value!r} (esperaba uno de {list(options)})."
    )


def rows_to_models(model: type, header: list[str], rows: list[list[str]]) -> list[Any]:
    """Construye una lista de instancias de ``model`` a partir del encabezado y las filas."""
    _require_dataclass(model)
    hints = get_type_hints(model)
    fields = dataclasses.fields(model)
    index_of = {name: position for position, name in enumerate(header)}
    result: list[Any] = []
    for row in rows:
        kwargs: dict[str, Any] = {}
        for field in fields:
            column = _column_name(field)
            if column not in index_of:
                if _has_default(field):
                    continue  # el dataclass usa su valor por defecto
                raise SchemaError(
                    f"Falta la columna '{column}' (campo '{field.name}') en el encabezado."
                )
            position = index_of[column]
            raw = row[position] if position < len(row) else ""
            kwargs[field.name] = _coerce(raw, hints[field.name], field.name)
        result.append(model(**kwargs))
    return result


def format_cell(value: Any) -> Any:
    """Serializa un valor de campo para escribir en la hoja (bool/fecha/Decimal/Enum/None)."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Enum):
        return format_cell(value.value)
    return value


def model_header(model: type) -> list[str]:
    """Encabezado esperado por un dataclass (nombres de columna en orden de campos)."""
    _require_dataclass(model)
    return [_column_name(field) for field in dataclasses.fields(model)]


def models_to_rows(models: list[Any]) -> tuple[list[str], list[list[Any]]]:
    """Convierte una lista de instancias de dataclass en ``(encabezado, filas)``."""
    if not models:
        return [], []
    model = type(models[0])
    _require_dataclass(model)
    fields = dataclasses.fields(model)
    header = [_column_name(field) for field in fields]
    rows = [[format_cell(getattr(item, field.name)) for field in fields] for item in models]
    return header, rows
