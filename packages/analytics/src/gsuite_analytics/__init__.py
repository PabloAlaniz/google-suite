"""Google Suite Analytics - read-only GA4 Admin and Data API client."""

__version__ = "0.1.0"

from gsuite_analytics.client import Analytics, build_filter, property_name

__all__ = ["Analytics", "build_filter", "property_name"]
