"""Sheets client - high-level interface."""

import logging
from typing import Any, Literal

from googleapiclient.discovery import build

from gsuite_core import GoogleAuth, authorized_http, drive_query_literal, execute, paginate
from gsuite_core.exceptions import NotFoundError, ValidationError
from gsuite_sheets.a1 import grid_range
from gsuite_sheets.parser import SheetsParser
from gsuite_sheets.spreadsheet import Spreadsheet
from gsuite_sheets.worksheet import Worksheet

logger = logging.getLogger(__name__)

ValueRender = Literal["FORMATTED_VALUE", "UNFORMATTED_VALUE", "FORMULA"]
ValueInput = Literal["USER_ENTERED", "RAW"]


class Sheets:
    """
    High-level Google Sheets client.

    Inspired by gspread's simple API.

    Example:
        auth = GoogleAuth()
        auth.authenticate()

        sheets = Sheets(auth)

        # Open by title (like gspread!)
        doc = sheets.open("My Spreadsheet")

        # Or by key/url
        doc = sheets.open_by_key("abc123...")
        doc = sheets.open_by_url("https://docs.google.com/spreadsheets/...")

        # Work with worksheets
        ws = doc.sheet1
        data = ws.get_all_values()
        ws.update("A1", [["Hello", "World"]])
    """

    def __init__(self, auth: GoogleAuth):
        """
        Initialize Sheets client.

        Args:
            auth: GoogleAuth instance with valid credentials
        """
        self.auth = auth
        self._sheets_service: Any = None
        self._drive_service: Any = None

    @property
    def service(self) -> Any:
        """Lazy-load Sheets API service."""
        if self._sheets_service is None:
            self._sheets_service = build(
                "sheets", "v4", http=authorized_http(self.auth.credentials), cache_discovery=False
            )
        return self._sheets_service

    @property
    def drive(self) -> Any:
        """Lazy-load Drive API service (for listing/sharing)."""
        if self._drive_service is None:
            self._drive_service = build(
                "drive", "v3", http=authorized_http(self.auth.credentials), cache_discovery=False
            )
        return self._drive_service

    # ========== Opening spreadsheets (gspread-style) ==========

    def open(self, title: str) -> Spreadsheet:
        """
        Open a spreadsheet by title.

        Args:
            title: Spreadsheet title

        Returns:
            Spreadsheet object

        Raises:
            ValueError: If not found
        """
        # Search in Drive
        response = execute(
            self.drive.files().list(
                q=(
                    f"name={drive_query_literal(title)}"
                    " and mimeType='application/vnd.google-apps.spreadsheet' and trashed=false"
                ),
                fields="files(id, name)",
                pageSize=1,
            ),
            "sheets",
            "spreadsheet",
            title,
        )

        files = response.get("files", [])
        if not files:
            raise ValueError(f"Spreadsheet not found: {title}")

        return self.open_by_key(files[0]["id"])

    def open_by_key(self, key: str) -> Spreadsheet:
        """
        Open a spreadsheet by key (ID).

        Args:
            key: Spreadsheet ID

        Returns:
            Spreadsheet object
        """
        response = execute(
            self.service.spreadsheets().get(
                spreadsheetId=key,
                fields="spreadsheetId,properties,sheets.properties",
            ),
            "sheets",
            "spreadsheet",
            key,
        )

        return self._parse_spreadsheet(response)

    def open_by_url(self, url: str) -> Spreadsheet:
        """
        Open a spreadsheet by URL.

        Args:
            url: Full Google Sheets URL

        Returns:
            Spreadsheet object
        """
        # Extract key from URL
        import re

        match = re.search(r"/spreadsheets/d/([a-zA-Z0-9-_]+)", url)
        if not match:
            raise ValueError(f"Invalid Google Sheets URL: {url}")

        return self.open_by_key(match.group(1))

    # ========== Creating spreadsheets ==========

    def create(self, title: str) -> Spreadsheet:
        """
        Create a new spreadsheet.

        Args:
            title: Spreadsheet title

        Returns:
            Created Spreadsheet
        """
        body = {
            "properties": {"title": title},
            "sheets": [{"properties": {"title": "Sheet1"}}],
        }

        response = execute(self.service.spreadsheets().create(body=body), "sheets", "spreadsheet")
        return self._parse_spreadsheet(response)

    # ========== Listing ==========

    def list_spreadsheets(self, max_results: int | None = 100) -> list[dict]:
        """
        List all spreadsheets accessible to the user.

        Args:
            max_results: Maximum spreadsheets to return (None = all)

        Returns:
            List of {id, name} dicts
        """
        return list(
            paginate(
                self.drive.files().list,
                "files",
                "sheets",
                max_items=max_results,
                page_size_param="pageSize",
                max_page_size=1000,
                q="mimeType='application/vnd.google-apps.spreadsheet' and trashed=false",
                fields="nextPageToken, files(id, name)",
                orderBy="modifiedTime desc",
            )
        )

    # ========== Low-level operations ==========

    def get_values(
        self,
        spreadsheet_id: str,
        range: str,
        value_render: ValueRender = "FORMATTED_VALUE",
    ) -> list[list[Any]]:
        """
        Get values from a range.

        Args:
            spreadsheet_id: Spreadsheet ID
            range: A1 range including the sheet, e.g. "'Sheet 1'!A1:C10"
            value_render: FORMATTED_VALUE (as displayed), UNFORMATTED_VALUE
                (numbers as numbers) or FORMULA
        """
        response = execute(
            self.service.spreadsheets()
            .values()
            .get(spreadsheetId=spreadsheet_id, range=range, valueRenderOption=value_render),
            "sheets",
            "spreadsheet",
            spreadsheet_id,
        )
        values: list[list[Any]] = response.get("values", [])
        return values

    def batch_get_values(
        self,
        spreadsheet_id: str,
        ranges: list[str],
        value_render: ValueRender = "FORMATTED_VALUE",
    ) -> list[list[list[Any]]]:
        """Get several ranges in one request; results follow the order of `ranges`."""
        response = execute(
            self.service.spreadsheets()
            .values()
            .batchGet(spreadsheetId=spreadsheet_id, ranges=ranges, valueRenderOption=value_render),
            "sheets",
            "spreadsheet",
            spreadsheet_id,
        )
        return [vr.get("values", []) for vr in response.get("valueRanges", [])]

    def update_values(
        self,
        spreadsheet_id: str,
        range: str,
        values: list[list[Any]],
        value_input: ValueInput = "USER_ENTERED",
    ) -> dict:
        """
        Update values in a range.

        Args:
            value_input: USER_ENTERED parses values as if typed into the UI
                ("=SUM(A1:A3)" becomes a formula, "2026-01-01" a date). Use RAW
                for untrusted data so text starting with "=" stays text.
        """
        result: dict = execute(
            self.service.spreadsheets()
            .values()
            .update(
                spreadsheetId=spreadsheet_id,
                range=range,
                valueInputOption=value_input,
                body={"values": values},
            ),
            "sheets",
            "spreadsheet",
            spreadsheet_id,
        )
        return result

    def append_values(
        self,
        spreadsheet_id: str,
        range: str,
        values: list[list[Any]],
        value_input: ValueInput = "USER_ENTERED",
    ) -> dict:
        """Append rows after the table found in `range` (see update_values for value_input)."""
        result: dict = execute(
            self.service.spreadsheets()
            .values()
            .append(
                spreadsheetId=spreadsheet_id,
                range=range,
                valueInputOption=value_input,
                insertDataOption="INSERT_ROWS",
                body={"values": values},
            ),
            "sheets",
            "spreadsheet",
            spreadsheet_id,
        )
        return result

    def clear_values(self, spreadsheet_id: str, range: str) -> dict:
        """Clear values from a range (formatting is kept)."""
        result: dict = execute(
            self.service.spreadsheets().values().clear(spreadsheetId=spreadsheet_id, range=range),
            "sheets",
            "spreadsheet",
            spreadsheet_id,
        )
        return result

    def batch_update(
        self,
        spreadsheet_id: str,
        data: list[dict],
        value_input: ValueInput = "USER_ENTERED",
    ) -> dict:
        """
        Batch update multiple ranges.

        Args:
            spreadsheet_id: Spreadsheet ID
            data: List of {range, values} dicts
            value_input: See update_values
        """
        result: dict = execute(
            self.service.spreadsheets()
            .values()
            .batchUpdate(
                spreadsheetId=spreadsheet_id,
                body={
                    "valueInputOption": value_input,
                    "data": [{"range": d["range"], "values": d["values"]} for d in data],
                },
            ),
            "sheets",
            "spreadsheet",
            spreadsheet_id,
        )
        return result

    def batch_requests(self, spreadsheet_id: str, requests: list[dict]) -> list[dict]:
        """
        Run raw spreadsheets.batchUpdate requests (formatting, structure, ...).

        Use for anything this client doesn't wrap; see the Sheets API
        reference for request types. Returns one reply per request.
        """
        response = execute(
            self.service.spreadsheets().batchUpdate(
                spreadsheetId=spreadsheet_id, body={"requests": requests}
            ),
            "sheets",
            "spreadsheet",
            spreadsheet_id,
        )
        replies: list[dict] = response.get("replies", [])
        return replies

    # ========== Formatting and protection ==========

    def format_range(
        self, spreadsheet_id: str, sheet_id: int, range: str, cell_format: dict
    ) -> None:
        """
        Apply a cell format to a range.

        Args:
            range: A1 range without the sheet, e.g. "A1:Z1"
            cell_format: A Sheets CellFormat, e.g.
                {"textFormat": {"bold": True},
                 "numberFormat": {"type": "CURRENCY", "pattern": "$#,##0.00"}}.
                Only the top-level keys given are changed.
        """
        if not cell_format:
            raise ValidationError("cell_format", "must not be empty")
        fields = ",".join(cell_format)
        self.batch_requests(
            spreadsheet_id,
            [
                {
                    "repeatCell": {
                        "range": grid_range(range, sheet_id),
                        "cell": {"userEnteredFormat": cell_format},
                        "fields": f"userEnteredFormat({fields})",
                    }
                }
            ],
        )

    def freeze(
        self,
        spreadsheet_id: str,
        sheet_id: int,
        rows: int | None = None,
        cols: int | None = None,
    ) -> None:
        """Freeze the first `rows` rows and/or `cols` columns (0 unfreezes)."""
        grid: dict[str, int] = {}
        if rows is not None:
            grid["frozenRowCount"] = rows
        if cols is not None:
            grid["frozenColumnCount"] = cols
        if not grid:
            raise ValidationError("rows", "give rows, cols or both")

        self.batch_requests(
            spreadsheet_id,
            [
                {
                    "updateSheetProperties": {
                        "properties": {"sheetId": sheet_id, "gridProperties": grid},
                        "fields": ",".join(f"gridProperties.{key}" for key in grid),
                    }
                }
            ],
        )

    def protect_range(
        self,
        spreadsheet_id: str,
        sheet_id: int,
        range: str | None = None,
        description: str | None = None,
        editors: list[str] | None = None,
        warning_only: bool = False,
    ) -> int:
        """
        Protect a range (or the whole sheet when range is None).

        Args:
            editors: Emails that can still edit (default: only the owner)
            warning_only: Let everyone edit but show a warning

        Returns:
            The protected range ID
        """
        protected: dict[str, Any] = {
            "range": grid_range(range, sheet_id) if range else {"sheetId": sheet_id},
            "warningOnly": warning_only,
        }
        if description:
            protected["description"] = description
        if editors and not warning_only:
            protected["editors"] = {"users": editors}

        replies = self.batch_requests(
            spreadsheet_id, [{"addProtectedRange": {"protectedRange": protected}}]
        )
        protected_id: int = replies[0]["addProtectedRange"]["protectedRange"]["protectedRangeId"]
        return protected_id

    def find_replace(
        self,
        spreadsheet_id: str,
        find: str,
        replacement: str,
        sheet_id: int | None = None,
        match_case: bool = False,
        match_entire_cell: bool = False,
        regex: bool = False,
    ) -> int:
        """
        Find and replace text, in one sheet or all of them.

        Args:
            regex: Treat `find` as a regular expression; `replacement` can
                use $1-style groups

        Returns:
            Number of occurrences changed
        """
        request: dict[str, Any] = {
            "find": find,
            "replacement": replacement,
            "matchCase": match_case,
            "matchEntireCell": match_entire_cell,
            "searchByRegex": regex,
        }
        if sheet_id is None:
            request["allSheets"] = True
        else:
            request["sheetId"] = sheet_id

        replies = self.batch_requests(spreadsheet_id, [{"findReplace": request}])
        changed: int = replies[0].get("findReplace", {}).get("occurrencesChanged", 0)
        return changed

    # ========== Worksheet operations ==========

    def add_worksheet(
        self,
        spreadsheet_id: str,
        title: str,
        rows: int = 1000,
        cols: int = 26,
    ) -> Worksheet:
        """Add a worksheet to a spreadsheet."""
        replies = self.batch_requests(
            spreadsheet_id,
            [
                {
                    "addSheet": {
                        "properties": {
                            "title": title,
                            "gridProperties": {"rowCount": rows, "columnCount": cols},
                        }
                    }
                }
            ],
        )
        return SheetsParser.parse_worksheet_from_reply(replies[0]["addSheet"])

    def rename_worksheet(self, spreadsheet_id: str, sheet_id: int, title: str) -> None:
        """Rename a worksheet."""
        self.batch_requests(
            spreadsheet_id,
            [
                {
                    "updateSheetProperties": {
                        "properties": {"sheetId": sheet_id, "title": title},
                        "fields": "title",
                    }
                }
            ],
        )

    def duplicate_worksheet(
        self,
        spreadsheet_id: str,
        sheet_id: int,
        new_title: str | None = None,
        index: int | None = None,
    ) -> Worksheet:
        """Copy a worksheet within the spreadsheet (default name: "Copy of ...")."""
        request: dict[str, Any] = {"sourceSheetId": sheet_id}
        if new_title:
            request["newSheetName"] = new_title
        if index is not None:
            request["insertSheetIndex"] = index

        replies = self.batch_requests(spreadsheet_id, [{"duplicateSheet": request}])
        return SheetsParser.parse_worksheet_from_reply(replies[0]["duplicateSheet"])

    def delete_worksheet(self, spreadsheet_id: str, sheet_id: int) -> bool:
        """
        Delete a worksheet.

        Returns:
            True if deleted, False if the spreadsheet doesn't exist. Other
            failures raise, e.g. ValidationError-like 400s when deleting the
            last remaining sheet.
        """
        try:
            execute(
                self.service.spreadsheets().batchUpdate(
                    spreadsheetId=spreadsheet_id,
                    body={"requests": [{"deleteSheet": {"sheetId": sheet_id}}]},
                ),
                "sheets",
                "spreadsheet",
                spreadsheet_id,
            )
        except NotFoundError:
            logger.warning(f"Spreadsheet not found: {spreadsheet_id}")
            return False
        logger.info(f"Deleted worksheet {sheet_id} from {spreadsheet_id}")
        return True

    # ========== Sharing ==========

    def share(
        self,
        spreadsheet_id: str,
        email: str,
        role: str = "reader",
        notify: bool = True,
    ) -> bool:
        """
        Share a spreadsheet.

        Returns:
            True if shared, False if the spreadsheet doesn't exist. Other
            failures raise.
        """
        try:
            execute(
                self.drive.permissions().create(
                    fileId=spreadsheet_id,
                    body={"type": "user", "role": role, "emailAddress": email},
                    sendNotificationEmail=notify,
                ),
                "sheets",
                "spreadsheet",
                spreadsheet_id,
            )
        except NotFoundError:
            logger.error(f"Spreadsheet not found: {spreadsheet_id}")
            return False
        logger.info(f"Shared spreadsheet {spreadsheet_id} with {email} ({role})")
        return True

    # ========== Parsing ==========

    def _parse_spreadsheet(self, data: dict) -> Spreadsheet:
        """Parse API response to Spreadsheet object."""
        spreadsheet = SheetsParser.parse_spreadsheet(data)

        # Link worksheets to spreadsheet and client
        for ws in spreadsheet.worksheets:
            ws._spreadsheet = spreadsheet

        spreadsheet._sheets = self
        return spreadsheet
