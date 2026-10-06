"""Servicio de permisos: compartir, listar permisos y quitar permisos.

Opera sobre ``SpreadsheetPort`` (el facade resuelve el documento por nombre).
"""

from __future__ import annotations

from typing import Any

from gspreadmanager.ports.sheets import SpreadsheetPort


class SharingService:
    """Casos de uso de compartición y permisos de un documento."""

    def share(
        self,
        spreadsheet: SpreadsheetPort,
        email_address: str,
        role: str,
        perm_type: str,
        notify: bool,
        email_message: str | None,
        with_link: bool,
    ) -> Any:
        """Comparte el documento con un usuario/grupo/dominio o con cualquiera."""
        return spreadsheet.share(email_address, perm_type, role, notify, email_message, with_link)

    def list_permissions(self, spreadsheet: SpreadsheetPort) -> list[dict[str, Any]]:
        """Lista los permisos del documento."""
        return spreadsheet.list_permissions()

    def remove_permission(self, spreadsheet: SpreadsheetPort, value: str, role: str) -> list[str]:
        """Quita el permiso de un usuario/grupo/dominio; devuelve los IDs eliminados."""
        return spreadsheet.remove_permissions(value, role)
