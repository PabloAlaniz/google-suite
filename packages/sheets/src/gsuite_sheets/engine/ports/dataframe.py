"""Puerto de DataFrame.

Abstrae la conversión filas <-> DataFrame para que la capa de aplicación no dependa de
pandas. La implementación concreta (``PandasDataFrameAdapter``) vive en infraestructura.
"""

from __future__ import annotations

from typing import Any, Protocol


class DataFramePort(Protocol):
    """Convierte entre filas (listas) y un DataFrame."""

    def from_rows(self, header: list[str], rows: list[list[Any]]) -> Any:
        """Construye un DataFrame con ``header`` como columnas y ``rows`` como datos."""
        ...

    def to_rows(self, df: Any, include_header: bool) -> list[list[Any]]:
        """Convierte un DataFrame en filas, anteponiendo el encabezado si se pide."""
        ...
