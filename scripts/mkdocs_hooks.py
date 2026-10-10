"""MkDocs hooks: publish the READMEs that live outside docs/ without copying them.

The root README, CHANGELOG, CONTRIBUTING, SECURITY and each package README stay
the single source; this adds them to the site as generated pages and rewrites
their relative links: to the page when the target is part of the site, to
GitHub otherwise.
"""

from __future__ import annotations

import posixpath
import re
from pathlib import Path
from typing import Any

from mkdocs.structure.files import File, Files

ROOT = Path(__file__).resolve().parent.parent
GITHUB = "https://github.com/PabloAlaniz/google-suite/blob/main/"
LINK = re.compile(r"(\]\()([^)\s]+)(\))")

PACKAGES = ["core", "gmail", "calendar", "drive", "sheets", "tasks", "contacts", "mcp"]

# repo path -> site path
GENERATED = {
    "README.md": "index.md",
    "CHANGELOG.md": "project/changelog.md",
    "CONTRIBUTING.md": "project/contributing.md",
    "SECURITY.md": "project/security.md",
    **{f"packages/{p}/README.md": f"services/{p}.md" for p in PACKAGES},
}


def _site_path(repo_path: str) -> str | None:
    """Where a repo file lives in the site, or None if it isn't part of it."""
    if repo_path in GENERATED:
        return GENERATED[repo_path]
    if repo_path.startswith("docs/") and repo_path.endswith(".md"):
        return repo_path.removeprefix("docs/")
    return None


def rewrite_links(markdown: str, repo_path: str) -> str:
    """Point the relative links of ``repo_path`` (a repo file) at the site or GitHub."""
    page = GENERATED[repo_path]

    def fix(match: re.Match[str]) -> str:
        target = match.group(2)
        if re.match(r"^[a-z]+:|^#|^/", target):
            return match.group(0)
        path, _, anchor = target.partition("#")
        resolved = posixpath.normpath(posixpath.join(posixpath.dirname(repo_path), path))
        site = _site_path(resolved)
        if site is None:
            new = GITHUB + resolved
        else:
            new = posixpath.relpath(site, posixpath.dirname(page) or ".")
        if anchor:
            new += f"#{anchor}"
        return f"{match.group(1)}{new}{match.group(3)}"

    return LINK.sub(fix, markdown)


def on_files(files: Files, config: Any) -> Files:
    for repo_path, site_path in GENERATED.items():
        content = rewrite_links((ROOT / repo_path).read_text(encoding="utf-8"), repo_path)
        files.append(File.generated(config, site_path, content=content))
    return files
