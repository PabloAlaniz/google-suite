"""REST API rate limit (GSUITE_API_RATE_LIMIT): 429 with Retry-After past the budget."""

import pytest

from gsuite_core import Settings


@pytest.fixture
def limited(make_client, services, settings):
    """Client for an app allowing one request at once, refilling at 0.5/s."""
    services["sheets"].list_spreadsheets.return_value = []
    update = {"api_rate_limit": 0.5, "api_rate_limit_burst": 1}
    return make_client(settings.model_copy(update=update))


def test_off_by_default(client, services):
    services["sheets"].list_spreadsheets.return_value = []

    statuses = {client.get("/sheets/list").status_code for _ in range(20)}

    assert statuses == {200}


def test_over_the_budget_is_429_with_retry_after(limited, settings):
    limited.headers["X-API-Key"] = settings.api_key

    assert limited.get("/sheets/list").status_code == 200
    response = limited.get("/sheets/list")

    assert response.status_code == 429
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["detail"] == "API rate limit exceeded"
    # one token at 0.5 tokens/s: about 2 seconds, rounded up
    assert 1 <= int(response.headers["Retry-After"]) <= 2


def test_requests_without_a_valid_key_spend_nothing(limited, settings):
    for _ in range(3):
        assert limited.get("/sheets/list", headers={"X-API-Key": "wrong"}).status_code == 401

    assert limited.get("/sheets/list", headers={"X-API-Key": settings.api_key}).status_code == 200


def test_health_is_not_limited(limited):
    statuses = {limited.get("/health").status_code for _ in range(5)}

    assert statuses == {200}


def test_rate_limit_must_be_positive():
    with pytest.raises(ValueError, match="greater than 0"):
        Settings(api_rate_limit=0, _env_file=None)
