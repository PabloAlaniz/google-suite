"""Check the shell command lines of a skill against the CLI they document.

Works with Click/Typer commands (``typer.main.get_command(app)``) and with
``argparse.ArgumentParser`` objects, by introspection: no process is run.
"""

from __future__ import annotations

import argparse
import re
import shlex
from typing import Any


def command_lines(blocks: list[str], prog: str) -> list[str]:
    """Lines invoking ``prog`` in shell blocks.

    Prompts (``$``, ``!``), leading ``VAR=x`` assignments, comments and pipes are stripped.
    """
    lines = []
    for block in blocks:
        for raw in block.splitlines():
            line = raw.strip().lstrip("$!").strip()
            line = re.sub(r"^(?:[A-Z_][A-Z0-9_]*=\S+\s+)+", "", line)
            if line.startswith(prog + " ") or line == prog:
                lines.append(line.split(" #")[0].split(" |")[0].strip())
    return lines


class _Node:
    """A command or group, whichever CLI library it comes from."""

    def __init__(self, obj: Any) -> None:
        self.obj = obj

    def subcommand(self, name: str) -> _Node | None:
        if hasattr(self.obj, "commands"):  # click / typer group
            sub = self.obj.commands.get(name)
            return _Node(sub) if sub is not None else None
        if isinstance(self.obj, argparse.ArgumentParser):
            for action in self.obj._actions:
                if isinstance(action, argparse._SubParsersAction) and name in action.choices:
                    return _Node(action.choices[name])
        return None

    def is_group(self) -> bool:
        if hasattr(self.obj, "commands"):
            return True
        if isinstance(self.obj, argparse.ArgumentParser):
            return any(isinstance(a, argparse._SubParsersAction) for a in self.obj._actions)
        return False

    def options(self) -> set[str]:
        found = {"--help", "-h"}
        if isinstance(self.obj, argparse.ArgumentParser):
            found.update(self.obj._option_string_actions)
        else:
            for param in getattr(self.obj, "params", []):
                found.update(getattr(param, "opts", []))
                found.update(getattr(param, "secondary_opts", []))
        return found


def check_commands(lines: list[str], cli: Any, prog: str) -> list[str]:
    problems = []
    for line in lines:
        tokens = shlex.split(line)[1:]
        node, path = _Node(cli), [prog]
        unknown = False
        while tokens and node.is_group() and not tokens[0].startswith("-"):
            sub = node.subcommand(tokens[0])
            if sub is None:
                problems.append(f"{line}: unknown command {' '.join(path)} {tokens[0]}")
                unknown = True
                break
            node, path = sub, [*path, tokens.pop(0)]
        if unknown:
            continue
        options = node.options()
        for token in tokens:
            if token.startswith("-") and token != "-" and token.split("=")[0] not in options:
                problems.append(f"{line}: {' '.join(path)} has no option {token}")
    return problems
