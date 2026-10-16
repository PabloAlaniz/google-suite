"""Search Console, Analytics and Tag Manager REST routes (read-only) with mocked clients."""

import pytest


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
        sc.list_sites.return_value = [{"siteUrl": "sc-domain:a.com"}]
        assert client.get("/searchconsole/sites").json()["count"] == 1
        sc.list_sitemaps.return_value = []
        assert client.get("/searchconsole/sitemaps", params={"site_url": "s"}).json()["count"] == 0
        assert client.get("/searchconsole/sitemaps").status_code == 422

    def test_query(self, client, sc):
        sc.query.return_value = [{"query": "x", "clicks": 1}]
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
        sc.inspect_url.return_value = {"indexStatusResult": {"verdict": "PASS"}}
        body = client.post(
            "/searchconsole/urlInspection", json={"site_url": "s", "url": "u"}
        ).json()
        assert body["indexStatusResult"]["verdict"] == "PASS"


class TestAnalytics:
    def test_admin(self, client, ga):
        ga.account_summaries.return_value = [{"account": "accounts/1"}]
        assert client.get("/analytics/accountSummaries").json()["count"] == 1
        ga.list_properties.return_value = []
        assert client.get("/analytics/properties", params={"account_id": "1"}).json()["count"] == 0

    def test_run_report(self, client, ga):
        ga.run_report.return_value = {
            "rows": [{"date": "20260901", "sessions": "3"}],
            "row_count": 1,
        }
        response = client.post(
            "/analytics/properties/123:runReport",
            json={"metrics": ["sessions"], "dimensions": ["date"]},
        )
        assert response.status_code == 200
        assert response.json()["row_count"] == 1
        assert ga.run_report.call_args.kwargs["date_ranges"] == [("28daysAgo", "today")]
        assert (
            client.post("/analytics/properties/123:runReport", json={"metrics": []}).status_code
            == 422
        )

    def test_realtime(self, client, ga):
        ga.run_realtime_report.return_value = {"rows": []}
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
