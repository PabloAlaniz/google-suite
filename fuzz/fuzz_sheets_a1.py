"""Fuzz A1 notation: split_sheet, grid_range, A1Range and column letters."""

import sys

import atheris

with atheris.instrument_imports():
    from gsuite_sheets._testing.properties import (
        MAX_COLUMNS,
        check_a1_split_round_trip,
        check_a1range_agrees_with_grid_range,
        check_column_round_trip,
        check_grid_range,
        check_grid_range_total,
        check_split_sheet_lossless,
    )


def TestOneInput(data: bytes) -> None:
    fdp = atheris.FuzzedDataProvider(data)
    choice = fdp.ConsumeIntInRange(0, 5)
    if choice == 0:
        check_split_sheet_lossless(fdp.ConsumeUnicodeNoSurrogates(200))
    elif choice == 1:
        check_grid_range_total(fdp.ConsumeUnicodeNoSurrogates(200), fdp.ConsumeIntInRange(0, 2**31))
    elif choice == 2:
        check_grid_range(fdp.ConsumeUnicodeNoSurrogates(200))
    elif choice == 3:
        check_a1range_agrees_with_grid_range(fdp.ConsumeUnicodeNoSurrogates(200))
    elif choice == 4:
        title = fdp.ConsumeUnicodeNoSurrogates(50)
        cell_range = fdp.ConsumeUnicodeNoSurrogates(50) if fdp.ConsumeBool() else None
        check_a1_split_round_trip(title, cell_range)
    else:
        check_column_round_trip(fdp.ConsumeIntInRange(0, MAX_COLUMNS - 1))


def main() -> None:
    atheris.Setup(sys.argv, TestOneInput)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
