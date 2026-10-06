"""Label CRUD, batch modify, filters and threads."""

from unittest.mock import MagicMock, Mock, patch

import pytest

from gsuite_core.exceptions import ValidationError
from gsuite_gmail.client import BATCH_MODIFY_LIMIT, Gmail

LABELS = {"labels": [{"id": "INBOX", "name": "INBOX"}, {"id": "Label_7", "name": "Work"}]}


@pytest.fixture
def service(batching):
    with patch("gsuite_gmail.client.build") as build:
        svc = batching(MagicMock())
        svc.users().labels().list().execute.return_value = LABELS
        build.return_value = svc
        yield svc


@pytest.fixture
def gmail(service):
    return Gmail(Mock())


class TestLabels:
    def test_create(self, gmail, service):
        service.users().labels().create().execute.return_value = {
            "id": "Label_9",
            "name": "Clients/Acme",
        }

        label = gmail.create_label("Clients/Acme", show_in_label_list=False)

        assert label.id == "Label_9"
        assert (
            service.users().labels().create.call_args.kwargs["body"]["labelListVisibility"]
            == "labelHide"
        )

    def test_rename_by_name(self, gmail, service):
        service.users().labels().patch().execute.return_value = {"id": "Label_7", "name": "Job"}

        gmail.rename_label("Work", "Job")

        assert service.users().labels().patch.call_args.kwargs["id"] == "Label_7"

    def test_rename_unknown(self, gmail):
        with pytest.raises(ValidationError):
            gmail.rename_label("Nope", "X")

    def test_delete(self, gmail, service):
        assert gmail.delete_label("Work") is True
        assert service.users().labels().delete.call_args.kwargs["id"] == "Label_7"
        assert gmail.delete_label("Nope") is False

    def test_cache_invalidated_after_create(self, gmail, service):
        gmail._get_label_id("Work")
        service.users().labels().create().execute.return_value = {"id": "Label_9", "name": "New"}
        gmail.create_label("New")
        assert gmail._labels_cache is None


class TestBatchModify:
    def _bodies(self, service):
        return [
            c.kwargs["body"]
            for c in service.users().messages().batchModify.call_args_list
            if c.kwargs
        ]

    def test_resolves_names_and_chunks(self, gmail, service):
        ids = [str(i) for i in range(BATCH_MODIFY_LIMIT + 5)]

        assert gmail.batch_modify(ids, add_labels=["Work"], remove_labels=["UNREAD"]) == len(ids)

        bodies = self._bodies(service)
        assert [len(b["ids"]) for b in bodies] == [BATCH_MODIFY_LIMIT, 5]
        assert bodies[0]["addLabelIds"] == ["Label_7"]
        # System labels are fixed IDs, accepted without a lookup
        assert bodies[0]["removeLabelIds"] == ["UNREAD"]

    def test_unknown_label(self, gmail):
        with pytest.raises(ValidationError, match="Nope"):
            gmail.batch_modify(["1"], add_labels=["Nope"])

    def test_nothing_to_do(self, gmail, service):
        assert gmail.batch_modify(["1"]) == 0
        assert self._bodies(service) == []


class TestFilters:
    def test_create_resolves_label_names(self, gmail, service):
        service.users().settings().filters().create().execute.return_value = {"id": "f1"}

        gmail.create_filter(
            {"from": "alerts@x.com"}, {"addLabelIds": ["Work"], "removeLabelIds": ["INBOX"]}
        )

        body = service.users().settings().filters().create.call_args.kwargs["body"]
        assert body["action"] == {"addLabelIds": ["Label_7"], "removeLabelIds": ["INBOX"]}

    def test_list_and_delete(self, gmail, service, http_error):
        service.users().settings().filters().list().execute.return_value = {
            "filter": [{"id": "f1"}]
        }
        assert gmail.list_filters() == [{"id": "f1"}]
        assert gmail.delete_filter("f1") is True
        service.users().settings().filters().delete().execute.side_effect = http_error(404)
        assert gmail.delete_filter("f1") is False


def test_threads(gmail, service):
    service.users().threads().list().execute.return_value = {
        "threads": [{"id": "t1"}, {"id": "t2"}]
    }
    service.users().threads().get().execute.side_effect = lambda: {
        "id": "t",
        "snippet": "s",
        "messages": [{"id": "m", "payload": {"headers": [{"name": "Subject", "value": "Hi"}]}}],
    }

    threads = gmail.get_threads(query="from:ana")

    assert [t.subject for t in threads] == ["Hi", "Hi"]
    assert service.users().threads().list.call_args.kwargs["q"] == "from:ana"


def test_deleted_message_is_skipped(gmail, service, http_error):
    service.users().messages().list().execute.return_value = {
        "messages": [{"id": "a"}, {"id": "b"}]
    }
    responses = iter([{"id": "a", "payload": {"headers": []}}, http_error(404)])

    def get_execute():
        item = next(responses)
        if isinstance(item, Exception):
            raise item
        return item

    service.users().messages().get().execute.side_effect = get_execute

    assert [m.id for m in gmail.get_messages()] == ["a"]
