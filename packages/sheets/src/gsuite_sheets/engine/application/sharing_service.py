"""Servicio de permisos: compartir, listar permisos y quitar permisos.

Opera sobre un documento duck-typed (el facade resuelve el documento por nombre).
"""

from __future__ import annotations

from typing import Any


class SharingService:
    """Casos de uso de compartición y permisos de un documento."""

    def share(
        self,
        spreadsheet: Any,
        email_address: str,
        role: str,
        perm_type: str,
        notify: bool,
        email_message: str | None,
        with_link: bool,
    ) -> Any:
        """Comparte el documento con un usuario/grupo/dominio o con cualquiera."""
        return spreadsheet.share(
            email_address,
            perm_type=perm_type,
            role=role,
            notify=notify,
            email_message=email_message,
            with_link=with_link,
        )

    def list_permissions(self, spreadsheet: Any) -> list[dict[str, Any]]:
        """Lista los permisos del documento."""
        result: list[dict[str, Any]] = spreadsheet.list_permissions()
        return result

    def remove_permission(self, spreadsheet: Any, value: str, role: str) -> list[str]:
        """Quita el permiso de un usuario/grupo/dominio; devuelve los IDs eliminados."""
        result: list[str] = spreadsheet.remove_permissions(value, role=role)
        return result
