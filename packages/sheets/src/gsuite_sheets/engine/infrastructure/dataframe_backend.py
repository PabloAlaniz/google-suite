"""Factory del backend de DataFrame: elige pandas o polars detrás de ``DataFramePort``.

Permite a ``SheetManager`` ser agnóstico al motor de DataFrame: la capa de aplicación solo
conoce el puerto, y aquí se decide la implementación concreta a partir de un nombre.
"""

from __future__ import annotations

from gspreadmanager.domain.errors import GSpreadManagerError
from gspreadmanager.infrastructure.pandas_adapter import PandasDataFrameAdapter
from gspreadmanager.infrastructure.polars_adapter import PolarsDataFrameAdapter
from gspreadmanager.ports.dataframe import DataFramePort


def build_dataframe_adapter(backend: str) -> DataFramePort:
    """Devuelve el adaptador de DataFrame para ``backend`` ('pandas' o 'polars')."""
    normalized = backend.lower()
    if normalized == "pandas":
        return PandasDataFrameAdapter()
    if normalized == "polars":
        return PolarsDataFrameAdapter()
    raise GSpreadManagerError(
        f"Backend de DataFrame desconocido: {backend!r}. Usá 'pandas' o 'polars'."
    )
