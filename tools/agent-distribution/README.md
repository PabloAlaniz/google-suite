# agent-distribution

> Lives in [google-suite](https://github.com/PabloAlaniz/google-suite) and is shared by
> its author's other projects: install the package from this subdirectory and call
> the `reusable-*.yml` workflows pinned to a commit SHA.

Tools to publish a project's **agent skill** (and MCP server) to the indexes
where AI agents and their users find tools, and to keep it correct.

- **`agent-skill-check`** (Python package, `src/`): tests that a skill's
  `SKILL.md` and `references/` match the code they document. It runs the
  official [Agent Skills](https://agentskills.io) validator, and checks every
  Python snippet (imports, methods, keyword arguments, literal types), shell
  command (commands and options of a Click/Typer or argparse CLI), environment
  variable and OpenClaw install line.
- **Reusable GitHub workflows** (google-suite's `.github/workflows/reusable-*.yml`): validate skills and
  plugin manifests, publish a skill to [ClawHub](https://clawhub.ai), publish
  an MCP server to the [official MCP Registry](https://registry.modelcontextprotocol.io).
- **[PLAYBOOK.md](PLAYBOOK.md)**: the checklist to make a project discoverable
  (layout, manifests, topics, indexes, manual submissions), with
  [templates](templates/).
- **[stats/](stats/)**: one table with installs and downloads per channel.

## agent-skill-check

```bash
pip install "agent-skill-check @ git+https://github.com/PabloAlaniz/google-suite#subdirectory=tools/agent-distribution"
```

With uv, as a dependency group (PyPI rejects git dependencies in published extras):

```toml
[dependency-groups]
skill = ["agent-skill-check"]

[tool.uv.sources]
agent-skill-check = { git = "https://github.com/PabloAlaniz/google-suite", subdirectory = "tools/agent-distribution", rev = "<commit-sha>" }
```

```python
# tests/test_skill.py
import pytest
from typer.main import get_command

from agent_skill_check import SkillCheck
from my_cli.main import app
from my_lib import Client, Sheet

CHECK = SkillCheck(
    "skills/my-lib",
    types={"client": Client, "sheet": Sheet},  # variable names the skill uses without building them
    cli=get_command(app),  # or an argparse.ArgumentParser
    prog="mylib",
    env_prefix="MYLIB_",
    env_names={"MYLIB_TOKEN", "MYLIB_TIMEOUT"},
    package="my-lib",
    extras={"cli", "all"},
    cli_extras={"cli", "all"},  # extras that install the CLI binary
)


@pytest.mark.parametrize("name", SkillCheck.CHECKS)
def test_skill(name):
    problems = CHECK.run(name)
    assert not problems, "\n".join(problems)
```

Each problem names the file and line: `my-lib/references/sheets.md:42:
Sheet has no attribute 'append'`.

## Workflows

```yaml
jobs:
  skill:
    uses: PabloAlaniz/google-suite/.github/workflows/reusable-skill-validate.yml@<commit-sha>

  clawhub:
    needs: publish-pypi
    uses: PabloAlaniz/google-suite/.github/workflows/reusable-clawhub-publish.yml@<commit-sha>
    with:
      skill-path: skills/my-lib
      slug: my-lib
      version: ${{ needs.release.outputs.version }}
    secrets: inherit   # CLAWHUB_TOKEN, an environment secret of "clawhub"

  mcp-registry:
    needs: publish-pypi
    permissions:
      id-token: write
    uses: PabloAlaniz/google-suite/.github/workflows/reusable-mcp-registry-publish.yml@<commit-sha>
```

## License

MIT
