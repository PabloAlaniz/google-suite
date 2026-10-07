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

#### Integration tests

`tests/integration/` runs real flows (create, read, delete) against a Google
account. They are not part of `uv run pytest` and skip themselves unless
enabled. Use a throwaway account:

```bash
gsuite auth login --force --scopes all     # with the test account
GSUITE_INTEGRATION=1 uv run pytest tests/integration -rs
```

Every test deletes what it creates. Tasks and Contacts tests skip when the
token lacks their scopes. In CI, `integration.yml` runs them weekly and on
demand with the `GSUITE_INTEGRATION_TOKEN` secret (the output of
`gsuite auth export`) in the `integration` environment. OAuth apps in
"Testing" status issue refresh tokens that expire after 7 days.

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
Python 3.11 (oldest supported) and 3.14 (latest), but only for the packages
a PR touches (core or shared config runs all of them). macOS and Windows run
the full suite. Nightly runs add the latest release of every dependency.

### Documentation

The site at https://pabloalaniz.github.io/google-suite/ is built with MkDocs
from `docs/`, the READMEs (root and packages) and the docstrings:

```bash
uv run --group docs mkdocs serve   # http://127.0.0.1:8000, live reload
uv run --group docs mkdocs build   # strict: broken links and bad docstrings fail
```

The READMEs are not copied into `docs/`: `scripts/mkdocs_hooks.py` adds them as
pages and rewrites their relative links. A new package needs its README in
`PACKAGES` there, a `docs/reference/<pkg>.md` page and entries in the `nav`
of `mkdocs.yml`. Docstrings use the Google style.

### The Sheets engine

`packages/sheets/src/gsuite_sheets/engine/` is the engine incorporated from
[GSpreadManager](https://github.com/PabloAlaniz/GSpreadManager) (merged with its
git history). It is hexagonal:

- `domain/`: pure value objects (CellFormat, Color, ranges, validation, charts, schemas)
- `ports/sheets.py`: `ClientPort` / `SpreadsheetPort` / `WorksheetPort`
- `application/`: services that only talk to those ports
- `testing/in_memory.py`: an in-memory implementation of the ports (a Sheets emulator)

`gsuite_sheets/engine_adapter.py` implements the ports on top of the google-suite
client, so requests go through `gsuite_core.execute` like every other service.
A1 parsing lives only in `gsuite_sheets/a1.py`; the engine delegates to it.

The engine tests run twice in CI: against the emulator, and through the real
adapter over a fake googleapiclient service backed by the same emulator:

```bash
uv run pytest packages/sheets/tests                           # emulator
uv run pytest packages/sheets/tests --engine-backend=adapter  # through the adapter
```

A test that inspects the emulator itself (not port behavior) is marked
`@pytest.mark.memory_only`.

The async engine works the same way: `engine_async_adapter.py` implements the
async ports over `gsuite_core.aio`, and with `--engine-backend=adapter` the
async engine tests go through it, against a fake Sheets/Drive REST server
(`engine/testing/rest_fake.py`, an `httpx.MockTransport`) backed by the same
emulator.

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

PRs are squash-merged and the **PR title** becomes the commit on `main`, so
the title must follow this format (CI checks it). Releases are driven by it:
`fix:` bumps the patch version, `feat:` the minor version, and `feat!:` or a
`BREAKING CHANGE:` footer marks a breaking change.

## Releases

Releases are automated with
[release-please](https://github.com/googleapis/release-please). Every push to
`main` updates a release PR that bumps the version in `pyproject.toml` and
`uv.lock` and writes `CHANGELOG.md`. Merging that PR tags the release and
publishes `gsuite-sdk` to PyPI through trusted publishing. Don't edit the
version by hand: `gsuite_core.__version__`, the API and the CLI all read it
from the installed package metadata.

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
   │   └── test_contacts_client.py   # test module names must be unique repo-wide
   ├── pyproject.toml
   └── README.md
   ```

2. Add dependency on `gsuite-core` in `pyproject.toml`
3. Follow existing patterns from other packages
4. Add router in `api/src/gsuite_api/routes/`
5. Add commands in `cli/src/gsuite_cli/`
6. Wire it into packaging and CI:
   - `where` in `[tool.setuptools.packages.find]` and `source` in `[tool.coverage.run]` (root `pyproject.toml`)
   - `PACKAGES`/`SERVICES` in `scripts/ci_select_packages.py` and a filter in `.github/workflows/ci.yml`
   - `TARGETS` in `scripts/mypy_ratchet.py`, then `uv run python scripts/mypy_ratchet.py --update`
7. Update main README with new package
8. Add the docs pages (see [Documentation](#documentation))

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

## Maintainer setup

One-time repository settings that live on GitHub, not in the repo:

```bash
REPO=PabloAlaniz/google-suite

# Squash-only merges, with the PR title as the commit message
gh api -X PATCH repos/$REPO -F allow_merge_commit=false -F allow_rebase_merge=false \
  -F allow_squash_merge=true -f squash_merge_commit_title=PR_TITLE \
  -f squash_merge_commit_message=PR_BODY -F delete_branch_on_merge=true

# Private vulnerability reports (SECURITY.md points here) and Dependabot security PRs
gh api -X PUT repos/$REPO/private-vulnerability-reporting
gh api -X PUT repos/$REPO/automated-security-fixes

# Let release-please open PRs
gh api -X PUT repos/$REPO/actions/permissions/workflow \
  -f default_workflow_permissions=read -F can_approve_pull_request_reviews=true

# Fine-grained PAT (this repo; contents + pull requests: write) so release PRs trigger CI
gh secret set RELEASE_PLEASE_TOKEN -R $REPO

# Protect main. Apply after ci-ok has run once on main, so the check exists.
gh api -X POST repos/$REPO/rulesets --input .github/rulesets/main.json
```

The ruleset requires a squash-merged PR with `ci-ok`, secret scanning, the
dependency audit, CodeQL and the PR title check green. It has no bypass
actors, so automation that pushed straight to `main` has to open PRs instead.
