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
