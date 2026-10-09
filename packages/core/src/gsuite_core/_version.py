"""Installed package version."""

from importlib.metadata import PackageNotFoundError, version


def _package_version() -> str:
    # pyproject.toml is the single source of truth; release-please bumps it.
    # Released installs are gsuite-sdk; per-package dev installs are gsuite-core.
    for dist in ("gsuite-sdk", "gsuite-core"):
        try:
            return version(dist)
        except PackageNotFoundError:
            continue
    return "0.0.0+unknown"


__version__ = _package_version()
