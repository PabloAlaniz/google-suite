#!/usr/bin/env bash
# Update a checkout of the `claude-plugin` branch with plugins/gsuite-sdk.
#
# The Claude Directory follows that branch: it holds only the plugin, because
# the directory scans every file above the plugin folder too, and the
# monorepo's pyproject.toml ([tool.uv.sources]) fails its checks. The Release
# workflow runs this after PyPI, so the gsuite-mcp pin already resolves.
#
# Usage: scripts/claude_plugin_branch.sh <checkout-of-claude-plugin>
set -euo pipefail

root=$(cd "$(dirname "$0")/.." && pwd)
dest=${1:?usage: $0 <checkout-of-claude-plugin>}

python3 "$root/scripts/sync_claude_plugin.py" --check
find "$dest" -mindepth 1 -maxdepth 1 ! -name .git -exec rm -rf {} +
cp -R "$root/plugins/gsuite-sdk/." "$dest/"
cp "$root/LICENSE" "$dest/LICENSE"
find "$dest" -name __pycache__ -prune -exec rm -rf {} +
