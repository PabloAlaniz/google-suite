"""Parsing de CSV a filas (lógica pura, solo stdlib).

Convierte texto CSV en la matriz de filas que consumen los puertos de escritura. La
lectura de archivos/buffers y la escritura en la hoja viven en la capa de aplicación.
"""

from __future__ import annotations

import csv
import io


def rows_from_csv(text: str, delimiter: str = ",") -> list[list[str]]:
    """Convierte texto CSV en lista de filas (lista de listas de ``str``).

    Usa ``csv.reader`` (maneja comillas, separadores embebidos y saltos de línea en
    celdas). Las filas pueden tener largos distintos; quien escribe decide el padding.
    """
    return [list(row) for row in csv.reader(io.StringIO(text), delimiter=delimiter)]
