"""Fuzz the Gmail query builder and MIME composition (no term or header injection)."""

import re
import sys

import atheris

with atheris.instrument_imports():
    from gsuite_gmail._testing.properties import (
        QUERY_OPERATORS,
        check_compose_roundtrip,
        check_construct_query_terms,
        check_query_combinators,
        check_query_single_term,
    )

LOCAL_CHARS = list("abcdefghijklmnopqrstuvwxyz0123456789._-")
DOMAIN_CHARS = list("abcdefghijklmnopqrstuvwxyz")


def _text(fdp: atheris.FuzzedDataProvider, size: int = 40) -> str:
    return fdp.ConsumeUnicodeNoSurrogates(size)


def _optional(fdp: atheris.FuzzedDataProvider) -> str | None:
    return _text(fdp) if fdp.ConsumeBool() else None


def _texts(fdp: atheris.FuzzedDataProvider, most: int) -> list[str]:
    return [_text(fdp) for _ in range(fdp.ConsumeIntInRange(0, most))]


def _address(fdp: atheris.FuzzedDataProvider) -> str:
    """A plain valid address: compose only promises a round trip for those."""
    local = "".join(fdp.PickValueInList(LOCAL_CHARS) for _ in range(fdp.ConsumeIntInRange(1, 10)))
    domain = "".join(fdp.PickValueInList(DOMAIN_CHARS) for _ in range(fdp.ConsumeIntInRange(1, 10)))
    local = re.sub(r"\.+", ".", local).strip(".") or "a"
    return f"{local}@{domain}.com"


def _addresses(fdp: atheris.FuzzedDataProvider, least: int, most: int) -> list[str]:
    return [_address(fdp) for _ in range(fdp.ConsumeIntInRange(least, most))]


def TestOneInput(data: bytes) -> None:
    fdp = atheris.FuzzedDataProvider(data)
    choice = fdp.ConsumeIntInRange(0, 3)
    if choice == 0:
        operator = QUERY_OPERATORS[fdp.ConsumeIntInRange(0, len(QUERY_OPERATORS) - 1)]
        check_query_single_term(operator, _text(fdp))
    elif choice == 1:
        check_query_combinators(_text(fdp), _text(fdp))
    elif choice == 2:
        check_construct_query_terms(_optional(fdp), _optional(fdp), _optional(fdp), _texts(fdp, 3))
    else:
        names = [name for name in _texts(fdp, 2) if name]
        check_compose_roundtrip(_addresses(fdp, 1, 3), _text(fdp, 80), _addresses(fdp, 0, 2), names)


def main() -> None:
    atheris.Setup(sys.argv, TestOneInput)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
