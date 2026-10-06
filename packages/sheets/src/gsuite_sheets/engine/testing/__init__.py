"""Utilidades de testing: un backend en memoria que implementa los puertos de Sheets.

Pensado para que los usuarios prueben su código sin tocar la red. Ver
``gspreadmanager.testing.in_memory`` para el detalle.
"""

from .async_in_memory import AsyncInMemoryBackend
from .in_memory import (
    FakeCell,
    InMemoryBackend,
    InMemoryClient,
    InMemorySpreadsheet,
    InMemoryWorksheet,
)

__all__ = [
    "AsyncInMemoryBackend",
    "FakeCell",
    "InMemoryBackend",
    "InMemoryClient",
    "InMemorySpreadsheet",
    "InMemoryWorksheet",
]
