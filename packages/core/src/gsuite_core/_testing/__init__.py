"""Invariant checks shared by the property-based tests and the fuzz harnesses.

Each package keeps its ``check_*`` functions in ``<package>/_testing/properties.py``.
They take concrete inputs, call the code under test and raise
:class:`PropertyViolation` when an invariant breaks, so Hypothesis tests and
atheris harnesses (``fuzz/``) exercise exactly the same properties.
"""


class PropertyViolation(AssertionError):
    """An invariant of the code under test does not hold for some input."""


def require(condition: bool, message: str) -> None:
    """Raise :class:`PropertyViolation` with ``message`` unless ``condition`` holds."""
    if not condition:
        raise PropertyViolation(message)


__all__ = ["PropertyViolation", "require"]
