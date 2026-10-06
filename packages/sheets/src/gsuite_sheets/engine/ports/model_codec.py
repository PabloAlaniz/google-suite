"""Puerto de codecs de modelos: filas de la hoja <-> modelos tipados.

Abstrae qué librería de modelos se usa (dataclasses, Pydantic, ...). La capa de
aplicación (``RowModelService``) resuelve el codec que soporta cada modelo y delega la
conversión; agregar soporte para otra librería es implementar este protocolo.
"""

from __future__ import annotations

from typing import Any, Protocol


class ModelCodec(Protocol):
    """Convierte entre filas (listas de strings) y modelos tipados."""

    def supports(self, model: type) -> bool:
        """True si este codec sabe manejar ``model``."""
        ...

    def header(self, model: type) -> list[str]:
        """Encabezado (nombres de columna, en orden) que espera el modelo."""
        ...

    def to_models(self, model: type, header: list[str], rows: list[list[str]]) -> list[Any]:
        """Construye instancias de ``model`` desde el encabezado y las filas."""
        ...

    def to_rows(self, models: list[Any]) -> tuple[list[str], list[list[Any]]]:
        """Convierte instancias en ``(encabezado, filas)`` listos para escribir."""
        ...
