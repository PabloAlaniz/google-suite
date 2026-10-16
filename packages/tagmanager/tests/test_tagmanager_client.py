"""TagManager client on a mocked discovery service."""

from unittest.mock import MagicMock

import pytest

from gsuite_tagmanager import TagManager

WS = "accounts/1/containers/2/workspaces/3"


@pytest.fixture
def gtm():
    client = TagManager(MagicMock(name="auth"))
    client._service = MagicMock(name="service")
    return client


def test_list_accounts_follows_page_tokens(gtm):
    method = gtm.service.accounts().list
    method.return_value.execute.side_effect = [
        {"account": [{"path": "accounts/1"}], "nextPageToken": "t"},
        {"account": [{"path": "accounts/2"}]},
    ]
    assert [a["path"] for a in gtm.list_accounts()] == ["accounts/1", "accounts/2"]
    assert method.call_args.kwargs == {"pageToken": "t"}


def test_list_containers_and_workspaces(gtm):
    containers = gtm.service.accounts().containers()
    containers.list.return_value.execute.return_value = {"container": [{"publicId": "GTM-X"}]}
    assert gtm.list_containers("accounts/1")[0]["publicId"] == "GTM-X"
    assert containers.list.call_args.kwargs == {"parent": "accounts/1"}

    containers.workspaces().list.return_value.execute.return_value = {
        "workspace": [{"name": "Default"}]
    }
    assert gtm.list_workspaces("accounts/1/containers/2") == [{"name": "Default"}]


@pytest.mark.parametrize(
    ("method", "resource", "key"),
    [
        ("list_tags", "tags", "tag"),
        ("list_triggers", "triggers", "trigger"),
        ("list_variables", "variables", "variable"),
    ],
)
def test_workspace_lists(gtm, method, resource, key):
    res = getattr(gtm.service.accounts().containers().workspaces(), resource)()
    res.list.return_value.execute.return_value = {key: [{"name": "x"}]}
    assert getattr(gtm, method)(WS) == [{"name": "x"}]
    assert res.list.call_args.kwargs == {"parent": WS}


def test_empty_list(gtm):
    tags = gtm.service.accounts().containers().workspaces().tags()
    tags.list.return_value.execute.return_value = {}
    assert gtm.list_tags(WS) == []


def test_versions(gtm):
    containers = gtm.service.accounts().containers()
    containers.version_headers().list.return_value.execute.return_value = {
        "containerVersionHeader": [{"containerVersionId": "7"}]
    }
    assert gtm.list_versions("accounts/1/containers/2")[0]["containerVersionId"] == "7"
    containers.versions().live.return_value.execute.return_value = {"containerVersionId": "7"}
    assert gtm.get_live_version("accounts/1/containers/2")["containerVersionId"] == "7"
