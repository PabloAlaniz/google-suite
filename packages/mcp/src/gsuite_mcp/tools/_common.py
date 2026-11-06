"""What every tool module shares: annotations, error mapping and parsing."""

from __future__ import annotations

import functools
from collections.abc import Callable
from datetime import date, datetime
from typing import Any, Protocol, TypeVar

from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from gsuite_core.exceptions import GSuiteError, PermissionDeniedError

READ = ToolAnnotations(read_only_hint=True, open_world_hint=True)
WRITE = ToolAnnotations(read_only_hint=False, destructive_hint=False, open_world_hint=True)
DESTRUCTIVE = ToolAnnotations(read_only_hint=False, destructive_hint=True, open_world_hint=True)

F = TypeVar("F", bound=Callable[..., Any])


class Register(Protocol):
    """Registers a function as a tool and returns it unchanged."""

    def __call__(self, func: F, /) -> F: ...


class ToolDecorator(Protocol):
    """``tool(annotations)``: the decorator each module's tools are declared with."""

    def __call__(self, annotations: ToolAnnotations, /) -> Register: ...


def sdk_errors(func: F) -> F:
    """SDK errors become tool errors the agent can read."""

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return func(*args, **kwargs)
        except ToolError:
            raise
        except PermissionDeniedError as exc:
            raise ToolError(
                f"{exc.message}. Usually a scope missing from the login: run "
                "`gsuite auth login --force --scopes default,tasks,contacts` "
                "(add `,marketing` for Search Console, Analytics and Tag Manager)."
            ) from exc
        except GSuiteError as exc:
            raise ToolError(f"{type(exc).__name__}: {exc.message}") from exc
        except ValueError as exc:
            raise ToolError(str(exc)) from exc

    return wrapper  # type: ignore[return-value]


def results(items: list[Any]) -> dict[str, Any]:
    """One object for list results (a bare list becomes one content block per item)."""
    return {"count": len(items), "results": items}


def parse_when(value: str) -> datetime | date:
    """ "2026-03-01" -> date; "2026-03-01T10:00" / "2026-03-01 10:00" -> datetime."""
    try:
        if len(value) == len("YYYY-MM-DD"):
            return date.fromisoformat(value)
        return datetime.fromisoformat(value)
    except ValueError as exc:
        raise ToolError(f"{value!r} is not an ISO date or datetime") from exc


def parse_day(value: str | None) -> date | None:
    if value is None:
        return None
    when = parse_when(value)
    return when.date() if isinstance(when, datetime) else when
