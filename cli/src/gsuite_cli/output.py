"""Machine-readable output."""

import json
from typing import Any

import typer


def print_json(data: Any) -> None:
    """Write JSON to stdout as-is.

    Not through rich's console.print: it wraps long lines at the terminal
    width, which inserts newlines inside JSON strings and breaks `| jq`.
    """
    typer.echo(json.dumps(data, indent=2, ensure_ascii=False, default=str))
