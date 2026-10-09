"""The engine's ports (ClientPort / SpreadsheetPort / WorksheetPort) over google-suite.

The Sheets engine incorporated from GSpreadManager talks to Google through
three ports. This module implements them with the google-suite Sheets client,
so every request goes through gsuite_core.execute: same auth, retries, rate-limit
handling and error mapping as the rest of the suite.

Compared to GSpreadManager's native client it replaces, sheet titles are always
quoted in A1 ranges, names are escaped in Drive queries, and range() returns
the whole rectangle (empty cells included), as gspread does.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from gsuite_core import drive_query_literal, execute, paginate
from gsuite_core.exceptions import NotFoundError
from gsuite_sheets.a1 import a1, grid_range
from gsuite_sheets.engine.config import DEFAULT_VALUE_INPUT_OPTION
from gsuite_sheets.engine.domain.errors import (
    GSpreadManagerError,
    SpreadsheetNotFoundError,
    WorksheetNotFoundError,
)
from gsuite_sheets.engine.domain.values import rowcol_to_a1

if TYPE_CHECKING:
    from gsuite_sheets.client import Sheets

SPREADSHEET_MIME = "application/vnd.google-apps.spreadsheet"


@dataclass(frozen=True)
class Cell:
    """A cell returned by find() / range() (gspread.Cell-compatible)."""

    row: int
    col: int
    value: str


def _qualify(title: str, a1_range: str) -> str:
    """Prefix the (quoted) sheet title unless the range already names a sheet."""
    return a1_range if "!" in a1_range else a1(title, a1_range)


def _rectangular(rows: list[list[Any]]) -> list[list[Any]]:
    """The API trims trailing empty cells; pad rows to the same width."""
    width = max((len(row) for row in rows), default=0)
    return [row + [""] * (width - len(row)) for row in rows]


class GoogleApiClient:
    """``ClientPort``: opens spreadsheets and works at the Drive level.

    Opened spreadsheets are cached by name/key, like GSpreadManager's clients:
    asking for another tab of the same document doesn't repeat the lookup.
    """

    def __init__(self, sheets: Sheets) -> None:
        self._sheets = sheets
        self._open: dict[str, GoogleApiSpreadsheet] = {}

    def open(self, doc_name: str) -> GoogleApiSpreadsheet:
        """Open by title (Drive search; quotes in the title are escaped)."""
        if doc_name not in self._open:
            response = execute(
                self._sheets.drive.files().list(
                    q=(
                        f"name = {drive_query_literal(doc_name)} "
                        f"and mimeType = '{SPREADSHEET_MIME}' and trashed = false"
                    ),
                    fields="files(id,name)",
                    pageSize=1,
                    supportsAllDrives=True,
                    includeItemsFromAllDrives=True,
                ),
                "sheets",
                "spreadsheet",
                doc_name,
            )
            files = response.get("files", [])
            if not files:
                raise SpreadsheetNotFoundError(f"No se encontró el documento '{doc_name}'.")
            self._open[doc_name] = self.open_by_key(files[0]["id"])
        return self._open[doc_name]

    def open_by_key(self, key: str) -> GoogleApiSpreadsheet:
        """Open by ID, loading the (title, sheetId) of each tab."""
        if key not in self._open:
            try:
                meta = execute(
                    self._sheets.service.spreadsheets().get(
                        spreadsheetId=key, fields="sheets.properties(sheetId,title)"
                    ),
                    "sheets",
                    "spreadsheet",
                    key,
                )
            except NotFoundError as exc:
                raise SpreadsheetNotFoundError(
                    f"No se encontró el documento con key '{key}'."
                ) from exc
            tabs = [
                (s["properties"]["title"], s["properties"]["sheetId"])
                for s in meta.get("sheets", [])
            ]
            self._open[key] = GoogleApiSpreadsheet(self._sheets, key, tabs)
        return self._open[key]

    def create(self, title: str, folder_id: str | None) -> GoogleApiSpreadsheet:
        """Create a spreadsheet (moved into ``folder_id`` if given) and return it opened."""
        created = execute(
            self._sheets.service.spreadsheets().create(body={"properties": {"title": title}}),
            "sheets",
            "spreadsheet",
        )
        if folder_id is not None:
            execute(
                self._sheets.drive.files().update(
                    fileId=created["spreadsheetId"],
                    addParents=folder_id,
                    removeParents="root",
                    fields="id,parents",
                    supportsAllDrives=True,
                ),
                "sheets",
                "spreadsheet",
                created["spreadsheetId"],
            )
        return self.open_by_key(created["spreadsheetId"])

    def del_spreadsheet(self, file_id: str) -> None:
        """Delete a spreadsheet (Drive)."""
        execute(
            self._sheets.drive.files().delete(fileId=file_id, supportsAllDrives=True),
            "sheets",
            "spreadsheet",
            file_id,
        )
        self._open = {k: v for k, v in self._open.items() if v.id != file_id}

    def copy(
        self, file_id: str, title: str | None, copy_permissions: bool, folder_id: str | None
    ) -> GoogleApiSpreadsheet:
        """Copy a spreadsheet (Drive ``files.copy``), optionally with its permissions."""
        body: dict[str, Any] = {}
        if title is not None:
            body["name"] = title
        if folder_id is not None:
            body["parents"] = [folder_id]
        copied = execute(
            self._sheets.drive.files().copy(fileId=file_id, body=body, supportsAllDrives=True),
            "sheets",
            "spreadsheet",
            file_id,
        )
        if copy_permissions:
            source = GoogleApiSpreadsheet(self._sheets, file_id, [])
            target = GoogleApiSpreadsheet(self._sheets, copied["id"], [])
            for perm in source.list_permissions():
                if perm.get("role") == "owner":
                    continue  # ownership doesn't transfer through a copy
                target.share(
                    perm.get("emailAddress") or perm.get("domain") or "",
                    perm.get("type", "user"),
                    perm.get("role", "reader"),
                    notify=False,
                    email_message=None,
                    with_link=False,
                )
        return self.open_by_key(copied["id"])

    def list_spreadsheet_files(
        self, title: str | None, folder_id: str | None
    ) -> list[dict[str, Any]]:
        """Spreadsheets visible to the user (Drive), following every page."""
        clauses = [f"mimeType = '{SPREADSHEET_MIME}'", "trashed = false"]
        if title is not None:
            clauses.append(f"name = {drive_query_literal(title)}")
        if folder_id is not None:
            clauses.append(f"{drive_query_literal(folder_id)} in parents")
        return list(
            paginate(
                self._sheets.drive.files().list,
                "files",
                "sheets",
                page_size_param="pageSize",
                max_page_size=1000,
                q=" and ".join(clauses),
                fields="nextPageToken,files(id,name)",
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
            )
        )


class GoogleApiSpreadsheet:
    """``SpreadsheetPort`` for one spreadsheet ID."""

    def __init__(self, sheets: Sheets, spreadsheet_id: str, tabs: list[tuple[str, int]]) -> None:
        self._sheets = sheets
        self.id = spreadsheet_id
        self._tabs = tabs

    def _sheet_id(self, title: str) -> int:
        for name, sheet_id in self._tabs:
            if name == title:
                return sheet_id
        raise WorksheetNotFoundError(f"No existe la hoja '{title}'.")

    @property
    def sheet1(self) -> GoogleApiWorksheet:
        """First tab."""
        if not self._tabs:
            raise GSpreadManagerError("El documento no tiene hojas.")
        title, sheet_id = self._tabs[0]
        return GoogleApiWorksheet(self, title, sheet_id)

    def worksheet(self, name: str) -> GoogleApiWorksheet:
        """Tab by title."""
        return GoogleApiWorksheet(self, name, self._sheet_id(name))

    def add_worksheet(
        self, title: str, rows: int, cols: int, index: int | None
    ) -> GoogleApiWorksheet:
        """Add a tab and return it."""
        props: dict[str, Any] = {
            "title": title,
            "gridProperties": {"rowCount": rows, "columnCount": cols},
        }
        if index is not None:
            props["index"] = index
        reply = self.batch_update({"requests": [{"addSheet": {"properties": props}}]})
        sheet_id = reply["replies"][0]["addSheet"]["properties"]["sheetId"]
        self._tabs.append((title, sheet_id))
        return GoogleApiWorksheet(self, title, sheet_id)

    def delete_worksheet(self, title: str) -> None:
        """Delete a tab by title."""
        sheet_id = self._sheet_id(title)
        self.batch_update({"requests": [{"deleteSheet": {"sheetId": sheet_id}}]})
        self._tabs = [(n, sid) for (n, sid) in self._tabs if n != title]

    def values_get(self, a1_range: str) -> Any:
        """``spreadsheets.values.get``."""
        return execute(
            self._sheets.service.spreadsheets().values().get(spreadsheetId=self.id, range=a1_range),
            "sheets",
            "spreadsheet",
            self.id,
        )

    def values_append(self, a1_range: str, params: dict[str, Any], body: dict[str, Any]) -> Any:
        """``spreadsheets.values.append`` (``params`` are API query parameters)."""
        return execute(
            self._sheets.service.spreadsheets()
            .values()
            .append(spreadsheetId=self.id, range=a1_range, body=body, **params),
            "sheets",
            "spreadsheet",
            self.id,
        )

    def batch_update(self, body: dict[str, Any]) -> Any:
        """``spreadsheets.batchUpdate``."""
        return execute(
            self._sheets.service.spreadsheets().batchUpdate(spreadsheetId=self.id, body=body),
            "sheets",
            "spreadsheet",
            self.id,
        )

    def get_metadata(self, ranges: list[str] | None, fields: str) -> dict[str, Any]:
        """``spreadsheets.get`` limited to ``ranges`` / ``fields``."""
        params: dict[str, Any] = {"spreadsheetId": self.id, "fields": fields}
        if ranges is not None:
            params["ranges"] = ranges
        result: dict[str, Any] = execute(
            self._sheets.service.spreadsheets().get(**params), "sheets", "spreadsheet", self.id
        )
        return result

    def export(self, mime_type: str) -> bytes:
        """Export the whole spreadsheet (Drive ``files.export``)."""
        content: bytes = execute(
            self._sheets.drive.files().export(fileId=self.id, mimeType=mime_type),
            "sheets",
            "spreadsheet",
            self.id,
        )
        return content

    def share(
        self,
        email_address: str,
        perm_type: str,
        role: str,
        notify: bool,
        email_message: str | None,
        with_link: bool,
    ) -> Any:
        """Grant a permission (Drive ``permissions.create``)."""
        body: dict[str, Any] = {"type": perm_type, "role": role}
        if perm_type in ("user", "group"):
            body["emailAddress"] = email_address
        elif perm_type == "domain":
            body["domain"] = email_address
        if perm_type in ("domain", "anyone"):
            body["allowFileDiscovery"] = not with_link
        params: dict[str, Any] = {}
        if perm_type in ("user", "group"):
            params["sendNotificationEmail"] = notify
            if email_message:
                params["emailMessage"] = email_message
        return execute(
            self._sheets.drive.permissions().create(
                fileId=self.id, body=body, supportsAllDrives=True, **params
            ),
            "sheets",
            "spreadsheet",
            self.id,
        )

    def list_permissions(self) -> list[dict[str, Any]]:
        """All permissions (Drive ``permissions.list``)."""
        return list(
            paginate(
                self._sheets.drive.permissions().list,
                "permissions",
                "sheets",
                page_size_param="pageSize",
                max_page_size=100,
                fileId=self.id,
                fields="nextPageToken,permissions(id,type,role,emailAddress,domain)",
                supportsAllDrives=True,
            )
        )

    def remove_permissions(self, value: str, role: str) -> list[str]:
        """Remove the permissions of ``value`` (email or domain) with ``role`` ("any" = all)."""
        removed: list[str] = []
        for perm in self.list_permissions():
            matches_value = value in (perm.get("emailAddress"), perm.get("domain"))
            matches_role = role == "any" or perm.get("role") == role
            if matches_value and matches_role:
                execute(
                    self._sheets.drive.permissions().delete(
                        fileId=self.id, permissionId=perm["id"], supportsAllDrives=True
                    ),
                    "sheets",
                    "permission",
                    perm["id"],
                )
                removed.append(perm["id"])
        return removed


class GoogleApiWorksheet:
    """``WorksheetPort`` for one tab."""

    def __init__(self, spreadsheet: GoogleApiSpreadsheet, title: str, sheet_id: int) -> None:
        self._parent = spreadsheet
        self._title = title
        self._sheet_id = sheet_id

    @property
    def id(self) -> int:
        """Numeric sheetId."""
        return self._sheet_id

    @property
    def title(self) -> str:
        """Tab title."""
        return self._title

    @property
    def spreadsheet(self) -> GoogleApiSpreadsheet:
        """Spreadsheet this tab belongs to."""
        return self._parent

    @property
    def _values(self) -> Any:
        return self._parent._sheets.service.spreadsheets().values()

    def _run(self, request: Any) -> Any:
        return execute(request, "sheets", "spreadsheet", self._parent.id)

    def get_all_values(self, value_render_option: str | None = None) -> list[list[str]]:
        """Every row of the tab, padded to a rectangle."""
        params: dict[str, Any] = {"spreadsheetId": self._parent.id, "range": a1(self._title)}
        if value_render_option:
            params["valueRenderOption"] = value_render_option
        rows: list[list[str]] = self._run(self._values.get(**params)).get("values", [])
        return _rectangular(rows)

    def update_cell(self, row: int, col: int, value: Any) -> None:
        """Write one cell (1-based)."""
        self._run(
            self._values.update(
                spreadsheetId=self._parent.id,
                range=a1(self._title, rowcol_to_a1(row, col)),
                valueInputOption=DEFAULT_VALUE_INPUT_OPTION,
                body={"values": [[value]]},
            )
        )

    def append_rows(self, data: list[list[Any]], value_input_option: str) -> Any:
        """Append rows after the last one with data."""
        return self._run(
            self._values.append(
                spreadsheetId=self._parent.id,
                range=a1(self._title),
                valueInputOption=value_input_option,
                insertDataOption="INSERT_ROWS",
                body={"values": data},
            )
        )

    def batch_update(self, range_data: list[dict[str, Any]], value_input_option: str) -> None:
        """Write several ranges in one request."""
        data = [{**item, "range": _qualify(self._title, item["range"])} for item in range_data]
        self._run(
            self._values.batchUpdate(
                spreadsheetId=self._parent.id,
                body={"valueInputOption": value_input_option, "data": data},
            )
        )

    def update(
        self, values: list[list[Any]], value_input_option: str, range_name: str | None = None
    ) -> Any:
        """Write ``values`` from A1, or from ``range_name`` (its top-left cell)."""
        target = a1(self._title) if range_name is None else _qualify(self._title, range_name)
        return self._run(
            self._values.update(
                spreadsheetId=self._parent.id,
                range=target,
                valueInputOption=value_input_option,
                body={"values": values},
            )
        )

    def clear(self) -> None:
        """Clear every value of the tab (formatting is kept)."""
        self._run(self._values.clear(spreadsheetId=self._parent.id, range=a1(self._title)))

    def batch_clear(self, ranges: list[str]) -> None:
        """Clear several ranges."""
        self._run(
            self._values.batchClear(
                spreadsheetId=self._parent.id,
                body={"ranges": [_qualify(self._title, r) for r in ranges]},
            )
        )

    def col_values(self, col: int) -> list[Any]:
        """Values of a column (1-based)."""
        return [row[col - 1] if col - 1 < len(row) else "" for row in self.get_all_values()]

    def row_values(self, row: int) -> list[Any]:
        """Values of a row (1-based)."""
        values = self.get_all_values()
        return values[row - 1] if 0 < row <= len(values) else []

    def find(self, query: str, case_sensitive: bool) -> Cell | None:
        """First cell whose value equals ``query`` (client-side scan)."""
        needle = query if case_sensitive else query.lower()
        for r, row in enumerate(self.get_all_values(), start=1):
            for c, value in enumerate(row, start=1):
                if (value if case_sensitive else value.lower()) == needle:
                    return Cell(row=r, col=c, value=value)
        return None

    def range(self, name: str) -> list[Cell]:
        """Every cell of an A1 range, empty ones included (gspread semantics).

        GSpreadManager's native client returned only cells with data, which broke
        row_with_empty_in_column (it looks for the first "" in the range).
        """
        cell_range = name.split("!", 1)[1] if "!" in name else name
        grid = grid_range(cell_range, self._sheet_id)
        response = self._parent.values_get(_qualify(self._title, name))
        rows: list[list[Any]] = response.get("values", [])

        start_row = grid.get("startRowIndex", 0)
        start_col = grid.get("startColumnIndex", 0)
        end_row = grid.get("endRowIndex", start_row + len(rows))
        end_col = grid.get("endColumnIndex", start_col + max((len(r) for r in rows), default=0))

        cells = []
        for r in range(end_row - start_row):
            row = rows[r] if r < len(rows) else []
            for c in range(end_col - start_col):
                value = row[c] if c < len(row) else ""
                cells.append(Cell(row=start_row + r + 1, col=start_col + c + 1, value=value))
        return cells

    def format(self, ranges: str | list[str], cell_format: dict[str, Any]) -> Any:
        """Apply a (serialized) CellFormat to one or more ranges."""
        targets = [ranges] if isinstance(ranges, str) else ranges
        fields = (
            f"userEnteredFormat({','.join(cell_format)})" if cell_format else "userEnteredFormat"
        )
        return self._parent.batch_update(
            {
                "requests": [
                    {
                        "repeatCell": {
                            "range": grid_range(t.split("!", 1)[-1], self._sheet_id),
                            "cell": {"userEnteredFormat": cell_format},
                            "fields": fields,
                        }
                    }
                    for t in targets
                ]
            }
        )

    def freeze(self, rows: int | None, cols: int | None) -> Any:
        """Freeze rows and/or columns."""
        grid: dict[str, int] = {}
        if rows is not None:
            grid["frozenRowCount"] = rows
        if cols is not None:
            grid["frozenColumnCount"] = cols
        return self._parent.batch_update(
            {
                "requests": [
                    {
                        "updateSheetProperties": {
                            "properties": {"sheetId": self._sheet_id, "gridProperties": grid},
                            "fields": ",".join(f"gridProperties.{k}" for k in grid),
                        }
                    }
                ]
            }
        )

    def merge_cells(self, range_name: str, merge_type: str) -> Any:
        """Merge the cells of a range."""
        return self._parent.batch_update(
            {
                "requests": [
                    {
                        "mergeCells": {
                            "range": grid_range(range_name.split("!", 1)[-1], self._sheet_id),
                            "mergeType": merge_type,
                        }
                    }
                ]
            }
        )

    def copy_to(self, destination_spreadsheet_id: str) -> Any:
        """Copy this tab into another spreadsheet (``sheets.copyTo``)."""
        return self._run(
            self._parent._sheets.service.spreadsheets()
            .sheets()
            .copyTo(
                spreadsheetId=self._parent.id,
                sheetId=self._sheet_id,
                body={"destinationSpreadsheetId": destination_spreadsheet_id},
            )
        )
