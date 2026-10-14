"""Fuzz the date parsers of Tasks, Drive and Calendar (always aware, never crash)."""

import sys

import atheris

with atheris.instrument_imports():
    from gsuite_calendar._testing import properties as calendar
    from gsuite_drive._testing import properties as drive
    from gsuite_tasks._testing import properties as tasks

PARSERS = [
    tasks.check_parse_timestamp,
    tasks.check_parse_due,
    drive.check_parse_datetime,
    calendar.check_parse_datetime,
    calendar.check_parse_date,
]


def TestOneInput(data: bytes) -> None:
    fdp = atheris.FuzzedDataProvider(data)
    choice = fdp.ConsumeIntInRange(0, len(PARSERS))
    if choice < len(PARSERS):
        PARSERS[choice](fdp.ConsumeUnicodeNoSurrogates(64))
    else:
        start = fdp.ConsumeUnicodeNoSurrogates(40) if fdp.ConsumeBool() else None
        end = fdp.ConsumeUnicodeNoSurrogates(40) if fdp.ConsumeBool() else None
        calendar.check_event_duration(start, end, fdp.ConsumeBool())


def main() -> None:
    atheris.Setup(sys.argv, TestOneInput)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
