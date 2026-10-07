# Migrating from GSpreadManager

GSpreadManager is now part of gsuite-sdk: its engine runs behind
`gsuite_sheets.Sheets` / `Spreadsheet` / `Worksheet`. The `GSpreadManager`
package stays on PyPI at 0.1.5 and won't get new releases.

```bash
pip uninstall GSpreadManager
pip install gsuite-sdk                 # + "gsuite-sdk[pandas]" or "[polars]" for DataFrames
```

## Authentication

GSpreadManager used a service account file; gsuite-sdk supports it too (and
OAuth user login, shared with Gmail/Drive/Calendar):

```python
from gsuite_core import GoogleAuth, Scopes
from gsuite_sheets import Sheets

auth = GoogleAuth.from_service_account("credentials.json", scopes=Scopes.sheets() + Scopes.drive())
sheets = Sheets(auth)
```

Share the spreadsheet with the service account's email, as before.

## From 0.1.5 (`GoogleSheetConector`)

| GSpreadManager 0.1.5 | gsuite-sdk |
|---|---|
| `c = GoogleSheetConector(doc, json_file, sheet_name)` | `ws = Sheets(auth).open(doc).worksheet(sheet_name)` |
| `c.read_sheet_data(output_format="list")` | `ws.get_all_values()` |
| `c.read_sheet_data(output_format="dict")` | `ws.get_all_records()` |
| `c.read_sheet_data(output_format="pandas")` | `ws.read_dataframe()` |
| `c.read_sheet_data(skiprows=n)` | `ws.read_dataframe(skiprows=n)` / `ws.get_all_values()[n:]` |
| `c.spreadsheet_append(data, tab_name)` | `doc.worksheet(tab_name).append_rows(data)` |
| `c.update_cell(sheet, row, col, value)` | `ws.update_cell(row, col, value)` |
| `c.update_row(sheet, row, data, start_column)` | `ws.update_row(row, data, start_column)` |
| `c.spreadsheet_read_range(sheet, tab, r1, r2, "A", "D")` | `doc.worksheet(tab).get(f"A{r1}:D{r2}")` |
| `c.get_rows_where_column_equals(column, value)` | `ws.rows_where_column_equals(column, value)` (0-based column) |
| `c.batch_update(range_data)` | `ws.batch_update(range_data)` |
| `c.get_last_row(tab_name)` | `ws.last_row()` |
| `c.get_row_with_empty_in_column(sheet, "B")` | `ws.row_with_empty_in_column("B")` |
| `c.spreadsheet_insert(sheet, tab, data, fila=n)` | `ws.insert(data, row=n)` |

`ws.insert(data, row=n)` really inserts at row `n`, shifting rows down.
GSpreadManager sent a `values.append` starting at that row, which Google
treats as "append after the table found there", so the data ended up at the
end of the table.

### Example

```python
# Before
from gspreadmanager import GoogleSheetConector

sheet = GoogleSheetConector(doc_name="Inversiones", json_google_file="creds.json")
sheet.spreadsheet_append([[today, total]])
df = sheet.read_sheet_data(tab_name="Total diario", output_format="pandas")

# After
from gsuite_core import GoogleAuth, Scopes
from gsuite_sheets import Sheets

auth = GoogleAuth.from_service_account("creds.json", scopes=Scopes.sheets() + Scopes.drive())
doc = Sheets(auth).open("Inversiones")
doc.sheet1.append_row([today, total])
df = doc.worksheet("Total diario").read_dataframe()
```

## From 2.x / 3.0 (`SheetManager`)

Most `WorksheetContext` methods keep their names on `Worksheet`
(`upsert`, `update_where`, `iter_rows`, `read_as`, `add_dropdown`,
`add_chart`, `sort_range`, `insert_rows`, ...). The differences:

| GSpreadManager 3.0 | gsuite-sdk |
|---|---|
| `SheetManager("Doc", json_google_file=...)` | `Sheets(auth).open("Doc")` |
| `SheetManager(key=...)` / `.open_by_url(url)` | `sheets.open_by_key(key)` / `sheets.open_by_url(url)` |
| `SheetManager(..., cache=True, rate_limit=...)` | `Sheets(auth, cache=True)`; retries and rate-limit handling are built in |
| `SheetManager(..., dataframe_backend="polars")` | `Sheets(auth, dataframe_backend="polars")` |
| `mgr.worksheet("Tab")` | `doc.worksheet("Tab")` |
| `mgr.list_worksheets()` | `doc.worksheets` |
| `mgr.worksheet_by_index(i)` | `doc.get_worksheet(i)` |
| `mgr.create_sheet(t)` / `mgr.delete_sheet(t)` | `doc.add_worksheet(t)` / `doc.del_worksheet(ws)` |
| `mgr.create_spreadsheet(t)` / `copy_spreadsheet` / `delete_spreadsheet` | `sheets.create(t)` / `sheets.copy(id)` / `sheets.delete(id)` |
| `mgr.export(ExportFormat.PDF)` | `doc.export("pdf")` |
| `ws.read(output_format=...)` | `ws.get_all_values()` / `get_all_records()` / `read_dataframe()` |
| `ws.read_range(...)` | `ws.get("A1:D10")` |
| `ws.append(data)` | `ws.append_rows(data)` |
| `ws.insert(data, fila=n)` | `ws.insert(data, row=n)` (now really inserts; see above) |
| `ws.format_range(r, CellFormat(...))` | `ws.format(r, CellFormat(...))` |
| `ws.add_protected_range(r)` | `ws.protect(r, editors=[...])` |
| `ws.find_replace(...)` | `ws.replace(find, replacement, regex=...)` |
| `AsyncSheetManager` | not yet; async is planned for the whole suite |
| `backend="gspread"` / `"native"` | not needed: requests go through google-suite's client |
| `gspreadmanager.testing.InMemoryBackend` | `gsuite_sheets.engine.testing.InMemoryBackend` + `fake_sheets(backend.client)` |

Errors are subclasses of `gsuite_core.exceptions.GSuiteError`; the
GSpreadManager names (`SchemaError`, `WorksheetNotFoundError`, ...) are
importable from `gsuite_sheets`.
