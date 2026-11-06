"""REST API rate limit (GSUITE_API_RATE_LIMIT): 429 with Retry-After past the budget."""

import pytest
from pydantic import SecretStr, ValidationError

from gsuite_api.rate_limit import build_limiter, to_policy
from gsuite_core import Settings

# Nothing listens on port 1, so Redis fails right away
DOWN = SecretStr("redis://127.0.0.1:1/0")


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


def test_responses_report_the_budget(limited, settings):
    limited.headers["X-API-Key"] = settings.api_key

    response = limited.get("/sheets/list")

    assert response.status_code == 200
    assert response.headers["RateLimit-Policy"] == '"gsuite-api";q=1;w=2'
    assert response.headers["RateLimit"].startswith('"gsuite-api";r=0;')


@pytest.mark.parametrize(
    ("rate", "burst", "policy"),
    [
        (5, None, (5, 1000, 5)),
        (5, 20, (5, 1000, 20)),
        (0.5, None, (1, 2000, 1)),
        (0.5, 1, (1, 2000, 1)),
        (2.5, None, (5, 2000, 2)),
        (2.5, 3.9, (5, 2000, 3)),
        (0.1, 0.5, (1, 10000, 1)),
        (1e-9, None, (1, 1_000_000_000, 1)),
    ],
)
def test_decimal_rates_become_integers(rate, burst, policy):
    assert to_policy(rate, burst) == policy


def test_off_without_a_rate():
    assert build_limiter(Settings(_env_file=None)) is None


def test_redis_url_requires_a_failure_mode():
    with pytest.raises(ValidationError, match="ON_STORE_ERROR"):
        Settings(api_rate_limit=1, api_rate_limit_redis_url=DOWN, _env_file=None)


def test_redis_url_is_not_shown_in_settings():
    url = SecretStr("redis://:hunter2@127.0.0.1:1/0")
    settings = Settings(
        api_rate_limit_redis_url=url, api_rate_limit_on_store_error="open", _env_file=None
    )

    assert "hunter2" not in repr(settings)


def _down(make_client, settings, mode):
    update = {
        "api_rate_limit": 1,
        "api_rate_limit_redis_url": DOWN,
        "api_rate_limit_on_store_error": mode,
    }
    client = make_client(settings.model_copy(update=update))
    client.headers["X-API-Key"] = settings.api_key
    return client


def test_redis_down_and_open_serves_requests(make_client, services, settings):
    services["sheets"].list_spreadsheets.return_value = []

    response = _down(make_client, settings, "open").get("/sheets/list")

    assert response.status_code == 200
    assert "RateLimit" not in response.headers


def test_redis_down_and_closed_answers_503(make_client, settings):
    response = _down(make_client, settings, "closed").get("/sheets/list")

    assert response.status_code == 503
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["detail"] == "API rate limiter unavailable"
    assert response.headers["Retry-After"] == "1"
