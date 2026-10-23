"""GA4 entities: account summaries, properties and reports."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class PropertySummary:
    """A property as listed in an account summary; ``name`` is "properties/123"."""

    name: str
    display_name: str = ""
    property_type: str | None = None
    parent: str | None = None

    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @property
    def property_id(self) -> str:
        return self.name.removeprefix("properties/")


@dataclass
class AccountSummary:
    """An account with the properties the user can see in it."""

    name: str
    account: str
    display_name: str = ""
    properties: list[PropertySummary] = field(default_factory=list)

    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @property
    def account_id(self) -> str:
        return self.account.removeprefix("accounts/")


@dataclass
class Property:
    """A GA4 property ("properties/123")."""

    name: str
    display_name: str = ""
    property_type: str | None = None
    parent: str | None = None
    time_zone: str | None = None
    currency_code: str | None = None
    industry_category: str | None = None
    service_level: str | None = None
    create_time: datetime | None = None
    update_time: datetime | None = None
    delete_time: datetime | None = None

    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @property
    def property_id(self) -> str:
        return self.name.removeprefix("properties/")


@dataclass
class ReportRow:
    """One report row. Metric values are numbers (None if the API sent something else)."""

    dimensions: dict[str, str]
    metrics: dict[str, int | float | None]


@dataclass
class Report:
    """A runReport / runRealtimeReport response.

    ``raw`` is the response without ``rows`` and ``totals`` (headers with their
    types, ``metadata``, ``propertyQuota``...).
    """

    dimensions: list[str]
    metrics: list[str]
    rows: list[ReportRow]
    row_count: int
    totals: list[ReportRow] = field(default_factory=list)

    raw: dict[str, Any] = field(default_factory=dict, repr=False)
