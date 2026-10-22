"""Search Console, Analytics and Tag Manager CLI commands with mocked clients."""

import json
from unittest.mock import MagicMock, Mock, patch

import pytest
from typer.testing import CliRunner

from gsuite_cli.main import app

runner = CliRunner()


@pytest.fixture
def sc():
    client = MagicMock()
    with patch("gsuite_cli.searchconsole.get_searchconsole", return_value=client):
        yield client


@pytest.fixture
def ga():
    client = MagicMock()
    with patch("gsuite_cli.analytics.get_analytics", return_value=client):
        yield client


@pytest.fixture
def gtm():
    client = MagicMock()
    with patch("gsuite_cli.tagmanager.get_tagmanager", return_value=client):
        yield client


ROW = {"query": "shoes", "clicks": 12, "impressions": 340, "ctr": 0.035, "position": 4.27}

REPORT = {
    "dimensions": ["country"],
    "metrics": ["activeUsers"],
    "row_count": 1,
    "rows": [{"country": "Argentina", "activeUsers": "42"}],
}


class TestSearchConsole:
    def test_sites(self, sc):
        sc.list_sites.return_value = [
            {"siteUrl": "sc-domain:example.com", "permissionLevel": "siteOwner"}
        ]
        result = runner.invoke(app, ["searchconsole", "sites"])
        assert result.exit_code == 0, result.output
        assert "sc-domain:example.com" in result.output

    def test_query(self, sc):
        sc.query.return_value = [ROW]

        result = runner.invoke(
            app,
            [
                "searchconsole", "query", "sc-domain:example.com",
                "-s", "2026-10-01", "-e", "2026-10-21",
                "-d", "query", "-f", "query:contains:sho:es", "-l", "10",
            ],
        )  # fmt: skip

        assert result.exit_code == 0, result.output
        assert "shoes" in result.output
        assert "3.5%" in result.output
        assert "4.3" in result.output
        sc.query.assert_called_once_with(
            "sc-domain:example.com",
            "2026-10-01",
            "2026-10-21",
            dimensions=["query"],
            filters=[{"dimension": "query", "operator": "contains", "expression": "sho:es"}],
            row_limit=10,
            start_row=0,
            search_type="web",
        )

    def test_query_json(self, sc):
        sc.query.return_value = [ROW]
        result = runner.invoke(
            app, ["searchconsole", "query", "s", "-s", "a", "-e", "b", "-o", "json"]
        )
        assert json.loads(result.output) == [ROW]

    def test_query_all(self, sc):
        sc.query_all.return_value = [ROW]

        result = runner.invoke(
            app, ["searchconsole", "query", "s", "-s", "a", "-e", "b", "--all", "-o", "json"]
        )

        assert json.loads(result.output) == [ROW]
        sc.query.assert_not_called()
        sc.query_all.assert_called_once_with(
            "s", "a", "b", dimensions=[], filters=[], search_type="web"
        )

    def test_query_empty(self, sc):
        sc.query.return_value = []
        result = runner.invoke(app, ["searchconsole", "query", "s", "-s", "a", "-e", "b"])
        assert "No rows" in result.output

    def test_bad_filter(self, sc):
        result = runner.invoke(
            app, ["searchconsole", "query", "s", "-s", "a", "-e", "b", "-f", "query:contains"]
        )
        assert result.exit_code != 0
        sc.query.assert_not_called()

    def test_inspect(self, sc):
        sc.inspect_url.return_value = {
            "indexStatusResult": {"verdict": "PASS", "coverageState": "Submitted and indexed"}
        }
        result = runner.invoke(app, ["searchconsole", "inspect", "s", "https://example.com/a"])
        assert "Submitted and indexed" in result.output
        sc.inspect_url.assert_called_once_with("s", "https://example.com/a")

    def test_sitemaps(self, sc):
        sc.list_sitemaps.return_value = [{"path": "https://example.com/sitemap.xml", "errors": 2}]
        result = runner.invoke(app, ["searchconsole", "sitemaps", "s"])
        assert "sitemap.xml" in result.output


