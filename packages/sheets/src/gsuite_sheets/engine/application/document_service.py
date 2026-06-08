"""Servicio de documentos (Drive): crear, eliminar, copiar y listar.

Opera sobre ``ClientPort`` (el adaptador con caché del facade).
"""

from __future__ import annotations

from typing import Any

from gspreadmanager.ports.sheets import ClientPort


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
