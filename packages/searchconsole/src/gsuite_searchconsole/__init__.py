"""Google Suite Search Console - read-only Search Console client."""

__version__ = "0.1.0"

from gsuite_searchconsole.client import SearchConsole
from gsuite_searchconsole.models import SearchAnalyticsRow, Site, Sitemap, UrlInspection

__all__ = ["SearchAnalyticsRow", "SearchConsole", "Site", "Sitemap", "UrlInspection"]
