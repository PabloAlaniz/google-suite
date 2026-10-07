# ADR 0001: Incorporate GSpreadManager into gsuite-sdk

- Status: accepted
- Date: 2026-10-06

## Context

`PabloAlaniz/GSpreadManager` (a Google Sheets library, 3.0 in its repo) and
`gsuite_sheets` covered the same ground. GSpreadManager was far deeper (~334 KB
vs ~39 KB): typed rows, upsert, streaming, validation, conditional formats,
charts, pivots, caching, an in-memory emulator. Keeping both meant two Sheets
implementations drifting apart.

Usage of GSpreadManager, measured before deciding:

| Signal | Value |
|---|---|
| Stars / forks | 0 / 0 |
| Repo views (14 days) | 0 |
| PyPI downloads | ~9/month (bot noise; gsuite-sdk shows ~12) |
| Public code importing it | two of the author's own scripts, pinned to 0.1.5 |
| 2.x / 3.0 releases | never published (PyPI still at 0.1.5, 2023) |

## Decision

Incorporate the GSpreadManager engine into `gsuite_sheets`:

- Merge its history (`git filter-repo`) into `packages/sheets/src/gsuite_sheets/engine`,
  keeping domain, ports, application services, the in-memory emulator,
  cache, model codecs and the facade as internal orchestration.
- Drop its transports (native REST client, gspread), auth and retries: an
  adapter (`engine_adapter.py`) implements the engine's ports on top of
  `gsuite_core.execute`, so Sheets shares auth, retries and errors with the
  rest of the suite.
- Keep `Sheets` / `Spreadsheet` / `Worksheet` as the only public API,
  extended with the engine's features.
- Async (GSpreadManager's `AsyncSheetManager`) is left for a suite-wide
  async design.
- Archive the GSpreadManager repository with a pointer to gsuite-sdk; PyPI
  stays at 0.1.5 so the two existing scripts keep working.

## Consequences

- One Sheets implementation and one A1 parser for the suite.
- The engine's tests run twice in CI: against the emulator and through the
  real adapter over a fake googleapiclient service backed by the same
  emulator, which pins the adapter's behavior to the engine's.
- Bugs found while integrating were fixed rather than carried over: bare
  sheet titles in ranges, unescaped Drive queries, `range()` dropping empty
  cells, domain shares losing the domain, `insert(fila=n)` appending instead
  of inserting, and the A1 parser dropping the start row of `A2:C`.
