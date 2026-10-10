"""One table with how each project is doing on each channel.

    python stats/stats.py [stats/projects.json] > stats.md

Each project in the JSON can name its GitHub repo, PyPI package, ClawHub slug,
claude-plugins.dev skill (owner/repo/skill) and MCP Registry server name; the
missing ones are skipped. Standard library only; set GITHUB_TOKEN to avoid
GitHub's anonymous rate limit.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path
from typing import Any

TIMEOUT = 20


def fetch(url: str, headers: dict[str, str] | None = None) -> Any:
    request = urllib.request.Request(
        url, headers={"User-Agent": "agent-distribution-stats", **(headers or {})}
    )
    for _attempt in range(2):  # one retry: these APIs time out now and then
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return None
        except (urllib.error.URLError, TimeoutError, ValueError):
            pass
    return None


def github_stars(repo: str) -> str:
    token = os.environ.get("GITHUB_TOKEN")
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    data = fetch(f"https://api.github.com/repos/{repo}", headers)
    return str(data["stargazers_count"]) if data else "?"


def pypi_month(package: str) -> str:
    data = fetch(f"https://pypistats.org/api/packages/{package.lower()}/recent")
    return str(data["data"]["last_month"]) if data else "?"


def clawhub(slug: str) -> str:
    data = fetch(f"https://clawhub.ai/api/v1/skills/{slug}")
    if not data:
        return "?"
    stats = data["skill"]["stats"]
    return (
        f"{stats['downloads']} dl / {stats['installs']} inst (v{data['latestVersion']['version']})"
    )


def claude_plugins(skill: str) -> str:
    data = fetch(f"https://api.claude-plugins.dev/api/skills/{skill}/stats")
    if not data or "installs" not in data:
        return "not indexed"
    return f"{data['installs']['total']} inst ({data['installs']['month']} this month)"


def mcp_registry(name: str) -> str:
    query = urllib.parse.urlencode({"search": name.split("/")[-1]})
    data = fetch(f"https://registry.modelcontextprotocol.io/v0/servers?{query}")
    if not data:
        return "?"
    versions = [
        s["server"]["version"]
        for s in data.get("servers", [])
        if s.get("server", {}).get("name") == name
    ]
    return f"v{versions[0]}" if versions else "not listed"


COLUMNS = [
    ("GitHub ★", "github", github_stars),
    ("PyPI / month", "pypi", pypi_month),
    ("ClawHub", "clawhub", clawhub),
    ("claude-plugins.dev", "claude_plugins_skill", claude_plugins),
    ("MCP Registry", "mcp_registry", mcp_registry),
]


def main() -> None:
    path = Path(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).with_name("projects.json"))
    projects = json.loads(path.read_text(encoding="utf-8"))
    print(f"# Agent distribution stats ({date.today().isoformat()})\n")
    print("| Project | " + " | ".join(title for title, _, _ in COLUMNS) + " |")
    print("|---|" + "---|" * len(COLUMNS))
    for project in projects:
        cells = [fn(project[key]) if project.get(key) else "—" for _, key, fn in COLUMNS]
        print(f"| {project['name']} | " + " | ".join(cells) + " |")


if __name__ == "__main__":
    main()
