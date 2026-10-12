"""Keep the Claude Code plugin (plugins/gsuite-sdk) in sync with the repo.

A plugin can only ship files inside its own folder, so the plugin carries a
copy of skills/gsuite-sdk, and the Claude Directory requires the MCP launcher
to pin an exact version (uvx gsuite-mcp==X.Y.Z). This script copies the skill
and writes the version of packages/mcp into plugin.json.
cli/tests/test_claude_plugin.py fails when they drift; the Release workflow
runs it on the release PR, since release-please can't rewrite the pin.

Usage:
    python scripts/sync_claude_plugin.py           # write
    python scripts/sync_claude_plugin.py --check   # exit 1 if out of sync
"""

import argparse
import filecmp
import json
import shutil
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "skills" / "gsuite-sdk"
PLUGIN = ROOT / "plugins" / "gsuite-sdk"
PLUGIN_SKILL = PLUGIN / "skills" / "gsuite-sdk"
MANIFEST = PLUGIN / ".claude-plugin" / "plugin.json"


def mcp_version() -> str:
    pyproject = tomllib.loads((ROOT / "packages/mcp/pyproject.toml").read_text(encoding="utf-8"))
    return pyproject["project"]["version"]


def expected_manifest() -> dict:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    version = mcp_version()
    manifest["version"] = version
    manifest["mcpServers"]["gsuite"]["args"] = [f"gsuite-mcp=={version}"]
    return manifest


def skill_diff() -> list[str]:
    """Relative paths that differ between the skill and the plugin's copy."""

    def files(base: Path) -> set[str]:
        return {
            p.relative_to(base).as_posix()
            for p in base.rglob("*")
            if p.is_file() and "__pycache__" not in p.parts
        }

    src, dst = files(SKILL), files(PLUGIN_SKILL)
    changed = {f for f in src & dst if not filecmp.cmp(SKILL / f, PLUGIN_SKILL / f, shallow=False)}
    return sorted((src ^ dst) | changed)


def check() -> list[str]:
    problems = [f"plugin skill differs: {f}" for f in skill_diff()]
    if json.loads(MANIFEST.read_text(encoding="utf-8")) != expected_manifest():
        problems.append(
            f"{MANIFEST.relative_to(ROOT)}: version or gsuite-mcp pin != {mcp_version()}"
        )
    return problems


def write() -> None:
    shutil.rmtree(PLUGIN_SKILL, ignore_errors=True)
    shutil.copytree(SKILL, PLUGIN_SKILL, ignore=shutil.ignore_patterns("__pycache__"))
    MANIFEST.write_text(json.dumps(expected_manifest(), indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="fail instead of writing")
    if parser.parse_args().check:
        problems = check()
        for p in problems:
            print(p, file=sys.stderr)
        if problems:
            print("run: python scripts/sync_claude_plugin.py", file=sys.stderr)
            sys.exit(1)
    else:
        write()


if __name__ == "__main__":
    main()
