"""Adaptador de pandas: implementa ``DataFramePort`` con la dependencia opcional pandas.

pandas se importa de forma diferida; si no está instalado, se lanza un ImportError con
instrucciones de instalación. Es el único módulo que conoce pandas.
"""

from __future__ import annotations

from typing import Any


class PandasDataFrameAdapter:
    """Conversión filas <-> ``pandas.DataFrame``."""

    def from_rows(self, header: list[str], rows: list[list[Any]]) -> Any:
        """Construye un ``DataFrame`` con ``header`` como columnas y ``rows`` como datos."""
        return self._pandas().DataFrame(rows, columns=header)

    def to_rows(self, df: Any, include_header: bool) -> list[list[Any]]:
        """Convierte un ``DataFrame`` en filas, anteponiendo el encabezado si se pide."""
        header: list[list[Any]] = [list(df.columns)] if include_header else []
        rows: list[list[Any]] = df.values.tolist()
        return header + rows

    def _pandas(self) -> Any:
        """Importa pandas de forma diferida o lanza un ImportError descriptivo."""
        try:
            import pandas as pd  # noqa: PLC0415  (dependencia opcional, carga diferida)
        except ImportError as exc:
            raise ImportError(
                "El formato 'pandas' requiere la dependencia opcional pandas. "
                "Instalala con: pip install GSpreadManager[pandas]"
            ) from exc
        return pd
