"""Servicio de documentos: crear, eliminar, copiar, listar y propiedades.

Las operaciones de Drive operan sobre ``ClientPort``; las propiedades del documento
(título, locale, zona horaria) van por ``SpreadsheetPort.batch_update``.
"""

from __future__ import annotations

from typing import Any

from gspreadmanager.ports.sheets import ClientPort, SpreadsheetPort


class DocumentService:
    """Casos de uso a nivel documento de Google Sheets (operaciones de Drive)."""

    def create(self, client: ClientPort, title: str, folder_id: str | None) -> Any:
        """Crea un nuevo documento y lo devuelve."""
        return client.create(title, folder_id)

    def delete(self, client: ClientPort, file_id: str) -> None:
        """Elimina un documento por su ID."""
        client.del_spreadsheet(file_id)

    def copy(
        self,
        client: ClientPort,
        file_id: str,
        title: str | None,
        copy_permissions: bool,
        folder_id: str | None,
    ) -> Any:
        """Crea una copia de un documento existente y la devuelve."""
        return client.copy(file_id, title, copy_permissions, folder_id)

    def list(
        self, client: ClientPort, title: str | None, folder_id: str | None
    ) -> list[dict[str, Any]]:
        """Lista los documentos accesibles (filtrando por título/carpeta si se indica)."""
        return client.list_spreadsheet_files(title, folder_id)

    # -- propiedades del documento (updateSpreadsheetProperties) ----------

    def update_title(self, spreadsheet: SpreadsheetPort, title: str) -> None:
        """Renombra el documento."""
        self._update_properties(spreadsheet, {"title": title}, "title")

    def update_locale(self, spreadsheet: SpreadsheetPort, locale: str) -> None:
        """Cambia el locale del documento (ej. ``"es_AR"``)."""
        self._update_properties(spreadsheet, {"locale": locale}, "locale")

    def update_timezone(self, spreadsheet: SpreadsheetPort, timezone: str) -> None:
        """Cambia la zona horaria del documento (ej. ``"America/Argentina/Buenos_Aires"``)."""
        self._update_properties(spreadsheet, {"timeZone": timezone}, "timeZone")

    def _update_properties(
        self, spreadsheet: SpreadsheetPort, properties: dict[str, Any], fields: str
    ) -> None:
        spreadsheet.batch_update(
            {
                "requests": [
                    {"updateSpreadsheetProperties": {"properties": properties, "fields": fields}}
                ]
            }
        )
