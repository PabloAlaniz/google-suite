"""Google Suite Analytics - read-only GA4 Admin and Data API client."""

__version__ = "0.1.0"

from gsuite_analytics.client import Analytics, build_filter, property_name
from gsuite_analytics.models import AccountSummary, Property, PropertySummary, Report, ReportRow

__all__ = [
    "AccountSummary",
    "Analytics",
    "Property",
    "PropertySummary",
    "Report",
    "ReportRow",
    "build_filter",
    "property_name",
]
