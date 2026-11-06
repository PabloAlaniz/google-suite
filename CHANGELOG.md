# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.12.0](https://github.com/PabloAlaniz/google-suite/compare/v0.11.0...v0.12.0) (2026-11-06)


### Features

* raw API resources, a page of Gmail IDs, history labels, raw contact writes ([#106](https://github.com/PabloAlaniz/google-suite/issues/106)) ([f3d7084](https://github.com/PabloAlaniz/google-suite/commit/f3d708405e2d18a4747a6cf862773aec251c3ded))


### Bug Fixes

* **core:** finishing a login no longer fails when Google grants other scopes ([#107](https://github.com/PabloAlaniz/google-suite/issues/107)) ([6646cb7](https://github.com/PabloAlaniz/google-suite/commit/6646cb7d065a4d7a83e43fec935e69fbcc09c351))

## [0.11.0](https://github.com/PabloAlaniz/google-suite/compare/v0.10.0...v0.11.0) (2026-11-06)


### Features

* **api:** async Calendar routes on AsyncCalendar ([#97](https://github.com/PabloAlaniz/google-suite/issues/97)) ([4226ce1](https://github.com/PabloAlaniz/google-suite/commit/4226ce1f0023be1e92f630c9c65655fce875c47b))
* **api:** async Drive routes on AsyncDrive ([#98](https://github.com/PabloAlaniz/google-suite/issues/98)) ([800f11e](https://github.com/PabloAlaniz/google-suite/commit/800f11eb559fb8614b9c623eb9c07713f7ab3963))
* **api:** async Gmail routes on AsyncGmail ([#99](https://github.com/PabloAlaniz/google-suite/issues/99)) ([edab2ee](https://github.com/PabloAlaniz/google-suite/commit/edab2ee359bcfcd1a9b87785b09293c064b7e619))
* **api:** server-side rate limit with GSUITE_API_RATE_LIMIT ([#92](https://github.com/PabloAlaniz/google-suite/issues/92)) ([40f0054](https://github.com/PabloAlaniz/google-suite/commit/40f005462230109de4c7353329ea6c67fdc524d3))
* **calendar:** AsyncCalendar ([#95](https://github.com/PabloAlaniz/google-suite/issues/95)) ([7395efd](https://github.com/PabloAlaniz/google-suite/commit/7395efd65463f41dea488a1028d4385f68fe38f8))
* **calendar:** incremental sync and event identification fields ([#105](https://github.com/PabloAlaniz/google-suite/issues/105)) ([fb6cb95](https://github.com/PabloAlaniz/google-suite/commit/fb6cb958a2f58886502473013bdc196263764bee))
* **contacts:** AsyncContacts ([#103](https://github.com/PabloAlaniz/google-suite/issues/103)) ([3215e49](https://github.com/PabloAlaniz/google-suite/commit/3215e497558e448a98125d3e0703ad6d1eef928e))
* **contacts:** contact groups and sync in the REST API, CLI and MCP ([#102](https://github.com/PabloAlaniz/google-suite/issues/102)) ([b214908](https://github.com/PabloAlaniz/google-suite/commit/b214908a54c75cabb60020ac07aac44cd8715ccf))
* **contacts:** incremental sync, batch get, raw fields and contact groups ([#101](https://github.com/PabloAlaniz/google-suite/issues/101)) ([47c95e6](https://github.com/PabloAlaniz/google-suite/commit/47c95e624bef5f826a0f5aba5d4f6ebdd3921b50))
* **core:** login without a browser, client config without a file, InsufficientScopeError ([7986589](https://github.com/PabloAlaniz/google-suite/commit/7986589e693bf6f9476bafc82bac9e2f4b96c626))
* **drive:** AsyncDrive with resumable chunked uploads ([#96](https://github.com/PabloAlaniz/google-suite/issues/96)) ([752f53c](https://github.com/PabloAlaniz/google-suite/commit/752f53cb120add526cba2e27bf6654f744664940))
* **gmail:** AsyncGmail ([#93](https://github.com/PabloAlaniz/google-suite/issues/93)) ([fe7a1d4](https://github.com/PabloAlaniz/google-suite/commit/fe7a1d4ea9ef72c69bb07bd19632897d208ac01e))
* **gmail:** incremental sync with history, ID-only listing, metadata format ([#104](https://github.com/PabloAlaniz/google-suite/issues/104)) ([9994fb5](https://github.com/PabloAlaniz/google-suite/commit/9994fb50deba823980a59208f67b454e4bf2475a))

## [0.10.0](https://github.com/PabloAlaniz/google-suite/compare/v0.9.0...v0.10.0) (2026-11-04)


### Features

* **mcp:** thread, label, forward, draft and trash tools for Gmail ([#83](https://github.com/PabloAlaniz/google-suite/issues/83)) ([27698f8](https://github.com/PabloAlaniz/google-suite/commit/27698f8714f4c59f6b88743dc6d4b572de917eeb))


### Bug Fixes

* **deps:** bump pyasn1 to 0.6.5 (CVE-2026-119194..119197) ([#79](https://github.com/PabloAlaniz/google-suite/issues/79)) ([6bb5329](https://github.com/PabloAlaniz/google-suite/commit/6bb53297ef50f054c9eb1dc505c79c925564497d))
* **deps:** bump pyasn1 to 0.6.5 in the fuzz build and audit its requirements ([#82](https://github.com/PabloAlaniz/google-suite/issues/82)) ([8d378ba](https://github.com/PabloAlaniz/google-suite/commit/8d378bac43cd1e9f6d1295f948e19b79497673a6))
* **gmail:** handle long decimal charrefs and URL-like attachment names ([#75](https://github.com/PabloAlaniz/google-suite/issues/75)) ([411e8a1](https://github.com/PabloAlaniz/google-suite/commit/411e8a17dd7466fc31d5239929cafafc85581745))

## [0.9.0](https://github.com/PabloAlaniz/google-suite/compare/v0.8.0...v0.9.0) (2026-10-23)


### ⚠ BREAKING CHANGES

* **tagmanager:** return typed models instead of dicts ([#71](https://github.com/PabloAlaniz/google-suite/issues/71))
* **analytics:** return typed models instead of dicts ([#70](https://github.com/PabloAlaniz/google-suite/issues/70))
* **searchconsole:** return typed models instead of dicts ([#68](https://github.com/PabloAlaniz/google-suite/issues/68))

### Features

* **analytics:** return typed models instead of dicts ([#70](https://github.com/PabloAlaniz/google-suite/issues/70)) ([7593d68](https://github.com/PabloAlaniz/google-suite/commit/7593d689220671df5293c5a14bf35bc9003f0521))
* **searchconsole:** return typed models instead of dicts ([#68](https://github.com/PabloAlaniz/google-suite/issues/68)) ([9d9741c](https://github.com/PabloAlaniz/google-suite/commit/9d9741c0b1ec6de2a61ce729873bed552c86e852))
* **tagmanager:** return typed models instead of dicts ([#71](https://github.com/PabloAlaniz/google-suite/issues/71)) ([3f5210b](https://github.com/PabloAlaniz/google-suite/commit/3f5210b127a4d2a78bf3edfc538bdb1e0b4f0dbb))

## [0.8.0](https://github.com/PabloAlaniz/google-suite/compare/v0.7.0...v0.8.0) (2026-10-22)


### Features

* **searchconsole:** query_all pages past the 25000-row cap ([#64](https://github.com/PabloAlaniz/google-suite/issues/64)) ([cc12748](https://github.com/PabloAlaniz/google-suite/commit/cc12748114feca60705b926d36f1516ed81eec16))


### Bug Fixes

* **analytics,searchconsole:** validate property IDs, numeric filters and days ([#63](https://github.com/PabloAlaniz/google-suite/issues/63)) ([a580fe9](https://github.com/PabloAlaniz/google-suite/commit/a580fe9a3bf707f67ef2670696c045dfd1ba4e0d))
* **core:** stop swallowing unexpected errors in auth and token storage ([#66](https://github.com/PabloAlaniz/google-suite/issues/66)) ([c99b93b](https://github.com/PabloAlaniz/google-suite/commit/c99b93bb64941b32eaa3605c11927b9446a427fa))

## [0.7.0](https://github.com/PabloAlaniz/google-suite/compare/v0.6.0...v0.7.0) (2026-10-22)


### Features

* **cli:** searchconsole, analytics and tagmanager commands ([#62](https://github.com/PabloAlaniz/google-suite/issues/62)) ([c48f29f](https://github.com/PabloAlaniz/google-suite/commit/c48f29f3d0dff1cb09fb3f61b853b943a8be7a89))


### Bug Fixes

* **deps:** bump certifi to 2026.10.19 (PYSEC-2026-4320) ([#59](https://github.com/PabloAlaniz/google-suite/issues/59)) ([3bc9446](https://github.com/PabloAlaniz/google-suite/commit/3bc944623be65f050403936ee704f864231a16e2))

## [0.6.0](https://github.com/PabloAlaniz/google-suite/compare/v0.5.2...v0.6.0) (2026-10-16)


### Features

* read-only Search Console, GA4 and Tag Manager support ([#55](https://github.com/PabloAlaniz/google-suite/issues/55)) ([896d406](https://github.com/PabloAlaniz/google-suite/commit/896d406a775c17d9bb6641ff448a1159955485f4))
  * **searchconsole,analytics,tagmanager:** read-only clients for Search Console (sites, search analytics, URL inspection, sitemaps), Google Analytics 4 (Admin account summaries/properties, Data API `runReport`/`runRealtimeReport`) and Tag Manager v2 (accounts, containers, workspaces, tags, triggers, variables, versions)
  * **mcp:** 15 read-only tools for those APIs (`searchconsole_*`, `analytics_*`, `tagmanager_*`)
  * **api:** read-only `/searchconsole`, `/analytics` and `/tagmanager` routes
  * **core,cli:** opt-in scopes `webmasters.readonly`, `analytics.readonly`, `tagmanager.readonly`; `gsuite auth login --scopes` accepts `searchconsole`, `analytics`, `tagmanager` and `marketing` (not in `default`/`all`, so existing logins are not asked to re-consent)

## [0.5.2](https://github.com/PabloAlaniz/google-suite/compare/v0.5.1...v0.5.2) (2026-10-14)


### Bug Fixes

* **gmail:** tolerate Date headers with out-of-range numbers ([#51](https://github.com/PabloAlaniz/google-suite/issues/51)) ([d332541](https://github.com/PabloAlaniz/google-suite/commit/d33254133b23703365e47c21e828a1cfa70a8c32))

## [0.5.1](https://github.com/PabloAlaniz/google-suite/compare/v0.5.0...v0.5.1) (2026-10-14)


### Bug Fixes

* **core,tasks,drive,calendar:** harden retry handling and return aware datetimes ([#45](https://github.com/PabloAlaniz/google-suite/issues/45)) ([1fa4f3c](https://github.com/PabloAlaniz/google-suite/commit/1fa4f3c4ae2e773de3ef7585aade8b94d87dac35))
* **gmail:** harden HTML conversion, query builder and message parsing ([#46](https://github.com/PabloAlaniz/google-suite/issues/46)) ([de6932e](https://github.com/PabloAlaniz/google-suite/commit/de6932e730e2c6a48ae82232aa06e2d7ec33b4de))
* **sheets:** validate A1 references, colors and numbers strictly ([#44](https://github.com/PabloAlaniz/google-suite/issues/44)) ([752f6f3](https://github.com/PabloAlaniz/google-suite/commit/752f6f3f303cdff9d712c1da6566ef4c2c97f763))


### Documentation

* add OpenSSF Best Practices badge ([#38](https://github.com/PabloAlaniz/google-suite/issues/38)) ([d02ac04](https://github.com/PabloAlaniz/google-suite/commit/d02ac04297d5ff23ff052c7ed3679d7d383ff0c3))

## [0.5.0](https://github.com/PabloAlaniz/google-suite/compare/v0.4.0...v0.5.0) (2026-10-12)


### Features

* **plugin:** move the Claude Code plugin to plugins/gsuite-sdk for the Claude Directory ([#31](https://github.com/PabloAlaniz/google-suite/issues/31)) ([754b112](https://github.com/PabloAlaniz/google-suite/commit/754b1126ad7df0980dd228945ec40d44275c401a))

## [0.4.0](https://github.com/PabloAlaniz/google-suite/compare/v0.3.0...v0.4.0) (2026-10-10)


### Features

* **mcp:** gsuite-mcp, an MCP server for Google Workspace ([#29](https://github.com/PabloAlaniz/google-suite/issues/29)) ([3b1a9fe](https://github.com/PabloAlaniz/google-suite/commit/3b1a9fe9b996c0280fc2b8c4a18a5d2f5e6577a1))

## [0.3.0](https://github.com/PabloAlaniz/google-suite/compare/v0.2.0...v0.3.0) (2026-10-10)


### Features

* **skill:** make the agent skill installable on skills.sh, Claude Code and Gemini CLI ([#28](https://github.com/PabloAlaniz/google-suite/issues/28)) ([857a964](https://github.com/PabloAlaniz/google-suite/commit/857a964a0da0a859af08188698aeaf64ac3b9e9f))


### Documentation

* point GSpreadManager references at the archive tag ([#25](https://github.com/PabloAlaniz/google-suite/issues/25)) ([2ff6656](https://github.com/PabloAlaniz/google-suite/commit/2ff66560ffec17834ab08b59f3e3d61706e7ff65))
* **skill:** rewrite the OpenClaw skill for 0.2.0 and keep it in sync ([#26](https://github.com/PabloAlaniz/google-suite/issues/26)) ([a5a422d](https://github.com/PabloAlaniz/google-suite/commit/a5a422da3b55e59cb30bb79886d551a0db2d1dac))

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
