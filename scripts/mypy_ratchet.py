"""Run mypy per package and fail if any error count goes above the baseline.

The codebase is not mypy-clean yet, so CI cannot require zero errors. This
ratchet blocks regressions instead: counts may only go down. When you fix
errors, run with --update and commit the new mypy-baseline.json.

Usage:
    python scripts/mypy_ratchet.py            # check
    python scripts/mypy_ratchet.py --update   # rewrite the baseline
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASELINE = ROOT / "mypy-baseline.json"

TARGETS = {
    "core": "packages/core/src",
    "gmail": "packages/gmail/src",
    "calendar": "packages/calendar/src",
    "drive": "packages/drive/src",
    "sheets": "packages/sheets/src",
    "api": "api/src",
    "cli": "cli/src",
}

SUMMARY = re.compile(r"Found (\d+) errors? in")


def count_errors(path: str) -> int:
    result = subprocess.run(
        [sys.executable, "-m", "mypy", path],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        return 0
    match = SUMMARY.search(result.stdout)
    if match is None:
        # mypy crashed or the config is broken; don't mistake that for a count
        print(result.stdout, result.stderr, sep="\n")
        raise SystemExit(f"mypy did not report an error count for {path}")
    return int(match.group(1))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--update", action="store_true", help="rewrite the baseline")
    args = parser.parse_args()

    current = {name: count_errors(path) for name, path in TARGETS.items()}

    if args.update:
        BASELINE.write_text(json.dumps(current, indent=2) + "\n")
        print(f"Baseline updated: {current}")
        return 0

    baseline = json.loads(BASELINE.read_text())
    failed = False
    for name, count in current.items():
        allowed = baseline.get(name, 0)
        if count > allowed:
            status = f"FAIL (baseline {allowed})"
            failed = True
        elif count < allowed:
            status = f"improved from {allowed}, run with --update"
        else:
            status = "ok"
        print(f"{name:<9} {count:>4} errors  {status}")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
