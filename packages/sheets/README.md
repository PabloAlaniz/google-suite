# gsuite-sheets

Simple, Pythonic Google Sheets API client.

## Installation

```bash
pip install gsuite-sdk
pip install "gsuite-sdk[pandas]"   # DataFrame support
```

## Quick Start

```python
from gsuite_core import GoogleAuth
from gsuite_sheets import Sheets

# Authenticate
auth = GoogleAuth()
auth.authenticate()  # Opens browser for consent

sheets = Sheets(auth)
```

## Opening Spreadsheets

```python
# By ID (from the URL: https://docs.google.com/spreadsheets/d/SPREADSHEET_ID/edit)
spreadsheet = sheets.open_by_key("1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms")

# By title (searches your Drive; raises ValueError if none matches)
spreadsheet = sheets.open("My Budget 2026")

# By URL
spreadsheet = sheets.open_by_url(
    "https://docs.google.com/spreadsheets/d/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms/edit"
)

# Create, list
spreadsheet = sheets.create("New Spreadsheet")
for item in sheets.list_spreadsheets(max_results=None):   # {"id", "name"}
    print(item["name"])
```

## Spreadsheet Properties

```python
spreadsheet.id
spreadsheet.title
spreadsheet.url
spreadsheet.locale       # "en_US"
spreadsheet.time_zone    # "America/Argentina/Buenos_Aires"

for ws in spreadsheet.worksheets:
    print(f"{ws.title} ({ws.row_count} rows, {ws.column_count} cols)")

ws = spreadsheet.sheet1              # first tab
ws = spreadsheet.worksheet("Data")   # by title, or None
ws = spreadsheet.get_worksheet(2)    # by index, or None
```

## Reading Data

Ranges are A1 notation without the sheet title; the title is added and
quoted for you, so tabs named "2024" or "Pablo's" work.

```python
ws = spreadsheet.worksheet("Data")

ws.get("A1:C10")             # 2D list
ws.get("A:A")                # whole column
ws.get("1:1")                # whole row
ws.get_all_values()          # the whole sheet
ws.get_all_records()         # list of dicts keyed by the first row
ws.cell(row=2, col=3)
ws.row_values(1)
ws.col_values(2)

# Several ranges, one request
names, totals = ws.batch_get(["A2:A100", "D2:D100"])

# Numbers as numbers, or formulas instead of results
ws.get("B2:B10", value_render="UNFORMATTED_VALUE")
ws.get("B2:B10", value_render="FORMULA")
```

## Writing Data

```python
ws.update("A1:C2", [
    ["Name", "Age", "City"],
    ["Alice", 30, "NYC"],
])
ws.update_cell(row=2, col=1, value="Updated")
ws.append_row(["Bob", 25, "LA"])
ws.append_rows([["Carol", 35, "Chicago"], ["Dan", 41, "Austin"]])

ws.clear("A1:C10")
ws.clear()                   # whole sheet (formatting is kept)
```

Values are parsed like typed into the UI by default (`"=SUM(A1:A3)"`
becomes a formula, `"2026-01-01"` a date). Write untrusted text with
`value_input="RAW"` so a value starting with `=` stays text:

```python
ws.update("A2", [[user_comment]], value_input="RAW")
```

## Managing Worksheets

```python
new = spreadsheet.add_worksheet("Q2", rows=500, cols=10)
copy = spreadsheet.duplicate_worksheet(new, "Q2 backup")
new.rename("Q2 2026")
spreadsheet.del_worksheet(copy)   # the last remaining sheet can't be deleted
```

## Formatting

```python
# Bold header row; only the keys you pass are changed
ws.format("A1:Z1", {
    "textFormat": {"bold": True},
    "backgroundColor": {"red": 0.9, "green": 0.9, "blue": 0.9},
})

ws.format("B2:B100", {"numberFormat": {"type": "CURRENCY", "pattern": "$#,##0.00"}})
ws.format("C2:C100", {"numberFormat": {"type": "DATE", "pattern": "yyyy-mm-dd"}})

ws.freeze(rows=1)            # header row
ws.freeze(rows=1, cols=2)
ws.freeze(rows=0)            # unfreeze rows
```

## Protecting Ranges

```python
ws.protect("A1:A100", description="IDs", editors=["admin@example.com"])
ws.protect(warning_only=True)   # whole sheet, warn before editing
```

## Find and Replace

```python
import re

ws.find("Total")                          # (row, col) of the first exact match, or None
ws.findall(re.compile(r"\d{3}-\d{4}"))     # regex: all matching cells

# Server-side replace; returns how many cells changed
ws.replace("old text", "new text")
ws.replace(r"Mr\.", "Mr", regex=True)
sheets.find_replace(spreadsheet.id, "2025", "2026")   # every sheet
```

## pandas

Needs `pip install "gsuite-sdk[pandas]"`.

```python
df = ws.to_dataframe()                # first row as headers
df = ws.to_dataframe(header_row=2)    # skip a title row

ws.from_dataframe(df)                       # header + rows at A1
ws.from_dataframe(df, start="B3", include_index=True, clear=True)
```

Values come back as displayed text; convert types in pandas. NaN/NaT
become empty cells and dates are written as ISO strings.

## Tables: upsert, filters, streaming

```python
ws.upsert([{"id": "7", "status": "paid"}, {"id": "8", "status": "new"}], key="id")
# -> {"updated": 1, "appended": 1}; big writes are split into several requests

ws.update_where({"status": "new"}, {"status": "pending"})        # -> rows changed
ws.delete_where(lambda row: row["status"] == "cancelled")         # predicate or dict

for row in ws.iter_rows(page_size=1000):      # lazily, page by page
    ...
for record in ws.iter_records():              # {header: value}
    ...

ws.insert([["new", "row"]], row=2)            # shifts the rest down
ws.last_row()                                 # 1-based, 0 if empty
ws.import_csv(open("data.csv"))               # replaces the sheet's contents
```

