"""Adaptador de polars: implementa ``DataFramePort`` con la dependencia opcional polars.

polars se importa de forma diferida; si no está instalado, se lanza un ImportError con
instrucciones de instalación. Es el único módulo que conoce polars. polars no tiene índice
de filas, así que ``index_col`` / ``include_index`` se ignoran (la columna se conserva como
una más).
"""

from __future__ import annotations

from typing import Any


class PolarsDataFrameAdapter:
    """Conversión filas <-> ``polars.DataFrame``."""

    def from_rows(
        self, header: list[str], rows: list[list[Any]], *, index_col: str | None = None
    ) -> Any:
        """Construye un ``DataFrame`` con ``header`` como columnas y ``rows`` como datos."""
        pl = self._polars()
        if not header:
            return pl.DataFrame()
        if not rows:
            return pl.DataFrame(schema=header)
        return pl.DataFrame(rows, schema=header, orient="row")

    def to_rows(
        self, df: Any, include_header: bool, *, include_index: bool = False
    ) -> list[list[Any]]:
        """Convierte un ``DataFrame`` en filas, anteponiendo el encabezado si se pide."""
        header: list[list[Any]] = [list(df.columns)] if include_header else []
        rows: list[list[Any]] = [list(row) for row in df.rows()]
        return header + rows

    def _polars(self) -> Any:
        """Importa polars de forma diferida o lanza un ImportError descriptivo."""
        try:
            import polars as pl  # noqa: PLC0415  (dependencia opcional, carga diferida)
        except ImportError as exc:
            raise ImportError(
                "El backend 'polars' requiere la dependencia opcional polars. "
                "Instalala con: pip install GSpreadManager[polars]"
            ) from exc
        return pl
