"""Fuzz the HTML-to-text conversion used by Gmail send() and forward().

Besides the output invariants, the fuzzed fragment is repeated to ~200 KB to
catch super-linear behavior that small inputs can't show.
"""

import sys

import atheris

with atheris.instrument_imports():
    from gsuite_gmail._testing.properties import (
        check_html_to_text_plain_passthrough,
        check_html_to_text_scales,
        check_html_to_text_strips_tags,
    )


def TestOneInput(data: bytes) -> None:
    fdp = atheris.FuzzedDataProvider(data)
    choice = fdp.ConsumeIntInRange(0, 7)
    markup = fdp.ConsumeUnicodeNoSurrogates(len(data))
    if choice < 3:
        check_html_to_text_plain_passthrough(markup)
    elif choice < 7:
        check_html_to_text_strips_tags(markup)
    else:
        # Converts ~250 KB per call: keep it to one input in eight
        check_html_to_text_scales(markup)


def main() -> None:
    atheris.Setup(sys.argv, TestOneInput)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
