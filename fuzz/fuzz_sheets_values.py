"""Fuzz cell-value handling: hex colors, numericise, schema coercion, spreadsheet IDs."""

import sys

import atheris

with atheris.instrument_imports():
    from gsuite_sheets._testing.properties import (
        COERCE_TYPES,
        check_coerce,
        check_color_from_hex,
        check_numericise,
        check_spreadsheet_id_from_url,
        check_spreadsheet_id_round_trip,
    )

KINDS = sorted(COERCE_TYPES)


def TestOneInput(data: bytes) -> None:
    fdp = atheris.FuzzedDataProvider(data)
    choice = fdp.ConsumeIntInRange(0, 4)
    if choice == 0:
        check_color_from_hex(fdp.ConsumeUnicodeNoSurrogates(16))
    elif choice == 1:
        check_numericise(fdp.ConsumeUnicodeNoSurrogates(64))
    elif choice == 2:
        kind = KINDS[fdp.ConsumeIntInRange(0, len(KINDS) - 1)]
        check_coerce(fdp.ConsumeUnicodeNoSurrogates(64), kind)
    elif choice == 3:
        check_spreadsheet_id_from_url(fdp.ConsumeUnicodeNoSurrogates(200))
    else:
        check_spreadsheet_id_round_trip(fdp.ConsumeUnicodeNoSurrogates(64))


def main() -> None:
    atheris.Setup(sys.argv, TestOneInput)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
