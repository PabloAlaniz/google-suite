"""Helpers internos de serialización para los value objects de formato."""

from __future__ import annotations

from typing import Any


def compact(data: dict[str, Any]) -> dict[str, Any]:
    """Elimina las claves con valor None (la API rechaza nulos en varios campos)."""
    return {k: v for k, v in data.items() if v is not None}