class TestAnalytics:
    def test_accounts(self, ga):
        ga.account_summaries.return_value = [
            {
                "displayName": "Acme",
                "propertySummaries": [{"property": "properties/123", "displayName": "Web"}],
            },
            {"displayName": "Empty"},
        ]
        result = runner.invoke(app, ["analytics", "accounts"])
        assert result.exit_code == 0, result.output
        assert "123" in result.output
        assert "Empty" in result.output

    def test_properties(self, ga):
        ga.list_properties.return_value = [{"name": "properties/123", "displayName": "Web"}]
        result = runner.invoke(app, ["analytics", "properties", "accounts/9", "--deleted"])
        assert "Web" in result.output
        ga.list_properties.assert_called_once_with("accounts/9", show_deleted=True)

    def test_report(self, ga):
        ga.run_report.return_value = REPORT

        result = runner.invoke(
            app,
            [
                "analytics", "report", "123", "-m", "activeUsers", "-d", "country",
                "-s", "7daysAgo", "--order-by", "activeUsers", "--asc",
            ],
        )  # fmt: skip

        assert result.exit_code == 0, result.output
        assert "Argentina" in result.output
        ga.run_report.assert_called_once_with(
            "123",
            ["country"],
            ["activeUsers"],
            date_ranges=[("7daysAgo", "today")],
            limit=100,
            order_by="activeUsers",
            descending=False,
        )

    def test_report_json(self, ga):
        ga.run_report.return_value = REPORT
        result = runner.invoke(app, ["analytics", "report", "123", "-o", "json"])
        assert json.loads(result.output) == REPORT
        assert ga.run_report.call_args.args[2] == ["activeUsers"]

    def test_realtime_empty(self, ga):
        ga.run_realtime_report.return_value = {**REPORT, "row_count": 0, "rows": []}
        result = runner.invoke(app, ["analytics", "realtime", "123"])
        assert "No rows" in result.output
        ga.run_realtime_report.assert_called_once_with("123", [], ["activeUsers"], limit=100)


class TestTagManager:
    def test_accounts(self, gtm):
        gtm.list_accounts.return_value = [{"path": "accounts/1", "name": "Acme"}]
        result = runner.invoke(app, ["tagmanager", "accounts"])
        assert "accounts/1" in result.output

    def test_containers_json(self, gtm):
        containers = [{"path": "accounts/1/containers/2", "publicId": "GTM-ABC"}]
        gtm.list_containers.return_value = containers
        result = runner.invoke(app, ["tagmanager", "containers", "accounts/1", "-o", "json"])
        assert json.loads(result.output) == containers
        gtm.list_containers.assert_called_once_with("accounts/1")

    @pytest.mark.parametrize("command", ["workspaces", "tags", "triggers", "variables"])
    def test_workspace_lists(self, gtm, command):
        getattr(gtm, f"list_{command}").return_value = [{"name": "GA4 config", "type": "gaawc"}]
        result = runner.invoke(app, ["tagmanager", command, "accounts/1/containers/2/workspaces/3"])
        assert "GA4 config" in result.output

    def test_versions_empty(self, gtm):
        gtm.list_versions.return_value = []
        result = runner.invoke(app, ["tagmanager", "versions", "accounts/1/containers/2"])
        assert "No versions" in result.output


@pytest.mark.parametrize(
    ("module", "command", "scope"),
    [
        ("searchconsole", ["searchconsole", "sites"], "searchconsole"),
        ("analytics", ["analytics", "accounts"], "analytics"),
        ("tagmanager", ["tagmanager", "accounts"], "tagmanager"),
    ],
)
def test_requires_auth(module, command, scope):
    auth = Mock()
    auth.is_authenticated.return_value = False
    auth.needs_refresh.return_value = False
    with patch(f"gsuite_cli.{module}.GoogleAuth", return_value=auth):
        result = runner.invoke(app, command)

    assert result.exit_code == 1
    assert f"--scopes default,{scope}" in result.output
