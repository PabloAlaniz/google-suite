"""Keep an agent skill (SKILL.md + references) in sync with the code it documents.

Usage in a project's test suite::

    from agent_skill_check import SkillCheck

    CHECK = SkillCheck(
        "skills/gsuite-sdk",
        types={"gmail": Gmail, "ws": Worksheet},   # names the skill uses without building them
        cli=typer.main.get_command(app),            # or an argparse.ArgumentParser
        prog="gsuite",
        env_prefix="GSUITE_",
        env_names=SETTINGS_ENV_VARS,
        package="gsuite-sdk",
        extras={"cli", "api", "all"},
        cli_extras={"cli", "all"},
    )

    @pytest.mark.parametrize("name", SkillCheck.CHECKS)
    def test_skill(name):
        problems = CHECK.run(name)
        assert not problems, "\\n".join(problems)
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from agent_skill_check.commands import check_commands, command_lines
from agent_skill_check.snippets import SnippetChecker

__all__ = ["SkillCheck"]

FENCE = re.compile(r"```(\w*)\n(.*?)```", re.S)
SHELL = ("bash", "sh", "shell", "console", "")


def located_blocks(text: str, *languages: str) -> list[tuple[int, str]]:
    """(line number of the block's first code line, code) for each fenced block."""
    return [
        (text.count("\n", 0, m.start(2)) + 1, m.group(2))
        for m in FENCE.finditer(text)
        if m.group(1) in languages
    ]


class SkillCheck:
    """Checks one skill directory. Each check returns a list of problems."""

    CHECKS = ("spec", "frontmatter", "env_vars", "python", "commands")

    def __init__(
        self,
        skill_dir: str | Path,
        *,
        types: dict[str, type] | None = None,
        cli: Any = None,
        prog: str | None = None,
        env_prefix: str | None = None,
        env_names: Iterable[str] = (),
        package: str | None = None,
        extras: Iterable[str] = (),
        cli_extras: Iterable[str] = (),
    ) -> None:
        self.skill_dir = Path(skill_dir)
        self.types = types or {}
        self.cli = cli
        self.prog = prog
        self.env_prefix = env_prefix
        self.env_names = set(env_names)
        self.package = package
        self.extras = set(extras)
        self.cli_extras = set(cli_extras)

    @property
    def docs(self) -> list[Path]:
        return sorted(self.skill_dir.rglob("*.md"))

    def _rel(self, path: Path) -> str:
        return str(path.relative_to(self.skill_dir.parent))

    def run(self, name: str) -> list[str]:
        if name not in self.CHECKS:
            raise ValueError(f"unknown check {name!r}; one of {self.CHECKS}")
        result: list[str] = getattr(self, f"check_{name}")()
        return result

    def run_all(self) -> list[str]:
        return [problem for name in self.CHECKS for problem in self.run(name)]

    # ---------------------------------------------------------------- checks

    def check_spec(self) -> list[str]:
        """The Agent Skills specification, via the reference validator (skills-ref)."""
        from skills_ref import validate

        return [f"{self.skill_dir.name}: {p}" for p in validate(self.skill_dir)]

    def _frontmatter(self) -> dict[str, Any]:
        """The frontmatter with nested values kept (skills-ref flattens metadata to strings)."""
        import strictyaml

        text = (self.skill_dir / "SKILL.md").read_text(encoding="utf-8")
        parts = text.split("---", 2)
        if len(parts) < 3:
            return {}  # check_spec reports it
        try:
            data = strictyaml.dirty_load(parts[1], allow_flow_style=True).data
        except strictyaml.YAMLError:
            return {}  # check_spec reports it
        return data if isinstance(data, dict) else {}

    def check_frontmatter(self) -> list[str]:
        """OpenClaw metadata: required env vars exist; the install line installs the CLI."""
        problems: list[str] = []
        openclaw = (self._frontmatter().get("metadata") or {}).get("openclaw")
        if not isinstance(openclaw, dict):
            return problems
        required = list((openclaw.get("requires") or {}).get("env") or [])
        if primary := openclaw.get("primaryEnv"):
            required.append(primary)
        for var in dict.fromkeys(required):
            if self.env_prefix and not var.startswith(self.env_prefix):
                problems.append(f"frontmatter env {var} doesn't start with {self.env_prefix}")
            elif self.env_names and var not in self.env_names:
                problems.append(f"frontmatter env {var} is not a known setting")
        for item in openclaw.get("install") or []:
            package = str(item.get("package", ""))
            name, _, extra_list = package.partition("[")
            wanted = set(filter(None, extra_list.rstrip("]").split(",")))
            if self.package and name != self.package:
                problems.append(f"install package {name} is not {self.package}")
            if self.extras and (unknown := wanted - self.extras):
                problems.append(f"install extras {sorted(unknown)} don't exist")
            bins = item.get("bins") or []
            if self.prog in bins and self.cli_extras and not wanted & self.cli_extras:
                problems.append(
                    f"the {self.prog} binary needs one of the extras {sorted(self.cli_extras)}"
                )
        return problems

    def check_env_vars(self) -> list[str]:
        """Every PREFIX_* variable mentioned anywhere is a known setting."""
        if not (self.env_prefix and self.env_names):
            return []
        pattern = re.compile(rf"\b{re.escape(self.env_prefix)}[A-Z][A-Z0-9_]*\b")
        problems = []
        for doc in self.docs:
            unknown = sorted(set(pattern.findall(doc.read_text(encoding="utf-8"))) - self.env_names)
            if unknown:
                problems.append(f"{self._rel(doc)}: not known settings: {unknown}")
        return problems

    def check_python(self) -> list[str]:
        problems = []
        for doc in self.docs:
            checker = SnippetChecker(self._rel(doc), self.types)
            for start, block in located_blocks(doc.read_text(encoding="utf-8"), "python", "py"):
                checker.check_block(block, start)
            problems += checker.problems
        return problems

    def check_commands(self) -> list[str]:
        if self.cli is None or not self.prog:
            return []
        problems = []
        for doc in self.docs:
            blocks = [b for _, b in located_blocks(doc.read_text(encoding="utf-8"), *SHELL)]
            problems += check_commands(command_lines(blocks, self.prog), self.cli, self.prog)
        return problems
