# Contributing to Google Suite

Thanks for your interest in contributing! Here's how to get started.

## Development Setup

### Prerequisites

- Python 3.11+
- Git
- A Google Cloud project with OAuth credentials (see [Getting Credentials](#getting-credentials))

### Clone and Install

```bash
# Clone the repo
git clone https://github.com/PabloAlaniz/google-suite.git
cd google-suite

# Create virtual environment (recommended)
python -m venv venv
source venv/bin/activate  # or `venv\Scripts\activate` on Windows

# Install all packages in development mode
pip install -e "packages/core[dev]"
pip install -e "packages/gmail[dev]"
pip install -e "packages/calendar[dev]"
pip install -e "packages/drive[dev]"
pip install -e "packages/sheets[dev]"
pip install -e "api[dev]"
pip install -e "cli[dev]"
```

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=packages --cov-report=html

# Run specific package tests
pytest packages/gmail/tests/
pytest packages/calendar/tests/

# Run single test
pytest packages/gmail/tests/test_query.py::test_from_query
```

### Linting

```bash
# Check code style
ruff check packages/ api/ cli/

# Auto-fix issues
ruff check --fix packages/ api/ cli/

# Format code
ruff format packages/ api/ cli/
```

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
