# Architecture & Design Decisions

## Current State

### What's Good ✅

1. **Dependency Inversion for Storage**
   - `TokenStore` is an abstract interface
   - `GoogleAuth` depends on abstraction, not concrete SQLite
   - Easy to add new storage backends (Secret Manager, Redis, etc.)

2. **Clean Entity Separation**
   - Domain entities: `Message`, `Event`, `File`, `Worksheet`
   - Each has its own module with clear responsibilities

3. **Hierarchical Exceptions**
   - `GSuiteError` → `AuthenticationError` → `TokenRefreshError`
   - Each exception carries relevant context (service, status_code, etc.)

4. **Lazy, Injectable Services**
   - Every client declares its API with the `GoogleService` descriptor
     (`gsuite_core.service`): built on first use, with a r#### 1. Hard Coupling to Google API Client (resolved)

Clients used to call `build()` from `googleapiclient` in a hand-written lazy
property, so tests had to patch each client module's `build`. They now
declare the service once and accept an injected one:

```python
from gsuite_core import GoogleService

class Gmail:
    service = GoogleService("gmail", "v1")

gmail = Gmail(auth)
gmail.service = fake_service  # no build() call
```

Tests that exercise the real build path patch `gsuite_core.service.build`.

 credentials=self.auth.credentials)

    @property
    def service(self):
        if self._service is None:
            self._service = self._service_factory()
        return self._service
```

#### 2. Entities Coupled to Clients (Active Record Anti-pattern)

**Problem:** Entities hold references to their parent client:

```python
@dataclass
class Message:
    _gmail: Optional["Gmail"] = field(default=None, repr=False)

    def mark_as_read(self) -> "Message":
        if self._gmail:
            self._gmail._modify_labels(self.id, remove=["UNREAD"])
        return self
```

**Impact:**
- Entities aren't pure data objects
- Can't serialize/deserialize easily
- Testing requires full client setup
- Circular dependencies

**Solution:** Keep entities pure, use service methods:

```python
# Pure entity - just data
@dataclass
class Message:
    id: str
    subject: str
    # ... no _gmail reference

# Client handles actions
class Gmail:
    def mark_as_read(self, message_id: str) -> None:
        self._modify_labels(message_id, remove=["UNREAD"])

# Usage changes from:
msg.mark_as_read()
# To:
gmail.mark_as_read(msg.id)
```

**Trade-off:** The current fluent API (`msg.mark_as_read().star()`) is very ergonomic. A middle ground could be a separate `MessageActions` helper.

#### 3. Parsing Logic Inside Clients

**Problem:** Each client has inline `_parse_*` methods:

```python
class Gmail:
    def _parse_message(self, data: dict) -> Message:
        # 50+ lines of parsing logic
```

**Impact:**
- Clients have multiple responsibilities (SRP violation)
- Parsing logic isn't reusable
- Hard to unit test parsing separately

**Solution:** Extract to dedicated parsers:

```python
# gsuite_gmail/parser.py
class GmailParser:
    @staticmethod
    def parse_message(data: dict, include_body: bool = True) -> Message:
        """Parse Gmail API response to Message entity."""
        ...

    @staticmethod
    def parse_label(data: dict) -> Label:
        ...

# In client:
from gsuite_gmail.parser import GmailParser

class Gmail:
    def _get_message_by_id(self, message_id: str) -> Message:
        msg_data = self.service.users().messages().get(...).execute()
        return GmailParser.parse_message(msg_data)
```

#### 4. Inconsistent Error Handling

**Problem:** Each method handles `HttpError` differently:

```python
# Calendar - returns None
def get_event(self, event_id: str) -> Event | None:
    try:
        ...
    except HttpError as e:
        if e.resp.status == 404:
            return None
        raise

# Drive - returns bool
def trash(self, file_id: str) -> bool:
    try:
        ...
    except HttpError as e:
        return False
```

**Solution:** Centralized error mapping:

```python
# gsuite_core/errors.py
def map_http_error(error: HttpError, service: str) -> GSuiteError:
    """Map Google API HttpError to domain exception."""
    status = error.resp.status
    if status == 404:
        return NotFoundError(service, "resource", str(error))
    elif status == 403:
        return PermissionDeniedError(service, "operation")
    elif status == 429:
        return RateLimitError(service)
    else:
        return APIError(str(error), service, status)

# Decorator for consistent handling
def api_call(service: str):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except HttpError as e:
                raise map_http_error(e, service)
        return wrapper
    return decorator

# Usage:
class Gmail:
    @api_call("gmail")
    def get_message(self, message_id: str) -> Message:
        ...
```

#### 5. Missing Configuration Options

**Problem:** Hardcoded values:
- Timezone always "UTC" for new events
- No request timeout configuration
- No retry configuration

**Solution:** Extend Settings:

```python
class Settings(BaseSettings):
    # Existing
    credentials_file: str = "credentials.json"

    # Add
    default_timezone: str = "UTC"
    request_timeout: int = 30
    max_retries: int = 3
    retry_delay: float = 1.0
```

## Recommended Refactoring Priority

### Phase 1: Quick Wins (Low Risk) ✅ DONE
1. ✅ Extract parsers to separate modules (Gmail, Calendar, Drive, Sheets)
2. ✅ Add `@api_call` decorator for error handling with retry logic
3. ✅ Add configurable timeouts and retry settings

### Phase 2: Structural (Medium Risk)
4. ⬜ Add service factory injection (for easier testing)
5. ⬜ Add optional pure-entity mode (no client references)

### Phase 3: Advanced (Higher Risk)
6. ⬜ Add repository pattern for data access
7. ⬜ Add caching layer
8. ⬜ Add async support

## Testing Strategy

Current tests are mostly unit tests with mocked API responses. Improvements:

1. **Parser tests** - Test parsing logic in isolation
2. **Integration tests** - Use Google's API with test account (CI only)
3. **Contract tests** - Verify our code matches Google's API schema

## File Structure (Proposed)

```
packages/gmail/src/gsuite_gmail/
├── __init__.py
├── client.py          # High-level Gmail client
├── parser.py          # NEW: Parse API responses
├── message.py         # Message entity
├── label.py           # Label entity
├── query.py           # Query builder
├── thread.py          # Thread entity
└── errors.py          # NEW: Gmail-specific error handling
```
