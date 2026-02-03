# gsuite-sheets

Simple, Pythonic Google Sheets API client.

## Installation

```bash
pip install gsuite-sheets
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
# Open by ID (from URL)
# URL: https://docs.google.com/spreadsheets/d/SPREADSHEET_ID/edit
spreadsheet = sheets.open("1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms")

# Open by name (searches your Drive)
spreadsheet = sheets.open_by_name("My Budget 2026")

# Open by URL
spreadsheet = sheets.open_by_url(
    "https://docs.google.com/spreadsheets/d/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms/edit"
)

# Create new spreadsheet
spreadsheet = sheets.create("New Spreadsheet")
```

## Spreadsheet Properties

```python
spreadsheet = sheets.open("spreadsheet_id")

# Basic info
spreadsheet.id          # Spreadsheet ID
spreadsheet.title       # Title
spreadsheet.url         # Full URL
spreadsheet.locale      # Locale (en_US, etc)
spreadsheet.timezone    # Timezone

# List worksheets
for ws in spreadsheet.worksheets:
    print(f"{ws.title} ({ws.row_count} rows, {ws.col_count} cols)")

# Get specific worksheet
sheet1 = spreadsheet.worksheet("Sheet1")
sheet1 = spreadsheet[0]  # By index
```

## Reading Data

```python
ws = spreadsheet.worksheet("Data")

# Get single cell
value = ws.get("A1")

# Get range
values = ws.get("A1:C10")
# Returns: [["Name", "Age", "City"], ["Alice", 30, "NYC"], ...]

# Get entire column
col_a = ws.get("A:A")

# Get entire row
row_1 = ws.get("1:1")

# Get all data
all_data = ws.get_all_values()

# Get as list of dicts (first row = headers)
records = ws.get_all_records()
# Returns: [{"Name": "Alice", "Age": 30, "City": "NYC"}, ...]

# Get specific cell by row/col (1-indexed)
value = ws.cell(row=2, col=3)
```

## Writing Data

```python
ws = spreadsheet.worksheet("Data")

# Update single cell
ws.update("A1", "Hello")

# Update range
ws.update("A1:C2", [
    ["Name", "Age", "City"],
    ["Alice", 30, "NYC"],
])

# Append rows (adds to end of data)
ws.append([
    ["Bob", 25, "LA"],
    ["Charlie", 35, "Chicago"],
])

# Update specific cell by row/col
ws.update_cell(row=2, col=1, value="Updated")

# Clear range
ws.clear("A1:C10")

# Clear entire worksheet
ws.clear()
```

## Working with Worksheets

```python
# Add new worksheet
new_sheet = spreadsheet.add_worksheet(
    title="Q1 Data",
    rows=100,
    cols=20,
)

# Duplicate worksheet
copy = spreadsheet.duplicate_worksheet(
    source_sheet_id=sheet1.id,
    new_name="Sheet1 Copy",
)

# Delete worksheet
spreadsheet.delete_worksheet(new_sheet)

# Rename worksheet
sheet1.update_title("Renamed Sheet")

# Resize worksheet
sheet1.resize(rows=500, cols=50)
```

## Formatting

```python
# Bold header row
ws.format("A1:Z1", {
    "textFormat": {"bold": True},
    "backgroundColor": {"red": 0.9, "green": 0.9, "blue": 0.9},
})

# Number format
ws.format("B2:B100", {
    "numberFormat": {"type": "CURRENCY", "pattern": "$#,##0.00"},
})

# Date format
ws.format("C2:C100", {
    "numberFormat": {"type": "DATE", "pattern": "yyyy-mm-dd"},
})

# Freeze rows/columns
ws.freeze(rows=1)  # Freeze header row
ws.freeze(cols=2)  # Freeze first 2 columns
ws.freeze(rows=1, cols=1)  # Both
```

## Batch Operations

For better performance with multiple operations:

```python
# Batch update (single API call)
ws.batch_update([
    {"range": "A1", "values": [["Header 1"]]},
    {"range": "B1", "values": [["Header 2"]]},
    {"range": "C1", "values": [["Header 3"]]},
])

# Batch get
results = ws.batch_get(["A1:A10", "C1:C10", "E1:E10"])
```

## Pandas Integration

```python
import pandas as pd

# Read to DataFrame
df = ws.to_dataframe()

# With custom options
df = ws.to_dataframe(
    header_row=1,        # Which row has headers (1-indexed)
    start_row=2,         # Start reading data from
    columns=["A", "B", "C"],  # Only these columns
)

# Write DataFrame
ws.from_dataframe(df)

# With options
ws.from_dataframe(
    df,
    start_cell="A1",
    include_headers=True,
    include_index=False,
)
```

## Named Ranges

```python
# Create named range
spreadsheet.create_named_range(
    name="SalesData",
    range="Sales!A1:D100",
)

# Get named range
data = spreadsheet.get_named_range("SalesData")

# List named ranges
for nr in spreadsheet.named_ranges:
    print(f"{nr.name}: {nr.range}")
```

## Find and Replace

```python
# Find cells containing text
cells = ws.find("searchterm")
for cell in cells:
    print(f"Found at {cell.address}: {cell.value}")

# Find with regex
import re
cells = ws.find(re.compile(r"\d{3}-\d{4}"))  # Phone pattern

# Find and replace
ws.replace("old text", "new text")

# Replace with regex
ws.replace(re.compile(r"Mr\."), "Mr", regex=True)
```

## Error Handling

```python
from gsuite_core.exceptions import (
    GsuiteError,
    NotFoundError,
    PermissionDeniedError,
)

try:
    spreadsheet = sheets.open("nonexistent_id")
except NotFoundError:
    print("Spreadsheet not found")
except PermissionDeniedError:
    print("No access to this spreadsheet")
except GsuiteError as e:
    print(f"Sheets error: {e}")
```

## Configuration

Uses `gsuite-core` settings. See [gsuite-core README](../core/README.md) for auth configuration.

## License

MIT
