"""Tests for SecretManagerTokenStore error handling."""

import json
from unittest.mock import MagicMock, patch

import pytest

exceptions = pytest.importorskip("google.api_core.exceptions")
pytest.importorskip("google.cloud.secretmanager")

from gsuite_core.storage.secretmanager import SecretManagerTokenStore  # noqa: E402


@pytest.fixture
def store():
    with patch("gsuite_core.storage.secretmanager.secretmanager.SecretManagerServiceClient"):
        yield SecretManagerTokenStore(project_id="proj")


def payload(data):
    response = MagicMock()
    response.payload.data = json.dumps(data).encode("utf-8")
    return response


def test_get_token_by_user(store):
    store.client.access_secret_version.return_value = payload({"alice": {"token": "t"}})
    assert store.get_token("alice") == {"token": "t"}
    assert store.get_token("bob") is None


def test_get_token_missing_secret_is_none(store):
    store.client.access_secret_version.side_effect = exceptions.NotFound("no secret")
    assert store.get_token() is None
    assert store.exists() is False


def test_get_token_permission_denied_propagates(store):
    """A misconfigured service account must not look like "not logged in"."""
    store.client.access_secret_version.side_effect = exceptions.PermissionDenied("denied")
    with pytest.raises(exceptions.PermissionDenied):
        store.get_token()


def test_get_token_corrupt_payload_propagates(store):
    response = MagicMock()
    response.payload.data = b"not json"
    store.client.access_secret_version.return_value = response
    with pytest.raises(json.JSONDecodeError):
        store.get_token()
