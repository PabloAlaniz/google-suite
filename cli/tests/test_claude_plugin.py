"""The Claude Code plugin (plugins/gsuite-sdk) must ship the same skill as
skills/gsuite-sdk and pin the gsuite-mcp version being released.

Fix a failure with: python scripts/sync_claude_plugin.py
"""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

spec = importlib.util.spec_from_file_location(
    "sync_claude_plugin", ROOT / "scripts" / "sync_claude_plugin.py"
)
sync = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync)


def test_plugin_skill_is_a_copy_of_the_skill():
    assert sync.skill_diff() == []


def test_plugin_pins_the_mcp_server_version():
    assert sync.check() == []
