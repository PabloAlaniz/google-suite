"""Machine-readable output."""

import dataclasses
import json
from datetime import date, datetime
from typing import Any

import typer


def print_json(data: Any) -> None:
    """Write JSON to stdout as-is.

    Not through rich's console.print: it wraps long lines at the terminal
    width, which inserts newlines inside JSON strings and breaks `| jq`.
    """
    typer.echo(json.dumps(data, indent=2, ensure_ascii=False, default=str))


def to_data(value: Any, keep_raw: bool = False) -> Any:
    """SDK entities as JSON-ready data: dataclasses become dicts (without their ``raw``
    API resource unless ``keep_raw``), dates become ISO strings."""
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {
            f.name: to_data(getattr(value, f.name), keep_raw)
            for f in dataclasses.fields(value)
            if keep_raw or f.name != "raw"
        }
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, list | tuple):
        return [to_data(v, keep_raw) for v in value]
    if isinstance(value, dict):
        return {k: to_data(v, keep_raw) for k, v in value.items()}
    return value
