# Contributing to Google Suite

Thanks for your interest in contributing! Here's how to get started.

## Development Setup

### Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/)
- Git
- A Google Cloud project with OAuth credentials (see [Getting Credentials](#getting-credentials))

### Clone and Install

```bash
git clone https://github.com/PabloAlaniz/google-suite.git
cd google-suite

# Creates .venv with every package, extra and dev tool pinned by uv.lock
uv sync --all-extras
```

CI installs from the same `uv.lock`. If you change dependencies in
`pyproject.toml`, run `uv lock` and commit the updated lockfile.

### Running Tests

```bash
# Run all tests
uv run pytest

# Run with coverage
uv run pytest --cov --cov-report=html

# Run one package's tests
uv run pytest packages/gmail/tests/
uv run pytest api/tests/

# Run a single test
uv run pytest packages/gmail/tests/test_query.py::TestQueryBuilder::test_from_query
```

Test module names must be unique across the repo (`test_gmail_client.py`,
not `test_client.py`); collection fails otherwise.

### Linting and Type Checking

```bash
# Check code style
uv run ruff check packages/ api/ cli/ scripts/

# Auto-fix issues and format
uv run ruff check --fix packages/ api/ cli/ scripts/
uv run ruff format packages/ api/ cli/ scripts/

# mypy error counts may only go down (see mypy-baseline.json)
uv run python scripts/mypy_ratchet.py
# after fixing type errors:
uv run python scripts/mypy_ratchet.py --update
```

### CI

Every PR runs lint, the mypy ratchet, a build/install smoke test and the
lowest-supported dependency versions. Package tests run per package on
Python 3.11–3.14, but only for the packages a PR touches (core or shared
config runs all of them). macOS and Windows run the full suite. Nightly runs
add the latest release of every dependency.

## Getting Credentials

To test the library locally, you need Google OAuth credentials:

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project (or select existing)
3. Enable the APIs you need:
   - Gmail API
   - Google Calendar API
   - Google Drive API
   - Google Sheets API
4. Go to **APIs & Services > Credentials**
5. Click **Create Credentials > OAuth client ID**
6. Select **Desktop app** as application type
7. Download the JSON file
8. Save it as `credentials.json` in the repo root

**Important:** Never commit `credentials.json` — it's in `.gitignore`.

## Project Structure

```
google-suite/
├── packages/
│   ├── core/           # Shared auth, config, storage
│   │   ├── src/gsuite_core/
│   │   └── tests/
│   ├── gmail/          # Gmail client
│   ├── calendar/       # Calendar client
│   ├── drive/          # Drive client
│   └── sheets/         # Sheets client
├── api/                # FastAPI REST gateway
├── cli/                # Typer CLI
├── conftest.py         # Shared pytest fixtures
├── pyproject.toml      # Workspace config
└── README.md
```

### Design Principles

1. **Package Independence**: Each package can be installed and used independently
2. **Shared Auth**: All packages use `gsuite-core` for authentication
3. **Pythonic API**: Simple, intuitive interfaces inspired by libraries like `gspread`
4. **Type Hints**: Full type annotations for IDE support
5. **Lazy Loading**: API services are created on-demand

## Making Changes

### Adding a Feature

1. Create a branch: `git checkout -b feat/my-feature`
2. Make your changes
3. Add tests for new functionality
4. Update documentation (README, docstrings)
5. Run tests and linting
6. Commit with conventional message (see below)
7. Open a pull request

### Fixing a Bug

1. Create a branch: `git checkout -b fix/description`
2. Add a failing test that reproduces the bug
3. Fix the bug
4. Ensure all tests pass
5. Commit and open PR

### Commit Messages

We use [Conventional Commits](https://www.conventionalcommits.org/):

```
feat: add attachment support to Gmail send
fix: handle empty calendar response
docs: update Gmail README with search examples
test: add Calendar recurring event tests
refactor: simplify OAuth token refresh logic
chore: update dependencies
```

## Pull Request Guidelines

- Keep PRs focused on a single change
- Include tests for new functionality
- Update relevant documentation
- Ensure CI passes (tests + linting)
- Request review from maintainers

## Adding a New Package

To add a new Google API (e.g., Contacts):

1. Create package structure:
   ```
   packages/contacts/
   ├── src/gsuite_contacts/
   │   ├── __init__.py
   │   ├── client.py
   │   └── py.typed
   ├── tests/
   │   └── test_client.py
   ├── pyproject.toml
   └── README.md
   ```

2. Add dependency on `gsuite-core` in `pyproject.toml`
3. Follow existing patterns from other packages
4. Add router in `api/src/gsuite_api/routes/`
5. Add commands in `cli/src/gsuite_cli/`
6. Update main README with new package

## Code Style

- **Line length**: 100 characters
- **Imports**: Sorted with `isort` (via `ruff`)
- **Docstrings**: Google style
- **Type hints**: Required for public functions

Example:

```python
def send_email(
    to: list[str],
    subject: str,
    body: str,
    html: bool = False,
) -> Message:
    """
    Send an email.

    Args:
        to: List of recipient email addresses
        subject: Email subject line
        body: Email body content
        html: Whether body is HTML (default: plain text)

    Returns:
        The sent Message object

    Raises:
        AuthenticationError: If not authenticated
        RateLimitError: If API rate limit exceeded
    """
```

## Questions?

- Open an issue for bugs or feature requests
- Check existing issues before creating new ones
- Be respectful and constructive

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
