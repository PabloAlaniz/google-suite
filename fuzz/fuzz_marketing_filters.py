"""Fuzz the Search Console and GA4 request builders (filters, property IDs, days)."""

import sys

import atheris

with atheris.instrument_imports():
    from gsuite_analytics._testing import properties as analytics
    from gsuite_searchconsole._testing import properties as searchconsole


def _text(fdp: atheris.FuzzedDataProvider) -> str:
    return fdp.ConsumeUnicodeNoSurrogates(fdp.ConsumeIntInRange(0, 16))


def _value(fdp: atheris.FuzzedDataProvider) -> object:
    kind = fdp.ConsumeIntInRange(0, 4)
    if kind == 0:
        return fdp.ConsumeInt(8)
    if kind == 1:
        return fdp.ConsumeRegularFloat() if fdp.ConsumeBool() else fdp.ConsumeFloat()
    if kind == 2:
        return fdp.ConsumeBool()
    if kind == 3:
        return None
    return _text(fdp)


def _ga4_filter(fdp: atheris.FuzzedDataProvider) -> dict[str, object]:
    f: dict[str, object] = {"field": _text(fdp)}
    if fdp.ConsumeBool():
        f["operator"] = _text(fdp)
    if fdp.ConsumeBool():
        f["value"] = _value(fdp)
    if fdp.ConsumeBool():
        f["values"] = [_value(fdp) for _ in range(fdp.ConsumeIntInRange(0, 3))]
    if fdp.ConsumeBool():
        f["not"] = fdp.ConsumeBool()
    return f


def _sc_filter(fdp: atheris.FuzzedDataProvider) -> dict[str, str]:
    f = {"dimension": _text(fdp), "expression": _text(fdp)}
    if fdp.ConsumeBool():
        f["operator"] = _text(fdp)
    return f


def TestOneInput(data: bytes) -> None:
    fdp = atheris.FuzzedDataProvider(data)
    choice = fdp.ConsumeIntInRange(0, 4)
    if choice == 0:
        analytics.check_property_name(_text(fdp))
    elif choice == 1:
        analytics.check_build_filter([_ga4_filter(fdp) for _ in range(fdp.ConsumeIntInRange(0, 4))])
    elif choice == 2:
        searchconsole.check_build_filters(
            [_sc_filter(fdp) for _ in range(fdp.ConsumeIntInRange(0, 4))]
        )
    elif choice == 3:
        searchconsole.check_day(_text(fdp))
    else:
        dims = [_text(fdp) or "d" for _ in range(fdp.ConsumeIntInRange(0, 3))]
        mets = [_text(fdp) or "m" for _ in range(fdp.ConsumeIntInRange(0, 3))]
        rows = [
            [_text(fdp) for _ in range(fdp.ConsumeIntInRange(0, 6))]
            for _ in range(fdp.ConsumeIntInRange(0, 3))
        ]
        analytics.check_parse_report(dims, mets, rows)


def main() -> None:
    atheris.Setup(sys.argv, TestOneInput)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