## Typed Rows (dataclasses or Pydantic)

```python
from dataclasses import dataclass
from datetime import date

@dataclass
class Invoice:
    id: str
    amount: float
    due: date | None = None

ws.ensure_schema(Invoice)          # writes the header if empty, raises SchemaError on drift
ws.append_models([Invoice("7", 120.5, date(2026, 3, 1))])
invoices = ws.read_as(Invoice)     # values converted to the field types
ws.upsert_models(invoices, key="id")
for inv in ws.iter_as(Invoice):
    ...
```

## Validation and Conditional Formatting

```python
from gsuite_sheets import CellFormat, Color, TextFormat

ws.add_dropdown("E2:E100", ["Pending", "In progress", "Done"])
ws.add_checkbox("F2:F100")
ws.set_data_validation("B2:B100", "NUMBER_GREATER", [0])
ws.add_conditional_format(
    "C2:C100", "NUMBER_LESS", [0],
    CellFormat(background_color=Color.from_hex("#F4CCCC"), text_format=TextFormat(bold=True)),
)

ws.format("A1:D1", CellFormat(background_color=Color.from_hex("#0B5394")))  # or a raw dict
ws.format_header()
ws.set_number_format("C2:C100", "#,##0.00", "CURRENCY")
ws.merge("A1:D1")
ws.set_tab_color(Color.from_hex("#D9EAD3"))
```

## Rows, Columns, Sorting, Filters

```python
ws.insert_rows(2, 3); ws.delete_cols(5); ws.add_rows(100)
ws.resize_cols(1, 3, 160); ws.hide_rows(10, 20)
ws.sort_range("A2:C100", (2, "desc"), (1, "asc"))
ws.set_basic_filter("A1:C100")
```

## Notes, Named Ranges, Metadata

```python
ws.update_note("B2", "check this"); ws.get_note("B2")
ws.define_named_range("Totals", "D2:D100"); doc.list_named_ranges()
doc.set_developer_metadata("source", "erp")
```

## Charts, Pivot Tables, Banding

```python
chart_id = ws.add_chart("COLUMN", "A1:A12", ["B1:B12", "C1:C12"], title="Sales", anchor_cell="E2")
ws.add_pivot_table("A1:C100", "H1", rows=[1], values=[(3, "SUM")])
ws.set_banding("A1:C100", first_color=Color.from_hex("#FFFFFF"), second_color=Color.from_hex("#F3F3F3"))
```

## Export, Copy, Spreadsheet Settings

```python
pdf = doc.export("pdf")            # also xlsx, ods, csv/tsv (first sheet), html (zip)
copy = sheets.copy(doc.id, title="Backup", copy_permissions=True)
sheets.delete(copy.id)
doc.update_timezone("America/Argentina/Buenos_Aires")
doc.worksheet_or_create("Log")
```

## Options: cache, DataFrame backend, chunking

```python
sheets = Sheets(
    auth,
    cache=True,                 # cache reads made by the features above; this client's writes invalidate it
    cache_ttl=60,
    dataframe_backend="polars", # read_dataframe / write_dataframe (pip install "gsuite-sdk[polars]")
    batch_cell_limit=50_000,    # split big writes
)
df = ws.read_dataframe(drop_empty_rows=True, index_col="id")
sheets.clear_cache()
```

## Async

Values, streaming, tables and typed rows are also available async
(`pip install "gsuite-sdk[async]"`; see [docs/ASYNC.md](../../docs/ASYNC.md)):

```python
from gsuite_sheets import AsyncSheets

async with AsyncSheets(auth) as sheets:
    ws = (await sheets.open("Budget")).worksheet("Data")
    await ws.upsert(rows, key="id")
    async for record in ws.iter_records():
        ...
```

## Testing Without Google

The same emulator the SDK is tested with is available to your tests:

```python
from gsuite_sheets.engine.testing import InMemoryBackend
from gsuite_sheets.engine.testing.google_api_fake import fake_sheets

backend = InMemoryBackend()
backend.add_spreadsheet("Budget", {"Data": [["name", "total"]]})
sheets = fake_sheets(backend.client)          # a real Sheets client, no network
sheets.open("Budget").worksheet("Data").append_row(["Ana", 10])
```

These features come from [GSpreadManager](https://github.com/PabloAlaniz/google-suite/tree/archive/gspreadmanager),
now part of gsuite-sdk; see [the migration guide](../../docs/MIGRATING_FROM_GSPREADMANAGER.md).

## Anything Else

Requests this client doesn't wrap (charts, conditional formatting, named
ranges, ...) can be sent as raw `spreadsheets.batchUpdate` requests:

```python
from gsuite_sheets.a1 import grid_range

sheets.batch_requests(spreadsheet.id, [
    {"addNamedRange": {"namedRange": {"name": "Totals", "range": grid_range("D2:D100", ws.id)}}},
])
```

## Error Handling

```python
from gsuite_core.exceptions import (
    GSuiteError,
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)

try:
    spreadsheet = sheets.open_by_key("nonexistent_id")
except NotFoundError:
    print("Spreadsheet not found")
except PermissionDeniedError:
    print("No access to this spreadsheet")
except ValidationError as e:   # e.g. an invalid A1 range
    print(e.field, e.message)
except GSuiteError as e:
    print(f"Sheets error: {e}")
```

## Configuration

Uses `gsuite-core` settings. See [gsuite-core README](../core/README.md) for auth configuration.

## License

MIT
