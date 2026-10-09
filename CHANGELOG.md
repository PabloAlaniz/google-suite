# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0](https://github.com/PabloAlaniz/google-suite/compare/v0.1.3...v0.2.0) (2026-10-09)


### ⚠ BREAKING CHANGES

* **core:** trash/delete/share/delete_event/delete_worksheet return False only when the resource doesn't exist; any other failure (auth, permissions, rate limit, 400) raises a GSuiteError instead of also returning False. get_event/Drive.get no longer turn arbitrary exceptions into None, and Gmail.get_signature only tolerates API errors.
* **api:** the API now fails closed. Without GSUITE_API_KEY every request gets a 401; deployments protected some other way (Cloud Run IAM, localhost) must set GSUITE_ALLOW_NO_API_KEY=true. The default host is 127.0.0.1 (settings and `gsuite serve`), CORS is off unless GSUITE_CORS_ORIGINS is set, error bodies are RFC 9457 problem details instead of {"detail": ...}, and the admin key is only read from the X-Admin-Key header.

### Features

* **api:** harden the REST API ([#14](https://github.com/PabloAlaniz/google-suite/issues/14)) ([b40a668](https://github.com/PabloAlaniz/google-suite/commit/b40a668dd35894699c3e1b1105cf29a10824dcc3))
* async foundation and AsyncSheets ([#21](https://github.com/PabloAlaniz/google-suite/issues/21)) ([b022075](https://github.com/PabloAlaniz/google-suite/commit/b022075b83b3556a64d22c0af9bd9b6456ae0c48))
* **core:** retries, pagination and timeouts for every Google request ([#15](https://github.com/PabloAlaniz/google-suite/issues/15)) ([503bd21](https://github.com/PabloAlaniz/google-suite/commit/503bd21aba9f8553095d7964ae4c1c4a67d795be))
* **drive:** complete Drive client, REST routes and CLI ([#16](https://github.com/PabloAlaniz/google-suite/issues/16)) ([7c584ee](https://github.com/PabloAlaniz/google-suite/commit/7c584eeea1e7ebed2baa8e7994c4bfb0b9f9dd7a))
* **gmail,calendar:** threaded replies, attachments, drafts, labels and Meet ([#18](https://github.com/PabloAlaniz/google-suite/issues/18)) ([9c36fff](https://github.com/PabloAlaniz/google-suite/commit/9c36fff4e33cd3802c15c05a829fb0ae08e9955f))
* **sheets:** expose the GSpreadManager engine on the public API ([#20](https://github.com/PabloAlaniz/google-suite/issues/20)) ([0e3c7a0](https://github.com/PabloAlaniz/google-suite/commit/0e3c7a011aaa8f112f7f59f30f3781e14a221420))
* **sheets:** formatting, protection, find/replace, worksheets and pandas ([#17](https://github.com/PabloAlaniz/google-suite/issues/17)) ([35fb962](https://github.com/PabloAlaniz/google-suite/commit/35fb962aa250693d775f62f78e9120d051cb5906))
* **sheets:** incorporate the GSpreadManager engine ([#19](https://github.com/PabloAlaniz/google-suite/issues/19)) ([70c11e5](https://github.com/PabloAlaniz/google-suite/commit/70c11e5a803bdb773de0932d3113ee643b177c89))
* Tasks and Contacts packages with REST API and CLI ([#22](https://github.com/PabloAlaniz/google-suite/issues/22)) ([cfdd84c](https://github.com/PabloAlaniz/google-suite/commit/cfdd84c1e5168b321ff2f1132f37d3477931e1ab))


### Bug Fixes

* add Sheets to default OAuth scopes ([#9](https://github.com/PabloAlaniz/google-suite/issues/9)) ([a082784](https://github.com/PabloAlaniz/google-suite/commit/a0827847a765d52d817d5d732711cc26d1cf9457))
* CI test failure + publish workflow for gsuite-api ([#5](https://github.com/PabloAlaniz/google-suite/issues/5)) ([4367008](https://github.com/PabloAlaniz/google-suite/commit/4367008a7902811d44e91cd6dedc3e547c4436e4))
* **ci:** get main green and run every test ([#11](https://github.com/PabloAlaniz/google-suite/issues/11)) ([13d3979](https://github.com/PabloAlaniz/google-suite/commit/13d3979fad9b1b212b82373a764566c8d75015b3))


### Documentation

* documentation site, integration tests and a smaller Docker image ([#23](https://github.com/PabloAlaniz/google-suite/issues/23)) ([9c9d27f](https://github.com/PabloAlaniz/google-suite/commit/9c9d27fde640a81060b2c0bab666dccf2cb63b46))

## [0.1.3] - 2026-02-11

### Fixed
- **auth**: `is_authenticated()` now correctly returns `True` after loading valid credentials from SQLite
- **auth**: `refresh()` no longer fails with `invalid_scope` error
- Root cause: `Credentials.from_authorized_user_info()` doesn't properly handle scopes; now using `Credentials` constructor directly

## [0.1.0] - 2026-01-28

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
