"""Servicio de modelos de fila tipados.

Lee/escribe filas de una hoja como instancias de un modelo tipado, delegando la conversión
en el ``ModelCodec`` que soporte el modelo (dataclasses o Pydantic). Opera sobre
``WorksheetPort``; también valida/crea el esquema de la hoja (``ensure_schema``).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from gspreadmanager.domain.errors import SchemaError
from gspreadmanager.ports.model_codec import ModelCodec
from gspreadmanager.ports.sheets import WorksheetPort


def schema_drift(expected: list[str], header: list[str]) -> tuple[list[str], list[str]]:
    """Compara el encabezado esperado por el modelo con el de la hoja: ``(faltan, sobran)``."""
    missing = [column for column in expected if column not in header]
    extra = [column for column in header if column not in expected and column != ""]
    return missing, extra


class RowModelService:
    """Casos de uso de lectura/escritura de filas tipadas (codec por modelo)."""

    def __init__(self, codecs: Sequence[ModelCodec] | None = None) -> None:
        """Recibe los codecs disponibles (por defecto: Pydantic + dataclasses)."""
        if codecs is None:
            from gspreadmanager.infrastructure.model_codecs import DEFAULT_CODECS  # noqa: PLC0415

            codecs = DEFAULT_CODECS
        self._codecs = list(codecs)

    def codec_for(self, model: type) -> ModelCodec:
        """Devuelve el primer codec que soporta ``model`` (``SchemaError`` si ninguno)."""
        for codec in self._codecs:
            if codec.supports(model):
                return codec
        raise SchemaError(
            f"El modelo {getattr(model, '__name__', model)!r} no es un dataclass ni un "
            "modelo Pydantic soportado."
        )

    def to_models(self, model: type, header: list[str], rows: list[list[str]]) -> list[Any]:
        """Filas -> instancias de ``model`` con el codec correspondiente."""
        return self.codec_for(model).to_models(model, header, rows)

    def to_rows(self, models: list[Any]) -> tuple[list[str], list[list[Any]]]:
        """Instancias -> (encabezado, filas) con el codec correspondiente."""
        if not models:
            return [], []
        return self.codec_for(type(models[0])).to_rows(models)

    def read(self, worksheet: WorksheetPort, model: type, skiprows: int) -> list[Any]:
        """Lee la hoja como una lista de instancias de ``model`` (encabezado en la 1ª fila)."""
        values = worksheet.get_all_values()[skiprows:]
        if not values:
            return []
        return self.to_models(model, values[0], values[1:])

    def append(self, worksheet: WorksheetPort, models: list[Any], value_input_option: str) -> Any:
        """Añade los modelos como filas al final (sin encabezado)."""
        if not models:
            return None
        _, rows = self.to_rows(models)
        return worksheet.append_rows(rows, value_input_option)

    def write(
        self,
        worksheet: WorksheetPort,
        models: list[Any],
        include_header: bool,
        clear: bool,
        value_input_option: str,
    ) -> Any:
        """Escribe los modelos desde A1 (encabezado opcional), limpiando antes si ``clear``."""
        header, rows = self.to_rows(models)
        values = ([header] if include_header and header else []) + rows
        if clear:
            worksheet.clear()
        return worksheet.update(values, value_input_option)

    def ensure_schema(
        self,
        worksheet: WorksheetPort,
        model: type,
        *,
        create: bool = True,
        strict: bool = False,
    ) -> dict[str, Any]:
        """Valida (o crea) el encabezado de la hoja contra el esquema del modelo.

        - Hoja sin encabezado: lo escribe desde el modelo si ``create`` (si no, ``SchemaError``).
        - Faltan columnas del modelo: ``SchemaError`` con ``missing_columns``/``extra_columns``.
        - Columnas extra: se toleran y se reportan, salvo ``strict=True`` (``SchemaError``).

        Devuelve ``{"created": bool, "missing": [...], "extra": [...]}``.
        """
        expected = self.codec_for(model).header(model)
        values = worksheet.get_all_values()
        header = values[0] if values else []
        if not any(cell != "" for cell in header):
            if not create:
                raise SchemaError(
                    "La hoja no tiene encabezado y create=False.", missing_columns=expected
                )
            worksheet.update([expected], "RAW")
            return {"created": True, "missing": [], "extra": []}

        missing, extra = schema_drift(expected, header)
        if missing:
            raise SchemaError(
                f"El encabezado no cubre el modelo: faltan {missing} (sobran: {extra}).",
                missing_columns=missing,
                extra_columns=extra,
            )
        if strict and extra:
            raise SchemaError(
                f"Columnas no declaradas en el modelo: {extra} (strict=True).",
                extra_columns=extra,
            )
        return {"created": False, "missing": missing, "extra": extra}
