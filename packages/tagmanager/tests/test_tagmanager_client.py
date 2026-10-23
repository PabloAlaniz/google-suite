"""TagManager client on a mocked discovery service."""

from unittest.mock import MagicMock

import httplib2
import pytest
from googleapiclient.errors import HttpError

from gsuite_core.exceptions import NotFoundError
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
    assert [a.path for a in gtm.list_accounts()] == ["accounts/1", "accounts/2"]
    assert method.call_args.kwargs == {"pageToken": "t"}


def test_list_containers_and_workspaces(gtm):
    containers = gtm.service.accounts().containers()
    containers.list.return_value.execute.return_value = {
        "container": [
            {
                "path": "accounts/1/containers/2",
                "accountId": "1",
                "containerId": "2",
                "name": "Site",
                "publicId": "GTM-X",
                "usageContext": ["web"],
            }
        ]
    }
    (container,) = gtm.list_containers("accounts/1")
    assert (container.container_id, container.public_id) == ("2", "GTM-X")
    assert container.usage_context == ["web"]
    assert container.domain_names == []
    assert containers.list.call_args.kwargs == {"parent": "accounts/1"}

    containers.workspaces().list.return_value.execute.return_value = {
        "workspace": [{"name": "Default", "workspaceId": "3"}]
    }
    (workspace,) = gtm.list_workspaces("accounts/1/containers/2")
    assert (workspace.name, workspace.workspace_id) == ("Default", "3")


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
    res.list.return_value.execute.return_value = {key: [{"name": "x", "type": "html"}]}
    (item,) = getattr(gtm, method)(WS)
    assert (item.name, item.type, item.raw) == ("x", "html", {"name": "x", "type": "html"})
    assert res.list.call_args.kwargs == {"parent": WS}


def test_empty_list(gtm):
    tags = gtm.service.accounts().containers().workspaces().tags()
    tags.list.return_value.execute.return_value = {}
    assert gtm.list_tags(WS) == []


def test_versions(gtm):
    containers = gtm.service.accounts().containers()
    containers.version_headers().list.return_value.execute.return_value = {
        "containerVersionHeader": [{"containerVersionId": "7", "numTags": "4", "deleted": True}]
    }
    (header,) = gtm.list_versions("accounts/1/containers/2")
    assert (header.container_version_id, header.num_tags, header.num_triggers) == ("7", 4, 0)
    assert header.deleted
    containers.versions().live.return_value.execute.return_value = {
        "containerVersionId": "7",
        "tag": [
            {
                "tagId": "1",
                "name": "GA4",
                "type": "gaawc",
                "firingTriggerId": ["2147479553"],
                "parameter": [{"type": "template", "key": "measurementId", "value": "G-X"}],
            }
        ],
        "trigger": [{"triggerId": "5", "type": "pageview"}],
        "variable": [{"variableId": "9", "type": "c"}],
    }
    live = gtm.get_live_version("accounts/1/containers/2")
    assert live.container_version_id == "7"
    (tag,) = live.tags
    assert (tag.tag_id, tag.firing_trigger_ids, tag.paused) == ("1", ["2147479553"], False)
    assert tag.parameters == [{"type": "template", "key": "measurementId", "value": "G-X"}]
    assert [t.trigger_id for t in live.triggers] == ["5"]
    assert [v.variable_id for v in live.variables] == ["9"]


def test_not_found_names_the_parent(gtm):
    tags = gtm.service.accounts().containers().workspaces().tags()
    not_found = HttpError(httplib2.Response({"status": "404"}), b"")
    tags.list.return_value.execute.side_effect = not_found

    with pytest.raises(NotFoundError) as exc:
        gtm.list_tags(WS)

    assert (exc.value.resource_type, exc.value.resource_id) == ("tags", WS)
    assert tags.list.call_args.kwargs == {"parent": WS}
