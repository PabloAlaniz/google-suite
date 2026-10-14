"""Fuzz HTTP error handling: Retry-After, backoff, error bodies and Drive query literals."""

import sys

import atheris

with atheris.instrument_imports():
    from gsuite_core._testing.properties import (
        MAX_BACKOFF_ATTEMPT,
        check_backoff,
        check_drive_query_literal,
        check_map_http_error,
        check_parse_retry_after,
        check_reason_from_body,
    )


def TestOneInput(data: bytes) -> None:
    fdp = atheris.FuzzedDataProvider(data)
    choice = fdp.ConsumeIntInRange(0, 4)
    if choice == 0:
        body = fdp.ConsumeBytes(len(data))
        check_reason_from_body(body if fdp.ConsumeBool() else body.decode("utf-8", "replace"))
    elif choice == 1:
        check_parse_retry_after(fdp.ConsumeUnicodeNoSurrogates(40))
    elif choice == 2:
        retry_after = fdp.ConsumeIntInRange(-(2**63), 2**63) if fdp.ConsumeBool() else None
        check_backoff(
            fdp.ConsumeIntInRange(0, MAX_BACKOFF_ATTEMPT), fdp.ConsumeRegularFloat(), retry_after
        )
    elif choice == 3:
        status = fdp.ConsumeIntInRange(100, 599)
        retry_after = fdp.ConsumeUnicodeNoSurrogates(20) if fdp.ConsumeBool() else None
        check_map_http_error(status, fdp.ConsumeBytes(len(data)), retry_after)
    else:
        check_drive_query_literal(fdp.ConsumeUnicodeNoSurrogates(200))


def main() -> None:
    atheris.Setup(sys.argv, TestOneInput)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
