"""Servicio de metadata: notas, named/protected ranges y developer metadata.

Las escrituras son requests de ``spreadsheets:batchUpdate``; las lecturas usan
``SpreadsheetPort.get_metadata`` (``spreadsheets.get`` con ``fields``). Recibe el
``GridRange`` ya resuelto (la conversión A1 -> GridRange vive en el facade).
"""

from __future__ import annotations

from typing import Any

from gspreadmanager.domain.values import DeveloperMetadataEntry, GridRange
from gspreadmanager.ports.sheets import SpreadsheetPort, WorksheetPort


class MetadataService:
    """Casos de uso de notas, named ranges y protected ranges."""

    def _apply(self, spreadsheet: SpreadsheetPort, request: dict[str, Any]) -> None:
        spreadsheet.batch_update({"requests": [request]})

    # ------------------------------------------------------------------
    # Notas de celda
    # ------------------------------------------------------------------

    def set_note(self, worksheet: WorksheetPort, grid_range: GridRange, text: str) -> None:
        """Fija (o limpia, con ``text=""``) la nota de una celda."""
        request = {
            "updateCells": {
                "range": grid_range.to_dict(),
                "rows": [{"values": [{"note": text}]}],
                "fields": "note",
            }
        }
        self._apply(worksheet.spreadsheet, request)

    def get_note(self, worksheet: WorksheetPort, a1_with_sheet: str) -> str:
        """Devuelve la nota de una celda (cadena vacía si no tiene)."""
        meta = worksheet.spreadsheet.get_metadata(
            [a1_with_sheet], "sheets(data(rowData(values(note))))"
        )
        for sheet in meta.get("sheets", []):
            for data in sheet.get("data", []):
                for row in data.get("rowData", []):
                    for value in row.get("values", []):
                        note = value.get("note")
                        if note is not None:
                            return str(note)
        return ""

    # ------------------------------------------------------------------
    # Named ranges
    # ------------------------------------------------------------------

    def define_named_range(
        self, worksheet: WorksheetPort, name: str, grid_range: GridRange
    ) -> None:
        """Define un named range que apunta a ``grid_range``."""
        request = {"addNamedRange": {"namedRange": {"name": name, "range": grid_range.to_dict()}}}
        self._apply(worksheet.spreadsheet, request)

    def list_named_ranges(self, spreadsheet: SpreadsheetPort) -> list[dict[str, Any]]:
        """Lista los named ranges del documento."""
        result: list[dict[str, Any]] = spreadsheet.get_metadata(None, "namedRanges").get(
            "namedRanges", []
        )
        return result

    def delete_named_range(self, spreadsheet: SpreadsheetPort, named_range_id: str) -> None:
        """Elimina un named range por su id."""
        self._apply(spreadsheet, {"deleteNamedRange": {"namedRangeId": named_range_id}})

    # ------------------------------------------------------------------
    # Protected ranges
    # ------------------------------------------------------------------

    def add_protected_range(
        self,
        worksheet: WorksheetPort,
        grid_range: GridRange,
        description: str | None,
        warning_only: bool,
    ) -> None:
        """Protege un rango (``warning_only`` solo advierte en vez de bloquear)."""
        protected: dict[str, Any] = {"range": grid_range.to_dict(), "warningOnly": warning_only}
        if description is not None:
            protected["description"] = description
        self._apply(worksheet.spreadsheet, {"addProtectedRange": {"protectedRange": protected}})

    def list_protected_ranges(self, worksheet: WorksheetPort) -> list[dict[str, Any]]:
        """Lista los rangos protegidos de la hoja."""
        meta = worksheet.spreadsheet.get_metadata(
            None, "sheets(properties.sheetId,protectedRanges)"
        )
        for sheet in meta.get("sheets", []):
            if sheet.get("properties", {}).get("sheetId") == worksheet.id:
                ranges: list[dict[str, Any]] = sheet.get("protectedRanges", [])
                return ranges
        return []

    def delete_protected_range(self, spreadsheet: SpreadsheetPort, protected_range_id: str) -> None:
        """Quita la protección de un rango por su id."""
        self._apply(spreadsheet, {"deleteProtectedRange": {"protectedRangeId": protected_range_id}})

    # ------------------------------------------------------------------
    # Developer metadata
    # ------------------------------------------------------------------

    def set_developer_metadata(
        self,
        spreadsheet: SpreadsheetPort,
        entry: DeveloperMetadataEntry,
        sheet_id: int | None,
    ) -> None:
        """Crea developer metadata anclada a una hoja (o al documento si ``sheet_id=None``)."""
        self._apply(spreadsheet, entry.to_request(sheet_id))

    def list_developer_metadata(self, spreadsheet: SpreadsheetPort) -> list[dict[str, Any]]:
        """Lista la developer metadata del documento y de todas sus hojas."""
        meta = spreadsheet.get_metadata(
            None, "developerMetadata,sheets(properties(sheetId),developerMetadata)"
        )
        entries: list[dict[str, Any]] = list(meta.get("developerMetadata", []))
        for sheet in meta.get("sheets", []):
            entries.extend(sheet.get("developerMetadata", []))
        return entries

    def delete_developer_metadata(self, spreadsheet: SpreadsheetPort, key: str) -> None:
        """Elimina toda la developer metadata cuya clave sea ``key``."""
        request = {
            "deleteDeveloperMetadata": {
                "dataFilter": {"developerMetadataLookup": {"metadataKey": key}}
            }
        }
        self._apply(spreadsheet, request)
