"""Problem-details error mapping and request IDs."""

from unittest.mock import Mock

import pytest
from googleapiclient.errors import HttpError

from gsuite_core.exceptions import (
    APIError,
    NotAuthenticatedError,
    NotFoundError,
    PermissionDeniedError,
    QuotaExceededError,
    RateLimitError,
    TokenRefreshError,
)

PROBLEM = "application/problem+json"


def _http_error(status: int, body: bytes = b"{}") -> HttpError:
    resp = Mock(status=status, reason="error")
    resp.get = lambda key, default=None: default
    return HttpError(resp, body)


@pytest.mark.parametrize(
    ("exc", "status"),
    [
        (NotFoundError("gmail", "label", "x"), 404),
        (PermissionDeniedError("gmail", "list labels"), 403),
        (QuotaExceededError("gmail"), 429),
        (RateLimitError("gmail"), 429),
        (APIError("boom", "gmail", 500), 502),
        (NotAuthenticatedError(), 401),
        (TokenRefreshError(), 401),
    ],
    ids=lambda v: type(v).__name__ if isinstance(v, Exception) else str(v),
)
def test_sdk_errors_map_to_status(client, services, exc, status):
    services["gmail"].get_labels.side_effect = exc

    response = client.get("/gmail/labels")

    assert response.status_code == status
    assert response.headers["content-type"] == PROBLEM
    body = response.json()
    assert body["status"] == status
    assert body["instance"] == "/gmail/labels"
    assert body["request_id"] == response.headers["x-request-id"]


def test_rate_limit_sets_retry_after(client, services):
    services["gmail"].get_labels.side_effect = RateLimitError("gmail", retry_after=30)

    response = client.get("/gmail/labels")

    assert response.status_code == 429
    assert response.headers["retry-after"] == "30"


def test_upstream_error_does_not_leak_message(client, services):
    services["gmail"].get_labels.side_effect = APIError(
        "<HttpError 500 when requesting https://gmail.googleapis.com/secret-id>", "gmail", 500
    )

    response = client.get("/gmail/labels")

    assert response.status_code == 502
    assert "secret-id" not in response.text
    assert response.json()["upstream_status"] == 500


def test_raw_google_http_error_is_mapped(client, services):
    # Sheets doesn't wrap its calls in @api_call yet; the handler maps them.
    services["sheets"].open_by_key.side_effect = _http_error(404)

    response = client.get("/sheets/does-not-exist")

    assert response.status_code == 404
    assert response.json()["service"] == "sheets"


def test_unexpected_error_is_generic_500(make_client, settings, services):
    client = make_client(settings, raise_server_exceptions=False)
    client.headers["X-API-Key"] = "test-api-key"
    services["sheets"].get_values.side_effect = RuntimeError("db password is hunter2")

    response = client.get("/sheets/abc/values/A1:B2")

    assert response.status_code == 500
    assert response.headers["content-type"] == PROBLEM
    assert "hunter2" not in response.text
    assert response.json()["request_id"]


def test_validation_error_is_problem(client):
    response = client.post("/calendar/events", json={"summary": "x", "start": "not-a-date"})

    assert response.status_code == 422
    assert response.headers["content-type"] == PROBLEM
    assert response.json()["errors"][0]["loc"] == ["body", "start"]


def test_not_found_route_is_problem(client):
    response = client.get("/nope")
    assert response.status_code == 404
    assert response.headers["content-type"] == PROBLEM


class TestRequestId:
    def test_generated_when_missing(self, client):
        response = client.get("/health")
        assert len(response.headers["x-request-id"]) == 32

    def test_valid_incoming_id_is_echoed(self, client):
        response = client.get("/health", headers={"X-Request-ID": "lb-abc.123"})
        assert response.headers["x-request-id"] == "lb-abc.123"

    @pytest.mark.parametrize("bad", ["a" * 200, "has space", "<script>"])
    def test_unsafe_incoming_id_is_replaced(self, client, bad):
        response = client.get("/health", headers={"X-Request-ID": bad})
        assert response.headers["x-request-id"] != bad
        assert len(response.headers["x-request-id"]) == 32
