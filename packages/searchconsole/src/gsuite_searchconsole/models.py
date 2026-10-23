"""Search Console entities: sites, search analytics rows, URL inspections and sitemaps."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class Site:
    """A Search Console property ("sc-domain:example.com" or a URL prefix)."""

    site_url: str
    permission_level: str = ""

    raw: dict[str, Any] = field(default_factory=dict, repr=False)


@dataclass
class SearchAnalyticsRow:
    """One search analytics row; ``keys`` maps each requested dimension to its value."""

    keys: dict[str, str]
    clicks: int = 0
    impressions: int = 0
    ctr: float = 0.0
    position: float = 0.0

    raw: dict[str, Any] = field(default_factory=dict, repr=False)


@dataclass
class UrlInspection:
    """The index status of one URL. Mobile usability, AMP and rich results stay in ``raw``
    (the whole ``inspectionResult``)."""

    url: str
    verdict: str = "VERDICT_UNSPECIFIED"
    coverage_state: str | None = None
    indexing_state: str | None = None
    page_fetch_state: str | None = None
    robots_txt_state: str | None = None
    last_crawl_time: datetime | None = None
    crawled_as: str | None = None
    google_canonical: str | None = None
    user_canonical: str | None = None
    inspection_result_link: str | None = None

    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @property
    def is_indexed(self) -> bool:
        return self.verdict == "PASS"


@dataclass
class Sitemap:
    """A sitemap submitted for a property."""

    path: str
    type: str | None = None
    last_submitted: datetime | None = None
    last_downloaded: datetime | None = None
    is_pending: bool = False
    is_sitemaps_index: bool = False
    warnings: int = 0
    errors: int = 0

    raw: dict[str, Any] = field(default_factory=dict, repr=False)
