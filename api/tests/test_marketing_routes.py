"""Search Console, Analytics and Tag Manager REST routes (read-only) with mocked clients."""

from datetime import UTC, datetime

import pytest

from gsuite_analytics import AccountSummary, Property, PropertySummary, Report, ReportRow
from gsuite_searchconsole import SearchAnalyticsRow, Site, Sitemap, UrlInspection


@pytest.fixture
def sc(services):
    return services["searchconsole"]


@pytest.fixture
def ga(services):
    return services["analytics"]


@pytest.fixture
def gtm(services):
    return services["tagmanager"]


class TestSearchConsole:
    def test_sites_and_sitemaps(self, client, sc):
        sc.list_sites.return_value = [Site("sc-domain:a.com", "siteOwner")]
        body = client.get("/searchconsole/sites").json()
        assert body == {
            "sites": [{"site_url": "sc-domain:a.com", "permission_level": "siteOwner"}],
            "count": 1,
        }
        sc.list_sitemaps.return_value = [
            Sitemap(
                "https://a.com/sitemap.xml",
                last_downloaded=datetime(2026, 9, 1, tzinfo=UTC),
                errors=2,
            )
        ]
        sitemap = client.get("/searchconsole/sitemaps", params={"site_url": "s"}).json()[
            "sitemaps"
        ][0]
        assert sitemap["path"] == "https://a.com/sitemap.xml"
        assert sitemap["last_downloaded"].startswith("2026-09-01T00:00:00")
        assert sitemap["errors"] == 2
        assert client.get("/searchconsole/sitemaps").status_code == 422

    def test_query(self, client, sc):
        sc.query.return_value = [SearchAnalyticsRow({"query": "x", "page": "/"}, clicks=1)]
        response = client.post(
            "/searchconsole/searchanalytics/query",
            json={
                "site_url": "sc-domain:a.com",
                "start_date": "2026-09-01",
                "end_date": "2026-09-30",
                "dimensions": ["query", "page"],
                "filters": [{"dimension": "country", "expression": "arg"}],
            },
        )
        assert response.status_code == 200
        assert response.json()["count"] == 1
        assert response.json()["rows"][0] == {
            "keys": {"query": "x", "page": "/"},
            "clicks": 1,
            "impressions": 0,
            "ctr": 0.0,
            "position": 0.0,
        }
        kwargs = sc.query.call_args.kwargs
        assert kwargs["filters"] == [
            {"dimension": "country", "operator": "equals", "expression": "arg"}
        ]

    def test_query_validation(self, client):
        bad = {"site_url": "s", "start_date": "2026-09-01", "end_date": "x"}
        assert client.post("/searchconsole/searchanalytics/query", json=bad).status_code == 422
        bad = {
            "site_url": "s",
            "start_date": "2026-09-01",
            "end_date": "2026-09-02",
            "row_limit": 0,
        }
        assert client.post("/searchconsole/searchanalytics/query", json=bad).status_code == 422

    def test_inspect(self, client, sc):
        raw = {"indexStatusResult": {"verdict": "PASS"}, "mobileUsabilityResult": {}}
        sc.inspect_url.return_value = UrlInspection("u", verdict="PASS", raw=raw)
        body = client.post(
            "/searchconsole/urlInspection", json={"site_url": "s", "url": "u"}
        ).json()
        assert body["verdict"] == "PASS"
        assert body["result"] == raw


class TestAnalytics:
    def test_admin(self, client, ga):
        ga.account_summaries.return_value = [
            AccountSummary(
                "accountSummaries/1",
                "accounts/1",
                "Acme",
                [PropertySummary("properties/9", "Web")],
            )
        ]
        summary = client.get("/analytics/accountSummaries").json()["account_summaries"][0]
        assert summary["account_id"] == "1"
        assert summary["properties"][0]["property_id"] == "9"
        ga.list_properties.return_value = [
            Property("properties/9", "Web", create_time=datetime(2024, 5, 1, tzinfo=UTC))
        ]
        prop = client.get("/analytics/properties", params={"account_id": "1"}).json()["properties"][
            0
        ]
        assert prop["property_id"] == "9"
        assert prop["create_time"].startswith("2024-05-01T00:00:00")

    def test_run_report(self, client, ga):
        ga.run_report.return_value = Report(
            ["date"],
            ["sessions", "rate"],
            [ReportRow({"date": "20260901"}, {"sessions": 3, "rate": 0.5})],
            row_count=1,
        )
        response = client.post(
            "/analytics/properties/123:runReport",
            json={"metrics": ["sessions"], "dimensions": ["date"]},
        )
        assert response.status_code == 200
        assert response.json()["row_count"] == 1
        assert response.json()["rows"] == [
            {"dimensions": {"date": "20260901"}, "metrics": {"sessions": 3, "rate": 0.5}}
        ]
        assert ga.run_report.call_args.kwargs["date_ranges"] == [("28daysAgo", "today")]
        assert (
            client.post("/analytics/properties/123:runReport", json={"metrics": []}).status_code
            == 422
        )

    def test_realtime(self, client, ga):
        ga.run_realtime_report.return_value = Report([], ["activeUsers"], [], row_count=0)
        assert client.post("/analytics/properties/1:runRealtimeReport", json={}).status_code == 200
        assert ga.run_realtime_report.call_args.args[2] == ["activeUsers"]


class TestTagManager:
    def test_accounts(self, client, gtm):
        gtm.list_accounts.return_value = [{"path": "accounts/1"}]
        assert client.get("/tagmanager/accounts").json() == {
            "accounts": [{"path": "accounts/1"}],
            "count": 1,
        }

    @pytest.mark.parametrize(
        ("path", "method", "parent"),
        [
            ("containers", "list_containers", "accounts/1"),
            ("workspaces", "list_workspaces", "accounts/1/containers/2"),
            ("versions", "list_versions", "accounts/1/containers/2"),
            ("tags", "list_tags", "accounts/1/containers/2/workspaces/3"),
            ("triggers", "list_triggers", "accounts/1/containers/2/workspaces/3"),
            ("variables", "list_variables", "accounts/1/containers/2/workspaces/3"),
        ],
    )
    def test_lists_validate_parent(self, client, gtm, path, method, parent):
        getattr(gtm, method).return_value = []
        assert client.get(f"/tagmanager/{path}", params={"parent": parent}).status_code == 200
        getattr(gtm, method).assert_called_once_with(parent)
        assert client.get(f"/tagmanager/{path}", params={"parent": "nope"}).status_code == 422

    def test_requires_api_key(self, client, gtm):
        client.headers.pop("X-API-Key", None)
        assert client.get("/tagmanager/accounts").status_code in (401, 403)
