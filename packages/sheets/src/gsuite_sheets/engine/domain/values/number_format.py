"""Value object: formato numérico."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ._serialization import compact


@dataclass(frozen=True)
class NumberFormat:
    """Formato numérico. ``type`` puede ser NUMBER, CURRENCY, PERCENT, DATE, TIME, etc."""

    type: str
    pattern: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serializa al objeto ``numberFormat`` de la Sheets API."""
        return compact({"type": self.type, "pattern": self.pattern})
