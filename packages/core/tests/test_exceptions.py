"""Tests for Google Suite exceptions."""

from gsuite_core.exceptions import (
    APIError,
    AuthenticationError,
    CredentialsNotFoundError,
    GSuiteError,
    NotAuthenticatedError,
    NotFoundError,
    PermissionDeniedError,
    QuotaExceededError,
    RateLimitError,
    TokenExpiredError,
    TokenRefreshError,
    ValidationError,
)


class TestGSuiteError:
    """Tests for base GSuiteError."""

    def test_basic_error(self):
        """Test creating a basic error."""
        error = GSuiteError("Something went wrong")
        assert str(error) == "Something went wrong"
        assert error.message == "Something went wrong"
        assert error.cause is None

    def test_error_with_cause(self):
        """Test error with underlying cause."""
        cause = ValueError("original error")
        error = GSuiteError("Wrapped error", cause=cause)
        assert error.cause is cause


class TestAuthenticationErrors:
    """Tests for authentication exceptions."""

    def test_credentials_not_found(self):
        """Test CredentialsNotFoundError."""
        error = CredentialsNotFoundError("/path/to/credentials.json")
        assert "/path/to/credentials.json" in str(error)
        assert error.path == "/path/to/credentials.json"
        assert isinstance(error, AuthenticationError)

    def test_token_expired(self):
        """Test TokenExpiredError."""
        error = TokenExpiredError()
        assert "expired" in str(error).lower()
        assert isinstance(error, AuthenticationError)

    def test_token_refresh_error(self):
        """Test TokenRefreshError."""
        cause = Exception("Network error")
        error = TokenRefreshError(cause=cause)
        assert "refresh" in str(error).lower()
        assert error.cause is cause

    def test_not_authenticated(self):
        """Test NotAuthenticatedError."""
        error = NotAuthenticatedError()
        assert "not authenticated" in str(error).lower()


class TestAPIErrors:
    """Tests for API exceptions."""

    def test_api_error(self):
        """Test basic APIError."""
        error = APIError("Request failed", service="gmail", status_code=500)
        assert error.service == "gmail"
        assert error.status_code == 500

    def test_rate_limit_error(self):
        """Test RateLimitError."""
        error = RateLimitError(service="drive", retry_after=60)
        assert error.status_code == 429
        assert error.retry_after == 60
        assert "drive" in str(error).lower()

    def test_quota_exceeded(self):
        """Test QuotaExceededError."""
        error = QuotaExceededError(service="sheets")
        assert error.status_code == 403
        assert "quota" in str(error).lower()

    def test_not_found_error(self):
        """Test NotFoundError."""
        error = NotFoundError(
            service="gmail",
            resource_type="Message",
            resource_id="msg123",
        )
        assert error.status_code == 404
        assert error.resource_type == "Message"
        assert error.resource_id == "msg123"
        assert "msg123" in str(error)

    def test_permission_denied(self):
        """Test PermissionDeniedError."""
        error = PermissionDeniedError(service="drive", operation="delete")
        assert error.status_code == 403
        assert error.operation == "delete"


class TestValidationError:
    """Tests for ValidationError."""

    def test_validation_error(self):
        """Test ValidationError."""
        error = ValidationError(field="email", message="invalid format")
        assert error.field == "email"
        assert "email" in str(error)
        assert "invalid format" in str(error)


class TestExceptionHierarchy:
    """Test exception inheritance."""

    def test_auth_errors_are_gsuite_errors(self):
        """All auth errors inherit from GSuiteError."""
        assert issubclass(AuthenticationError, GSuiteError)
        assert issubclass(CredentialsNotFoundError, AuthenticationError)
        assert issubclass(TokenExpiredError, AuthenticationError)
        assert issubclass(TokenRefreshError, AuthenticationError)
        assert issubclass(NotAuthenticatedError, AuthenticationError)

    def test_api_errors_are_gsuite_errors(self):
        """All API errors inherit from GSuiteError."""
        assert issubclass(APIError, GSuiteError)
        assert issubclass(RateLimitError, APIError)
        assert issubclass(QuotaExceededError, APIError)
        assert issubclass(NotFoundError, APIError)
        assert issubclass(PermissionDeniedError, APIError)

    def test_can_catch_by_base_class(self):
        """Can catch specific errors with base class."""
        try:
            raise CredentialsNotFoundError("/path")
        except GSuiteError as e:
            assert isinstance(e, CredentialsNotFoundError)
