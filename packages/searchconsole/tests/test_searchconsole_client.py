"""SearchConsole client on a mocked discovery service."""

from datetime import date
from unittest.mock import MagicMock

import pytest

from gsuite_core.exceptions import ValidationError
from gsuite_searchconsole import SearchConsole


@pytest.fixture
def sc():
    client = SearchConsole(MagicMock(name="auth"))
    client._service = MagicMock(name="service")
    return client


def test_list_sites(sc):
    sc.service.sites().list().execute.return_value = {
        "siteEntry": [{"siteUrl": "sc-domain:example.com", "permissionLevel": "siteOwner"}]
    }
    assert sc.list_sites()[0]["siteUrl"] == "sc-domain:example.com"


def test_list_sites_empty(sc):
    sc.service.sites().list().execute.return_value = {}
    assert sc.list_sites() == []


def test_query_builds_body_and_maps_rows(sc):
    method = sc.service.searchanalytics().query
    method.return_value.execute.return_value = {
        "rows": [
            {
                "keys": ["shoes", "ARG"],
                "clicks": 3,
                "impressions": 40,
                "ctr": 0.075,
                "position": 4.2,
            }
        ]
    }
    rows = sc.query(
        "sc-domain:example.com",
        date(2026, 9, 1),
        "2026-09-30",
        dimensions=["query", "country"],
        filters=[{"dimension": "query", "operator": "contains", "expression": "sho"}],
        row_limit=50,
    )
    assert rows == [
        {
            "query": "shoes",
            "country": "ARG",
            "clicks": 3,
            "impressions": 40,
            "ctr": 0.075,
            "position": 4.2,
        }
    ]
    body = method.call_args.kwargs["body"]
    assert method.call_args.kwargs["siteUrl"] == "sc-domain:example.com"
    assert body["startDate"] == "2026-09-01"
    assert body["endDate"] == "2026-09-30"
    assert body["rowLimit"] == 50
    assert body["type"] == "web"
    assert body["dimensionFilterGroups"] == [
        {
            "groupType": "and",
            "filters": [{"dimension": "query", "operator": "contains", "expression": "sho"}],
        }
    ]


@pytest.mark.parametrize(
    "kwargs",
    [
        {"dimensions": ["browser"]},
        {"row_limit": 0},
        {"row_limit": 25001},
        {"search_type": "shopping"},
        {"filters": [{"dimension": "query", "operator": "like", "expression": "x"}]},
        {"filters": [{"dimension": "date", "expression": "x"}]},
        {"filters": [{"dimension": "page", "expression": ""}]},
    ],
)
def test_query_validates(sc, kwargs):
    with pytest.raises(ValidationError):
        sc.query("sc-domain:example.com", "2026-09-01", "2026-09-30", **kwargs)


def test_query_rejects_bad_dates(sc):
    with pytest.raises(ValidationError):
        sc.query("s", "2026-09-30", "2026-09-01")
    with pytest.raises(ValidationError):
        sc.query("s", "last week", "2026-09-01")


def test_inspect_url(sc):
    method = sc.service.urlInspection().index().inspect
    method.return_value.execute.return_value = {
        "inspectionResult": {"indexStatusResult": {"verdict": "PASS"}}
    }
    result = sc.inspect_url("https://example.com/", "https://example.com/a", language_code="es")
    assert result["indexStatusResult"]["verdict"] == "PASS"
    assert method.call_args.kwargs["body"] == {
        "inspectionUrl": "https://example.com/a",
        "siteUrl": "https://example.com/",
        "languageCode": "es",
    }


def test_list_sitemaps(sc):
    sc.service.sitemaps().list.return_value.execute.return_value = {
        "sitemap": [{"path": "https://example.com/sitemap.xml"}]
    }
    assert sc.list_sitemaps("https://example.com/")[0]["path"].endswith("sitemap.xml")
    assert sc.service.sitemaps().list.call_args.kwargs == {"siteUrl": "https://example.com/"}


def _pages(sc, sizes):
    """query() returns pages of the given sizes, in order; returns the mocked method."""
    method = sc.service.searchanalytics().query
    method.return_value.execute.side_effect = [
        {"rows": [{"keys": [str(i)], "clicks": i} for i in range(n)]} for n in sizes
    ]
    return method


def test_query_all_pages_past_the_cap(sc):
    method = _pages(sc, [25000, 25000, 3])

    rows = sc.query_all("s", "2026-01-01", "2026-01-31", dimensions=["query"])

    assert len(rows) == 50003
    bodies = [c.kwargs["body"] for c in method.call_args_list]
    assert [(b["startRow"], b["rowLimit"]) for b in bodies] == [
        (0, 25000),
        (25000, 25000),
        (50000, 25000),
    ]


def test_query_all_max_rows_shrinks_last_page(sc):
    method = _pages(sc, [25000, 5000])

    rows = sc.query_all("s", "2026-01-01", "2026-01-31", max_rows=30000)

    assert len(rows) == 30000
    assert [c.kwargs["body"]["rowLimit"] for c in method.call_args_list] == [25000, 5000]


def test_query_all_short_first_page(sc):
    method = _pages(sc, [0])
    assert sc.query_all("s", "2026-01-01", "2026-01-31") == []
    assert method.call_count == 1


def test_query_all_rejects_bad_max_rows(sc):
    with pytest.raises(ValidationError):
        sc.query_all("s", "2026-01-01", "2026-01-31", max_rows=0)
