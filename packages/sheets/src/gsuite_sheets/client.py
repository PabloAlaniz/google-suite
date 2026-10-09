"""Sheets client - high-level interface."""

import logging
from typing import Any

from googleapiclient.discovery import build

from gsuite_core import GoogleAuth, authorized_http, drive_query_literal, execute, paginate
from gsuite_core.exceptions import NotFoundError
from gsuite_sheets.parser import SheetsParser
from gsuite_sheets.spreadsheet import Spreadsheet
from gsuite_sheets.worksheet import Worksheet

logger = logging.getLogger(__name__)


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
        self._sheets_service = None
        self._drive_service = None

    @property
    def service(self):
        """Lazy-load Sheets API service."""
        if self._sheets_service is None:
            self._sheets_service = build(
                "sheets", "v4", http=authorized_http(self.auth.credentials), cache_discovery=False
            )
        return self._sheets_service

    @property
    def drive(self):
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

    def get_values(self, spreadsheet_id: str, range: str) -> list[list[Any]]:
        """Get values from a range."""
        response = execute(
            self.service.spreadsheets()
            .values()
            .get(
                spreadsheetId=spreadsheet_id,
                range=range,
            ),
            "sheets",
        )
        return response.get("values", [])

    def update_values(
        self,
        spreadsheet_id: str,
        range: str,
        values: list[list[Any]],
    ) -> dict:
        """Update values in a range."""
        return execute(
            self.service.spreadsheets()
            .values()
            .update(
                spreadsheetId=spreadsheet_id,
                range=range,
                valueInputOption="USER_ENTERED",
                body={"values": values},
            ),
            "sheets",
        )

    def append_values(
        self,
        spreadsheet_id: str,
        range: str,
        values: list[list[Any]],
    ) -> dict:
        """Append values to a range."""
        return execute(
            self.service.spreadsheets()
            .values()
            .append(
                spreadsheetId=spreadsheet_id,
                range=range,
                valueInputOption="USER_ENTERED",
                insertDataOption="INSERT_ROWS",
                body={"values": values},
            ),
            "sheets",
        )

    def clear_values(self, spreadsheet_id: str, range: str) -> dict:
        """Clear values from a range."""
        return execute(
            self.service.spreadsheets()
            .values()
            .clear(
                spreadsheetId=spreadsheet_id,
                range=range,
            ),
            "sheets",
        )

    def batch_update(
        self,
        spreadsheet_id: str,
        data: list[dict],
    ) -> dict:
        """
        Batch update multiple ranges.

        Args:
            spreadsheet_id: Spreadsheet ID
            data: List of {range, values} dicts
        """
        return execute(
            self.service.spreadsheets()
            .values()
            .batchUpdate(
                spreadsheetId=spreadsheet_id,
                body={
                    "valueInputOption": "USER_ENTERED",
                    "data": [{"range": d["range"], "values": d["values"]} for d in data],
                },
            ),
            "sheets",
        )

    # ========== Worksheet operations ==========

    def add_worksheet(
        self,
        spreadsheet_id: str,
        title: str,
        rows: int = 1000,
        cols: int = 26,
    ) -> Worksheet:
        """Add a worksheet to a spreadsheet."""
        response = execute(
            self.service.spreadsheets().batchUpdate(
                spreadsheetId=spreadsheet_id,
                body={
                    "requests": [
                        {
                            "addSheet": {
                                "properties": {
                                    "title": title,
                                    "gridProperties": {
                                        "rowCount": rows,
                                        "columnCount": cols,
                                    },
                                },
                            },
                        }
                    ],
                },
            ),
            "sheets",
        )

        return SheetsParser.parse_worksheet_from_reply(response["replies"][0]["addSheet"])

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
