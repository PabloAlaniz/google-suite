"""Google Suite exceptions."""


class GSuiteError(Exception):
    """Base exception for all Google Suite errors."""

    def __init__(self, message: str, cause: Exception | None = None):
        super().__init__(message)
        self.message = message
        self.cause = cause


class AuthenticationError(GSuiteError):
    """Authentication-related errors."""

    pass


class CredentialsNotFoundError(AuthenticationError):
    """OAuth credentials file not found."""

    def __init__(self, path: str):
        super().__init__(
            f"Credentials file not found: {path}\n"
            "Download from Google Cloud Console -> APIs & Services -> Credentials"
        )
        self.path = path


class TokenExpiredError(AuthenticationError):
    """Token is expired and cannot be refreshed."""

    def __init__(self):
        super().__init__("Token expired and no refresh token available")


class TokenRefreshError(AuthenticationError):
    """Failed to refresh token."""

    def __init__(self, cause: Exception | None = None):
        super().__init__("Failed to refresh token", cause)


class NotAuthenticatedError(AuthenticationError):
    """Operation requires authentication but not authenticated."""

    def __init__(self):
        super().__init__("Not authenticated. Run authenticate() first")


class APIError(GSuiteError):
    """Google API call errors."""

    def __init__(
        self,
        message: str,
        service: str,
        status_code: int | None = None,
        cause: Exception | None = None,
    ):
        super().__init__(message, cause)
        self.service = service
        self.status_code = status_code


class RateLimitError(APIError):
    """Rate limit exceeded."""

    def __init__(self, service: str, retry_after: int | None = None):
        super().__init__(
            f"Rate limit exceeded for {service}",
            service=service,
            status_code=429,
        )
        self.retry_after = retry_after


class QuotaExceededError(APIError):
    """API quota exceeded."""

    def __init__(self, service: str):
        super().__init__(
            f"API quota exceeded for {service}",
            service=service,
            status_code=403,
        )


class NotFoundError(APIError):
    """Resource not found."""

    def __init__(self, service: str, resource_type: str, resource_id: str):
        super().__init__(
            f"{resource_type} not found: {resource_id}",
            service=service,
            status_code=404,
        )
        self.resource_type = resource_type
        self.resource_id = resource_id


class PermissionDeniedError(APIError):
    """Permission denied for operation."""

    def __init__(self, service: str, operation: str):
        super().__init__(
            f"Permission denied for {operation}",
            service=service,
            status_code=403,
        )
        self.operation = operation


class ValidationError(GSuiteError):
    """Input validation error."""

    def __init__(self, field: str, message: str):
        super().__init__(f"Validation error on {field}: {message}")
        self.field = field


class ConfigurationError(GSuiteError):
    """Configuration error."""

    pass
