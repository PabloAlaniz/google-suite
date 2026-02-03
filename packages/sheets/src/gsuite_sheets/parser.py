"""Sheets response parsers - converts API responses to domain entities."""

from gsuite_sheets.spreadsheet import Spreadsheet
from gsuite_sheets.worksheet import Worksheet


class SheetsParser:
    """Parser for Sheets API responses."""

    @staticmethod
    def parse_spreadsheet(data: dict) -> Spreadsheet:
        """
        Parse Sheets API response to Spreadsheet entity.

        Args:
            data: Raw API response dict

        Returns:
            Spreadsheet entity (without client reference)
        """
        props = data.get("properties", {})

        worksheets = [SheetsParser.parse_worksheet(sheet) for sheet in data.get("sheets", [])]

        return Spreadsheet(
            id=data["spreadsheetId"],
            title=props.get("title", ""),
            url=f"https://docs.google.com/spreadsheets/d/{data['spreadsheetId']}",
            locale=props.get("locale", "en_US"),
            time_zone=props.get("timeZone", "America/New_York"),
            worksheets=worksheets,
        )

    @staticmethod
    def parse_worksheet(data: dict) -> Worksheet:
        """
        Parse sheet data to Worksheet entity.

        Args:
            data: Raw sheet dict from API (with "properties" key)

        Returns:
            Worksheet entity
        """
        props = data.get("properties", {})
        grid_props = props.get("gridProperties", {})

        return Worksheet(
            id=props.get("sheetId", 0),
            title=props.get("title", ""),
            index=props.get("index", 0),
            row_count=grid_props.get("rowCount", 1000),
            column_count=grid_props.get("columnCount", 26),
        )

    @staticmethod
    def parse_worksheet_from_reply(data: dict) -> Worksheet:
        """
        Parse worksheet from batchUpdate reply.

        Args:
            data: Reply dict with "addSheet" > "properties"

        Returns:
            Worksheet entity
        """
        props = data["properties"]
        grid_props = props.get("gridProperties", {})

        return Worksheet(
            id=props["sheetId"],
            title=props["title"],
            index=props["index"],
            row_count=grid_props.get("rowCount", 1000),
            column_count=grid_props.get("columnCount", 26),
        )
