"""GoogleService: lazy, cached, injectable discovery services."""

from unittest.mock import Mock, patch

import pytest

from gsuite_core import GoogleService


class Client:
    service = GoogleService("gmail", "v1")
    drive = GoogleService("drive", "v3", attr="_drive_service")

    def __init__(self, auth: object) -> None:
        self.auth = auth


@pytest.fixture
def build():
    with patch("gsuite_core.service.build") as build:
        build.side_effect = lambda api, version, **_: Mock(name=f"{api}.{version}")
        yield build


def test_builds_on_first_access_with_a_timeout_transport(build):
    auth = Mock()
    client = Client(auth)
    build.assert_not_called()

    service = client.service

    assert build.call_args.args == ("gmail", "v1")
    assert build.call_args.kwargs["cache_discovery"] is False
    assert build.call_args.kwargs["http"].credentials is auth.credentials
    assert service is client._service


def test_caches_per_instance(build):
    first, second = Client(Mock()), Client(Mock())

    assert first.service is first.service
    assert first.service is not second.service
    assert build.call_count == 2


def test_assignment_injects_a_service(build):
    client = Client(Mock())
    fake = Mock()

    client.service = fake

    assert client.service is fake
    build.assert_not_called()


def test_custom_cache_attribute(build):
    client = Client(Mock())

    assert client.drive is client._drive_service
    assert build.call_args.args == ("drive", "v3")


def test_class_access_returns_the_descriptor():
    assert isinstance(Client.service, GoogleService)
    assert Client.service.api == "gmail"


def test_unbound_descriptor_says_where_it_belongs():
    loose = GoogleService("gmail", "v1")

    with pytest.raises(TypeError, match="class body"):
        loose.__get__(Client(Mock()))
