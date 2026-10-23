"""Invariants of the ``gsuite_analytics`` request builders, shared by property tests and
fuzz harnesses.

Each check takes arbitrary input and either sees ``ValidationError`` (bad input,
rejected before any request) or a request body the GA4 API accepts.
"""

import math
import re
from typing import Any

from gsuite_analytics.client import (
    MATCH_TYPES,
    NUMERIC_OPS,
    build_filter,
    property_name,
)
from gsuite_analytics.parser import parse_metric, parse_report
from gsuite_core._testing import PropertyViolation, require
from gsuite_core.exceptions import ValidationError

PROPERTY_NAME = re.compile(r"properties/[0-9]+")
INT64 = re.compile(r"-?[0-9]+")


def check_property_name(value: str | int) -> None:
    """``property_name`` gives ``properties/<ascii digits>``, idempotently, or rejects."""
    try:
        name = property_name(value)
    except ValidationError:
        return
    require(PROPERTY_NAME.fullmatch(name) is not None, f"{value!r} -> invalid name {name!r}")
    require(property_name(name) == name, f"property_name is not idempotent on {name!r}")


def _check_numeric(value: dict[str, Any]) -> None:
    require(len(value) == 1, f"NumericValue {value!r} needs exactly one field")
    if "int64Value" in value:
        text = value["int64Value"]
        require(
            isinstance(text, str) and INT64.fullmatch(text) is not None,
            f"int64Value {text!r} is not an integer string",
        )
    else:
        number = value.get("doubleValue")
        require(
            type(number) is float and math.isfinite(number),
            f"doubleValue {number!r} is not a finite float",
        )


def _check_leaf(expr: dict[str, Any]) -> None:
    f = expr["filter"]
    require(isinstance(f.get("fieldName"), str) and f["fieldName"], f"no fieldName in {f!r}")
    if "numericFilter" in f:
        numeric = f["numericFilter"]
        require(numeric["operation"] in NUMERIC_OPS, f"bad operation in {numeric!r}")
        _check_numeric(numeric["value"])
    elif "stringFilter" in f:
        require(f["stringFilter"]["matchType"] in MATCH_TYPES, f"bad matchType in {f!r}")
        require(isinstance(f["stringFilter"]["value"], str), f"non-str value in {f!r}")
    else:
        values = f["inListFilter"]["values"]
        require(all(isinstance(v, str) for v in values), f"non-str list values in {f!r}")


def check_build_filter(filters: list[dict[str, Any]]) -> None:
    """``build_filter`` rejects bad filters, or keeps one valid expression per filter."""
    try:
        expr = build_filter(filters)
    except ValidationError:
        return
    if not filters:
        require(expr is None, f"no filters gave {expr!r}")
        return
    if expr is None:
        raise PropertyViolation(f"{filters!r} gave no expression")
    exprs = [expr] if len(filters) == 1 else expr["andGroup"]["expressions"]
    require(len(exprs) == len(filters), f"{len(filters)} filters -> {len(exprs)} expressions")
    for f, e in zip(filters, exprs, strict=True):
        negated = bool(f.get("not"))
        require(("notExpression" in e) == negated, f"'not' of {f!r} not honored: {e!r}")
        _check_leaf(e["notExpression"] if negated else e)


def check_parse_report(dims: list[str], mets: list[str], rows: list[list[str]]) -> None:
    """Each row maps the header names to its values, in order; metrics become numbers."""
    width = len(dims) + len(mets)
    rows = [r[:width] + [""] * (width - len(r)) for r in rows]
    data = {
        "dimensionHeaders": [{"name": n} for n in dims],
        "metricHeaders": [{"name": n} for n in mets],
        "rows": [
            {
                "dimensionValues": [{"value": v} for v in r[: len(dims)]],
                "metricValues": [{"value": v} for v in r[len(dims) :]],
            }
            for r in rows
        ],
    }
    out = parse_report(data)
    require(out.dimensions == dims and out.metrics == mets, f"headers changed: {out!r}")
    require(out.row_count == len(rows), f"row_count {out.row_count} != {len(rows)}")
    for raw, row in zip(rows, out.rows, strict=True):
        dimensions = dict(zip(dims, raw[: len(dims)], strict=True))
        require(row.dimensions == dimensions, f"row {raw!r} -> {row!r}, expected {dimensions!r}")
        metrics = {n: parse_metric(v) for n, v in zip(mets, raw[len(dims) :], strict=True)}
        require(row.metrics == metrics, f"row {raw!r} -> {row!r}, expected {metrics!r}")
        for value in row.metrics.values():
            require(
                value is None or (isinstance(value, int | float) and math.isfinite(value)),
                f"metric not a finite number: {value!r}",
            )


def check_parse_metric(value: str) -> None:
    """A metric is an int when the text is one, a finite float when it reads as one, else None."""
    number = parse_metric(value)
    if number is None:
        return
    require(math.isfinite(number), f"parse_metric({value!r}) = {number!r}")
    require(value.isascii(), f"non-ASCII {value!r} parsed as {number!r}")
    expected = int(value) if isinstance(number, int) else float(value)
    require(number == expected, f"parse_metric({value!r}) = {number!r}")


__all__ = ["check_build_filter", "check_parse_metric", "check_parse_report", "check_property_name"]
