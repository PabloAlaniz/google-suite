"""Pick which package test jobs CI should run.

Reads the event name and the dorny/paths-filter `changes` output from the
environment and writes `packages` (JSON list) and `all` (true/false) to
$GITHUB_OUTPUT.

- Anything other than a pull request (push to main, nightly, manual run) tests
  every package.
- A change to core or shared config tests every package.
- A change to a service package also tests api and cli, which import them.
"""

import json
import os

PACKAGES = ["core", "gmail", "calendar", "drive", "sheets", "tasks", "contacts", "api", "cli"]
SERVICES = {"gmail", "calendar", "drive", "sheets", "tasks", "contacts"}


def select(event: str, changes: list[str]) -> list[str]:
    if event != "pull_request" or "shared" in changes:
        return PACKAGES
    selected = {c for c in changes if c in PACKAGES}
    if selected & SERVICES:
        selected |= {"api", "cli"}
    return [p for p in PACKAGES if p in selected]


def main() -> None:
    event = os.environ["EVENT_NAME"]
    changes = json.loads(os.environ.get("CHANGES") or "[]")
    packages = select(event, changes)

    lines = [
        f"packages={json.dumps(packages)}",
        f"all={str(packages == PACKAGES).lower()}",
    ]
    print("\n".join(lines))
    with open(os.environ["GITHUB_OUTPUT"], "a") as out:
        out.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
