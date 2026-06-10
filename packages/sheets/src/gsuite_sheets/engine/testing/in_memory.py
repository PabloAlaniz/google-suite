"""Backend en memoria que implementa los puertos de Sheets, para tests sin red.

Permite a los usuarios (y a nosotros) ejercitar código que usa ``SheetManager`` sin llamar
a la API de Google: los valores hacen round-trip (escribís y leés lo mismo) y las
operaciones estructurales por ``batchUpdate`` (insertar/eliminar filas, notas, named/protected
ranges) se aplican o se registran para poder inspeccionarlas en los tests.

Uso típico::

    from gspreadmanager.testing import InMemoryBackend

    backend = InMemoryBackend()
    backend.add_spreadsheet("MiDoc", {"Hoja1": [["nombre", "email"], ["Ana", "ana@x.com"]]})
    mgr = backend.manager("MiDoc")
    assert mgr.worksheet("Hoja1").read(output_format="dict") == [{"nombre": "Ana", ...}]

No es un clon fiel de la API: el formato/validación/orden/filtro se registran en
``spreadsheet.requests`` pero no alteran la grilla.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from gspreadmanager.domain.errors import (
    GSpreadManagerError,
    SpreadsheetNotFoundError,
    WorksheetNotFoundError,
)
from gspreadmanager.domain.values import GridRange
from gspreadmanager.ports.sheets import SpreadsheetPort, WorksheetPort

if TYPE_CHECKING:
    from gspreadmanager.facade import SheetManager


@dataclass(frozen=True)
class FakeCell:
    """Celda devuelta por ``range`` (equivalente en memoria de ``gspread.Cell``)."""

    row: int
    col: int
    value: str


def _grid_dict(a1_range: str) -> dict[str, int]:
    """Resuelve un rango A1 (sin pestaña) a su dict ``GridRange`` con la conversión del dominio."""
    return GridRange.from_a1(a1_range, sheet_id=0).to_dict()


def _anchor(a1_range: str) -> tuple[int, int]:
    """Devuelve el (row0, col0) 0-based de la esquina superior izquierda de un rango A1."""
    grid = _grid_dict(a1_range)
    return grid.get("startRowIndex", 0), grid.get("startColumnIndex", 0)


class _Grid:
    """Grilla dispersa de celdas (1-based) con valores ``str`` ('' = vacío)."""

    def __init__(self) -> None:
        self._cells: dict[tuple[int, int], str] = {}

    def set(self, row: int, col: int, value: Any) -> None:
        """Fija una celda (vacía la borra para no inflar los límites)."""
        text = "" if value is None else str(value)
        if text == "":
            self._cells.pop((row, col), None)
        else:
            self._cells[(row, col)] = text

    def get(self, row: int, col: int) -> str:
        """Valor de una celda ('' si está vacía)."""
        return self._cells.get((row, col), "")

    @property
    def max_row(self) -> int:
        """Última fila con datos (0 si está vacía)."""
        return max((r for r, _ in self._cells), default=0)

    @property
    def max_col(self) -> int:
        """Última columna con datos (0 si está vacía)."""
        return max((c for _, c in self._cells), default=0)

    def all_values(self) -> list[list[str]]:
        """Matriz rectangular hasta la última celda con datos (como ``get_all_values``)."""
        rows, cols = self.max_row, self.max_col
        return [[self.get(r, c) for c in range(1, cols + 1)] for r in range(1, rows + 1)]

    def clear(self) -> None:
        """Borra toda la grilla."""
        self._cells.clear()

    def write_block(self, row0: int, col0: int, values: list[list[Any]]) -> None:
        """Escribe ``values`` con esquina superior izquierda en (row0, col0) 0-based."""
        for i, row_values in enumerate(values):
            for j, value in enumerate(row_values):
                self.set(row0 + i + 1, col0 + j + 1, value)

    def clear_block(self, a1_range: str) -> None:
        """Borra las celdas dentro del rango A1 indicado."""
        grid = _grid_dict(a1_range.split("!", 1)[-1])
        r1 = grid.get("startRowIndex", 0) + 1
        r2 = grid.get("endRowIndex", self.max_row)
        c1 = grid.get("startColumnIndex", 0) + 1
        c2 = grid.get("endColumnIndex", self.max_col)
        for row, col in [k for k in self._cells if r1 <= k[0] <= r2 and c1 <= k[1] <= c2]:
            del self._cells[(row, col)]

    def shift(self, axis: str, start: int, count: int) -> None:
        """Inserta ``count`` filas/columnas en blanco antes del índice 0-based ``start``."""
        self._cells = {self._moved(k, axis, start, count): v for k, v in self._cells.items()}

    def remove(self, axis: str, start: int, end: int) -> None:
        """Elimina filas/columnas en el rango 0-based ``[start, end)``."""
        span = end - start
        survivors: dict[tuple[int, int], str] = {}
        for (row, col), value in self._cells.items():
            key = row if axis == "ROWS" else col
            if start + 1 <= key <= end:
                continue
            shifted = key - span if key > end else key
            survivors[(shifted, col) if axis == "ROWS" else (row, shifted)] = value
        self._cells = survivors

    @staticmethod
    def _moved(cell: tuple[int, int], axis: str, start: int, count: int) -> tuple[int, int]:
        row, col = cell
        if axis == "ROWS":
            return (row + count if row >= start + 1 else row, col)
        return (row, col + count if col >= start + 1 else col)


class InMemoryWorksheet:
    """``WorksheetPort`` en memoria sobre una ``_Grid``."""

    def __init__(self, spreadsheet: InMemorySpreadsheet, title: str, sheet_id: int) -> None:
        """Recibe el documento padre, el título y el id de hoja."""
        self._ss = spreadsheet
        self._title = title
        self._id = sheet_id
        self._grid = _Grid()

    @property
    def grid(self) -> _Grid:
        """Grilla subyacente (para precargar datos o inspeccionar en tests)."""
        return self._grid

    @property
    def id(self) -> int:
        """Id numérico de la hoja."""
        return self._id

    @property
    def title(self) -> str:
        """Nombre de la pestaña."""
        return self._title

    @property
    def spreadsheet(self) -> SpreadsheetPort:
        """Documento al que pertenece la hoja."""
        return self._ss

    def update_cell(self, row: int, col: int, value: Any) -> None:
        """Actualiza una celda (1-based)."""
        self._grid.set(row, col, value)

    def get_all_values(self, value_render_option: str | None = None) -> list[list[str]]:
        """Devuelve todas las filas como matriz rectangular de strings.

        ``value_render_option`` se acepta por contrato y se ignora: el fake no modela
        fórmulas ni formato (devuelve siempre el valor almacenado).
        """
        return self._grid.all_values()

    def append_rows(self, data: list[list[Any]], value_input_option: str) -> Any:
        """Añade filas tras la última con datos."""
        self._grid.write_block(self._grid.max_row, 0, data)
        return {"updates": {"updatedRows": len(data)}}

    def batch_update(self, range_data: list[dict[str, Any]], value_input_option: str) -> None:
        """Escribe varios rangos ``{'range': 'A1', 'values': [[...]]}``."""
        for item in range_data:
            row0, col0 = _anchor(item["range"])
            self._grid.write_block(row0, col0, item["values"])

    def update(
        self, values: list[list[Any]], value_input_option: str, range_name: str | None = None
    ) -> Any:
        """Escribe ``values`` desde A1 o desde ``range_name`` (ancla)."""
        row0, col0 = _anchor(range_name) if range_name else (0, 0)
        self._grid.write_block(row0, col0, values)
        return {"updatedCells": sum(len(row) for row in values)}

    def col_values(self, col: int) -> list[Any]:
        """Valores de una columna (1-based)."""
        return [row[col - 1] if col - 1 < len(row) else "" for row in self.get_all_values()]

    def row_values(self, row: int) -> list[Any]:
        """Valores de una fila (1-based)."""
        values = self.get_all_values()
        return values[row - 1] if 0 < row <= len(values) else []

    def range(self, name: str) -> list[Any]:
        """Celdas del rango A1 como ``FakeCell`` (incluye vacías dentro del rango)."""
        grid = _grid_dict(name.split("!", 1)[-1])
        r1 = grid.get("startRowIndex", 0) + 1
        r2 = grid.get("endRowIndex", self._grid.max_row)
        c1 = grid.get("startColumnIndex", 0) + 1
        c2 = grid.get("endColumnIndex", self._grid.max_col)
        return [
            FakeCell(row=r, col=c, value=self._grid.get(r, c))
            for r in range(r1, r2 + 1)
            for c in range(c1, c2 + 1)
        ]

    def format(self, ranges: str | list[str], cell_format: dict[str, Any]) -> Any:
        """Registra un formato (no altera la grilla)."""
        self._ss.requests.append({"format": {"ranges": ranges, "cell": cell_format}})
        return None

    def freeze(self, rows: int | None, cols: int | None) -> Any:
        """Registra un freeze (no altera la grilla)."""
        self._ss.requests.append({"freeze": {"rows": rows, "cols": cols}})
        return None

    def merge_cells(self, range_name: str, merge_type: str) -> Any:
        """Registra un merge (no altera la grilla)."""
        self._ss.requests.append({"merge": {"range": range_name, "mergeType": merge_type}})
        return None

    def clear(self) -> None:
        """Limpia toda la hoja."""
        self._grid.clear()

    def batch_clear(self, ranges: list[str]) -> None:
        """Limpia varios rangos."""
        for a1 in ranges:
            self._grid.clear_block(a1)

    def find(self, query: str, case_sensitive: bool) -> Any:
        """Busca la primera celda con valor ``query`` (orden por fila, luego columna)."""
        needle = query if case_sensitive else query.lower()
        for r, row in enumerate(self.get_all_values(), start=1):
            for c, value in enumerate(row, start=1):
                haystack = value if case_sensitive else value.lower()
                if haystack == needle:
                    return FakeCell(row=r, col=c, value=value)
        return None

    def copy_to(self, destination_spreadsheet_id: str) -> dict[str, Any]:
        """Copia esta hoja a otro documento del mismo backend (``sheets.copyTo``)."""
        client = self._ss.client
        if client is None:
            raise GSpreadManagerError(
                "copy_to requiere que el documento esté registrado en un InMemoryClient."
            )
        dest = client.spreadsheet_by_key(destination_spreadsheet_id)
        copy = dest.seed(f"Copia de {self._title}", self.get_all_values())
        return {"sheetId": copy.id, "title": copy.title, "index": len(dest.worksheets) - 1}


class InMemorySpreadsheet:
    """``SpreadsheetPort`` en memoria: contiene hojas, notas, named/protected ranges y permisos."""

    def __init__(self, title: str, file_id: str) -> None:
        """Crea un documento vacío con título e id."""
        self.title = title
        self.id = file_id
        # Cliente al que está registrado (lo fija InMemoryClient.register; habilita copy_to).
        self.client: InMemoryClient | None = None
        self._worksheets: list[InMemoryWorksheet] = []
        self._next_sheet_id = 0
        self.requests: list[dict[str, Any]] = []
        self.permissions: list[dict[str, Any]] = []
        self._notes: dict[tuple[int, int, int], str] = {}
        self._named: list[dict[str, Any]] = []
        self._protected: list[dict[str, Any]] = []
        self._next_named_id = 0
        self._next_protected_id = 0

    # -- gestión de hojas -------------------------------------------------

    def seed(self, title: str, values: list[list[Any]] | None = None) -> InMemoryWorksheet:
        """Crea una hoja precargada con ``values`` (atajo para armar fixtures)."""
        ws = self._add(title, None)
        if values:
            ws.grid.write_block(0, 0, values)
        return ws

    @property
    def worksheets(self) -> list[InMemoryWorksheet]:
        """Hojas del documento (para inspección en tests)."""
        return list(self._worksheets)

    @property
    def sheet1(self) -> WorksheetPort:
        """Primera hoja del documento."""
        if not self._worksheets:
            raise GSpreadManagerError(f"El documento '{self.title}' no tiene hojas.")
        return self._worksheets[0]

    def worksheet(self, name: str) -> WorksheetPort:
        """Hoja por nombre."""
        for ws in self._worksheets:
            if ws.title == name:
                return ws
        raise WorksheetNotFoundError(f"No existe la hoja '{name}' en '{self.title}'.")

    def add_worksheet(self, title: str, rows: int, cols: int, index: int | None) -> WorksheetPort:
        """Crea una nueva hoja y la devuelve."""
        return self._add(title, index)

    def _add(self, title: str, index: int | None) -> InMemoryWorksheet:
        ws = InMemoryWorksheet(self, title, self._next_sheet_id)
        self._next_sheet_id += 1
        if index is None:
            self._worksheets.append(ws)
        else:
            self._worksheets.insert(index, ws)
        return ws

    def delete_worksheet(self, title: str) -> None:
        """Elimina la hoja con el nombre dado."""
        self._worksheets = [ws for ws in self._worksheets if ws.title != title]

    def _by_id(self, sheet_id: int) -> InMemoryWorksheet:
        for ws in self._worksheets:
            if ws.id == sheet_id:
                return ws
        raise WorksheetNotFoundError(f"No existe la hoja con id {sheet_id}.")

    # -- valores ----------------------------------------------------------

    def values_get(self, a1_range: str) -> Any:
        """Lee un rango A1 (``{'values': [...]}``, recortando filas finales vacías)."""
        ws = self._resolve(a1_range)
        cells = ws.range(a1_range)
        if not cells:
            return {}
        rows: dict[int, dict[int, str]] = {}
        for cell in cells:
            rows.setdefault(cell.row, {})[cell.col] = cell.value
        cols = sorted({cell.col for cell in cells})
        matrix = [[rows[r].get(c, "") for c in cols] for r in sorted(rows)]
        trimmed = _trim_trailing_empty(matrix)
        return {"values": trimmed} if trimmed else {}

    def values_append(self, a1_range: str, params: dict[str, Any], body: dict[str, Any]) -> Any:
        """Añade valores al final de la hoja del rango."""
        ws = self._resolve(a1_range)
        ws.append_rows(body["values"], params.get("valueInputOption", "USER_ENTERED"))
        return {"updates": {"updatedRows": len(body["values"])}}

    def _resolve(self, a1_range: str) -> InMemoryWorksheet:
        """Resuelve la hoja referida por el prefijo del rango (o la primera)."""
        if "!" in a1_range:
            return self.worksheet(a1_range.split("!", 1)[0])  # type: ignore[return-value]
        return self._worksheets[0]

    # -- batchUpdate ------------------------------------------------------

    def batch_update(self, body: dict[str, Any]) -> Any:
        """Aplica/registra las requests de ``spreadsheets:batchUpdate``."""
        for request in body.get("requests", []):
            self._dispatch(request)
        return {"replies": []}

    def _dispatch(self, request: dict[str, Any]) -> None:
        self.requests.append(request)
        if "insertDimension" in request:
            rng = request["insertDimension"]["range"]
            self._by_id(rng["sheetId"]).grid.shift(
                rng["dimension"], rng["startIndex"], rng["endIndex"] - rng["startIndex"]
            )
        elif "deleteDimension" in request:
            rng = request["deleteDimension"]["range"]
            self._by_id(rng["sheetId"]).grid.remove(
                rng["dimension"], rng["startIndex"], rng["endIndex"]
            )
        elif "updateCells" in request:
            self._store_note(request["updateCells"])
        elif "addNamedRange" in request:
            self._add_named(request["addNamedRange"]["namedRange"])
        elif "deleteNamedRange" in request:
            target = request["deleteNamedRange"]["namedRangeId"]
            self._named = [n for n in self._named if n["namedRangeId"] != target]
        elif "addProtectedRange" in request:
            self._add_protected(request["addProtectedRange"]["protectedRange"])
        elif "deleteProtectedRange" in request:
            target = request["deleteProtectedRange"]["protectedRangeId"]
            self._protected = [p for p in self._protected if p["protectedRangeId"] != target]
        elif "findReplace" in request:
            self._apply_find_replace(request["findReplace"])

    def _apply_find_replace(self, spec: dict[str, Any]) -> None:
        """Aplica un findReplace literal sobre la grilla (sin regex: el fake es simple)."""
        ws = self._by_id(spec["sheetId"])
        find, replacement = spec["find"], spec["replacement"]
        match_case = spec.get("matchCase", False)
        entire = spec.get("matchEntireCell", False)
        flags = 0 if match_case else re.IGNORECASE
        pattern = re.compile(re.escape(find), flags)
        for (row, col), value in list(ws.grid._cells.items()):
            if entire:
                if pattern.fullmatch(value):
                    ws.grid.set(row, col, replacement)
            elif pattern.search(value):
                ws.grid.set(row, col, pattern.sub(replacement, value))

    def _store_note(self, update: dict[str, Any]) -> None:
        rng = update["range"]
        row = rng.get("startRowIndex", 0) + 1
        col = rng.get("startColumnIndex", 0) + 1
        note = update["rows"][0]["values"][0].get("note", "")
        self._notes[(rng["sheetId"], row, col)] = note

    def _add_named(self, named_range: dict[str, Any]) -> None:
        entry = dict(named_range)
        entry["namedRangeId"] = f"nr{self._next_named_id}"
        self._next_named_id += 1
        self._named.append(entry)

    def _add_protected(self, protected: dict[str, Any]) -> None:
        entry = dict(protected)
        entry["protectedRangeId"] = self._next_protected_id
        self._next_protected_id += 1
        self._protected.append(entry)

    # -- metadata ---------------------------------------------------------

    def get_metadata(self, ranges: list[str] | None, fields: str) -> dict[str, Any]:
        """Lee metadata: hojas, notas (por rango), named o protected ranges según ``fields``."""
        if "sheets.properties" in fields:
            return {
                "sheets": [
                    {"properties": {"sheetId": ws.id, "title": ws.title, "index": i}}
                    for i, ws in enumerate(self._worksheets)
                ]
            }
        if "namedRanges" in fields:
            return {"namedRanges": list(self._named)}
        if "protectedRanges" in fields:
            return {
                "sheets": [
                    {
                        "properties": {"sheetId": ws.id},
                        "protectedRanges": [
                            p for p in self._protected if p["range"]["sheetId"] == ws.id
                        ],
                    }
                    for ws in self._worksheets
                ]
            }
        if "note" in fields and ranges:
            return {"sheets": [{"data": [{"rowData": self._note_rows(ranges[0])}]}]}
        return {}

    def _note_rows(self, a1_with_sheet: str) -> list[dict[str, Any]]:
        ws = self._resolve(a1_with_sheet)
        row, col = _anchor(a1_with_sheet)
        note = self._notes.get((ws.id, row + 1, col + 1))
        if note is None:
            return []
        return [{"values": [{"note": note}]}]

    # -- export / permisos ------------------------------------------------

    def export(self, mime_type: str) -> bytes:
        """Exporta: CSV/TSV renderiza la primera hoja; otros formatos, un marcador."""
        if mime_type in ("text/csv", "text/tab-separated-values") and self._worksheets:
            sep = "," if mime_type == "text/csv" else "\t"
            rows = self._worksheets[0].get_all_values()
            return "\n".join(sep.join(row) for row in rows).encode()
        return f"in-memory-export:{mime_type}".encode()

    def share(
        self,
        email_address: str,
        perm_type: str,
        role: str,
        notify: bool,
        email_message: str | None,
        with_link: bool,
    ) -> Any:
        """Registra un permiso compartido."""
        perm = {
            "id": f"perm{len(self.permissions)}",
            "type": perm_type,
            "role": role,
            "emailAddress": email_address,
        }
        self.permissions.append(perm)
        return perm

    def list_permissions(self) -> list[dict[str, Any]]:
        """Lista los permisos del documento."""
        return list(self.permissions)

    def remove_permissions(self, value: str, role: str) -> list[str]:
        """Quita permisos por email/dominio (y rol si no es 'any'); devuelve los ids."""
        removed = [
            p["id"]
            for p in self.permissions
            if p.get("emailAddress") == value and (role == "any" or p.get("role") == role)
        ]
        self.permissions = [p for p in self.permissions if p["id"] not in removed]
        return removed


def _trim_trailing_empty(matrix: list[list[str]]) -> list[list[str]]:
    """Recorta filas finales vacías y celdas vacías a la derecha de cada fila (como la API)."""
    rows = [list(row) for row in matrix]
    while rows and all(cell == "" for cell in rows[-1]):
        rows.pop()
    for row in rows:
        while row and row[-1] == "":
            row.pop()
    return rows


class InMemoryClient:
    """``ClientPort`` en memoria: registra documentos por nombre e id."""

    def __init__(self) -> None:
        """Crea un cliente sin documentos."""
        self._by_name: dict[str, InMemorySpreadsheet] = {}
        self._by_id: dict[str, InMemorySpreadsheet] = {}
        self._next_id = 0

    def register(self, spreadsheet: InMemorySpreadsheet) -> InMemorySpreadsheet:
        """Registra un documento ya construido (por nombre e id)."""
        self._by_name[spreadsheet.title] = spreadsheet
        self._by_id[spreadsheet.id] = spreadsheet
        spreadsheet.client = self
        return spreadsheet

    def spreadsheet_by_key(self, key: str) -> InMemorySpreadsheet:
        """Documento registrado por id, como ``InMemorySpreadsheet`` (inspección/copy_to)."""
        if key not in self._by_id:
            raise SpreadsheetNotFoundError(f"No se encontró el documento con id '{key}'.")
        return self._by_id[key]

    def open(self, doc_name: str) -> SpreadsheetPort:
        """Abre un documento por nombre."""
        if doc_name not in self._by_name:
            raise SpreadsheetNotFoundError(f"No se encontró el documento '{doc_name}'.")
        return self._by_name[doc_name]

    def open_by_key(self, key: str) -> SpreadsheetPort:
        """Abre un documento por su id."""
        if key not in self._by_id:
            raise SpreadsheetNotFoundError(f"No se encontró el documento con id '{key}'.")
        return self._by_id[key]

    def create(self, title: str, folder_id: str | None) -> Any:
        """Crea un nuevo documento vacío y lo registra."""
        ss = InMemorySpreadsheet(title, self._new_id())
        self.register(ss)
        return ss

    def del_spreadsheet(self, file_id: str) -> None:
        """Elimina un documento por su id."""
        ss = self._by_id.pop(file_id, None)
        if ss is not None:
            self._by_name.pop(ss.title, None)

    def copy(
        self, file_id: str, title: str | None, copy_permissions: bool, folder_id: str | None
    ) -> Any:
        """Copia un documento existente (incluye hojas/valores; permisos si se pide)."""
        source = self._by_id[file_id]
        clone = InMemorySpreadsheet(title or f"Copy of {source.title}", self._new_id())
        for ws in source.worksheets:
            clone.seed(ws.title, ws.get_all_values())
        if copy_permissions:
            clone.permissions = list(source.permissions)
        self.register(clone)
        return clone

    def list_spreadsheet_files(
        self, title: str | None, folder_id: str | None
    ) -> list[dict[str, Any]]:
        """Lista documentos (filtrando por título si se indica)."""
        return [
            {"id": ss.id, "name": ss.title}
            for ss in self._by_id.values()
            if title is None or ss.title == title
        ]

    def _new_id(self) -> str:
        file_id = f"doc{self._next_id}"
        self._next_id += 1
        return file_id


class InMemoryBackend:
    """Fachada cómoda: arma documentos en memoria y entrega ``SheetManager`` cableados al fake."""

    def __init__(self) -> None:
        """Crea un backend con un cliente en memoria vacío."""
        self.client = InMemoryClient()

    def add_spreadsheet(
        self, doc_name: str, sheets: dict[str, list[list[Any]]] | None = None
    ) -> InMemorySpreadsheet:
        """Crea un documento con hojas precargadas (``{titulo: filas}``) y lo registra."""
        ss: InMemorySpreadsheet = self.client.create(doc_name, None)
        for title, values in (sheets or {"Sheet1": []}).items():
            ss.seed(title, values)
        return ss

    def manager(
        self, doc_name: str | None = None, *, key: str | None = None, **kwargs: Any
    ) -> SheetManager:
        """Devuelve un ``SheetManager`` que opera contra el backend en memoria."""
        from gspreadmanager.facade import SheetManager  # noqa: PLC0415  (evita ciclo de import)

        return SheetManager(doc_name, key=key, sheets_client=self.client, **kwargs)
