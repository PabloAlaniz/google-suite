"""Count ruff findings for rules the code doesn't meet yet; fail if any count grows.

These rules have too many findings to enable in pyproject.toml at once, so CI
holds each count at its baseline instead: counts may only go down. When you
fix findings, run with --update and commit the new lint-baseline.json.

Rules:
    D        docstrings (Google convention; D105/D107 off, D403 off because
             summaries start with API names such as runReport)
    PLC0415  imports inside functions (lazy imports keep a noqa with the reason)
    PLR0913  more than 5 arguments
    SLF001   access to another object's private members

Usage:
    python scripts/lint_ratchet.py            # check
    python scripts/lint_ratchet.py --update   # rewrite the baseline
"""

import argparse
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASELINE = ROOT / "lint-baseline.json"

RULES = ["D", "PLC0415", "PLR0913", "SLF001"]
IGNORE = ["D105", "D107", "D403"]
# Library code only; test fakes and property strategies are out of scope
PATHS = [
    *sorted(str(p.relative_to(ROOT)) for p in ROOT.glob("packages/*/src")),
    "api/src",
    "cli/src",
]
EXCLUDE = "**/testing/**,**/_testing/**"


def count_findings() -> Counter[str]:
    # fixed argv: this interpreter running ruff on the paths above
    result = subprocess.run(  # noqa: S603
        [
            sys.executable,
            "-m",
            "ruff",
            "check",
            "--no-cache",
            "--exit-zero",
            "--output-format=json",
            f"--select={','.join(RULES)}",
            f"--ignore={','.join(IGNORE)}",
            "--config=lint.pydocstyle.convention='google'",
            f"--extend-exclude={EXCLUDE}",
            *PATHS,
        ],
        check=True,
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    return Counter(finding["code"] for finding in json.loads(result.stdout))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--update", action="store_true", help="rewrite the baseline")
    args = parser.parse_args()

    current = count_findings()

    if args.update:
        BASELINE.write_text(json.dumps(dict(sorted(current.items())), indent=2) + "\n")
        print(f"Baseline updated: {sum(current.values())} findings")
        return 0

    baseline: dict[str, int] = json.loads(BASELINE.read_text())
    failed = False
    for code in sorted(set(current) | set(baseline)):
        count, allowed = current.get(code, 0), baseline.get(code, 0)
        if count > allowed:
            status = f"FAIL (baseline {allowed})"
            failed = True
        elif count < allowed:
            status = f"improved from {allowed}, run with --update"
        else:
            status = "ok"
        print(f"{code:<8} {count:>4}  {status}")

    if failed:
        print(
            "\nSee the new findings with: uv run ruff check --select <CODE> "
            "--config \"lint.pydocstyle.convention='google'\" packages/*/src api/src cli/src"
        )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
