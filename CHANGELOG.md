# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Initial monorepo structure with Clean Architecture
- `gsuite-core`: Unified OAuth2 authentication with token storage (SQLite, Secret Manager)
- `gsuite-gmail`: Gmail client with fluent message API and query builder
- `gsuite-calendar`: Calendar client for events and calendars
- `gsuite-drive`: Drive client for files, folders, and sharing
- `gsuite-sheets`: Sheets client inspired by gspread API
- `gsuite-api`: Unified FastAPI REST gateway
- `gsuite-cli`: Typer CLI with Rich output
- Comprehensive test suite with mocks (2500+ lines)
- Custom exception hierarchy (`gsuite_core.exceptions`)
- PEP 561 compliant with py.typed markers
- Structured logging with HttpError handling

### Architecture
- Monorepo with independent packages
- Shared authentication across all services
- Provider-agnostic design with interfaces
- Type hints throughout (Python 3.11+)

## [0.1.0] - 2026-01-28

### Added
- Initial release
- Core packages: gmail, calendar, drive, sheets
- REST API gateway
- CLI interface
