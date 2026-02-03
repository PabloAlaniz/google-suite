"""Tests for API utilities."""

from unittest.mock import MagicMock

import pytest

from gsuite_core.api_utils import api_call, api_call_optional, map_http_error
from gsuite_core.exceptions import (
    NotFoundError,
    PermissionDeniedError,
    QuotaExceededError,
    RateLimitError,
)


class MockHttpError(Exception):
    """Mock HttpError for testing."""

    def __init__(self, status: int, message: str = "Error"):
        self.resp = MagicMock()
        self.resp.status = status
        self.resp.get = MagicMock(return_value=None)
        self.message = message
        super().__init__(message)


class TestMapHttpError:
    """Tests for map_http_error function."""

    def test_map_404_to_not_found(self):
        """404 errors should map to NotFoundError."""
        error = MockHttpError(404, "Not found")
        result = map_http_error(error, "gmail", "message")

        assert isinstance(result, NotFoundError)
        assert result.service == "gmail"
        assert result.resource_type == "message"

    def test_map_403_to_permission_denied(self):
        """403 errors should map to PermissionDeniedError."""
        error = MockHttpError(403, "Permission denied")
        result = map_http_error(error, "drive", "file")

        assert isinstance(result, PermissionDeniedError)
        assert result.service == "drive"

    def test_map_403_quota_to_quota_exceeded(self):
        """403 with quota message should map to QuotaExceededError."""
        error = MockHttpError(403, "Quota exceeded for this API")
        result = map_http_error(error, "sheets", "spreadsheet")

        assert isinstance(result, QuotaExceededError)
        assert result.service == "sheets"

    def test_map_429_to_rate_limit(self):
        """429 errors should map to RateLimitError."""
        error = MockHttpError(429, "Too many requests")
        result = map_http_error(error, "calendar", "event")

        assert isinstance(result, RateLimitError)
        assert result.service == "calendar"


class TestApiCallDecorator:
    """Tests for api_call decorator."""

    def test_successful_call_returns_result(self):
        """Successful API calls should return normally."""

        @api_call("gmail", "message")
        def successful_function():
            return "success"

        result = successful_function()
        assert result == "success"

    def test_non_http_error_propagates(self):
        """Non-HttpError exceptions should propagate."""

        @api_call("gmail", "message")
        def raises_value_error():
            raise ValueError("Something wrong")

        with pytest.raises(ValueError, match="Something wrong"):
            raises_value_error()


class TestApiCallOptionalDecorator:
    """Tests for api_call_optional decorator."""

    def test_successful_call_returns_result(self):
        """Successful calls return the result."""

        @api_call_optional("drive", "file")
        def get_file():
            return {"id": "123", "name": "test.pdf"}

        result = get_file()
        assert result == {"id": "123", "name": "test.pdf"}

    def test_none_result_returns_none(self):
        """Functions that return None should work."""

        @api_call_optional("drive", "file")
        def get_nothing():
            return None

        result = get_nothing()
        assert result is None
