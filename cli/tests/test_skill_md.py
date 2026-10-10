"""The OpenClaw skill (gsuite-sdk/*.md) must match the SDK and CLI it documents.

Agents run the skill's snippets as written, so a renamed method or flag breaks
them silently. This checks, for every Markdown file in gsuite-sdk/:

- frontmatter: env vars are real GSUITE_ settings, and the install line brings
  the CLI when it promises the `gsuite` binary;
- every GSUITE_* variable mentioned is a setting;
- Python blocks parse, their imports resolve, and calls on SDK objects use
  methods and keyword arguments that exist (types are inferred from
  constructors, return annotations and a few conventional variable names);
- every `gsuite ...` command line names real commands and options.
"""

from __future__ import annotations

import ast
import importlib
import inspect
import re
import shlex
import tomllib
import types
import typing
from pathlib import Path

import pytest
from typer.main import get_command

from gsuite_cli.main import app
from gsuite_core import Settings

ROOT = Path(__file__).resolve().parents[2]
SKILL_DIR = ROOT / "gsuite-sdk"
DOCS = sorted(SKILL_DIR.rglob("*.md"))

FENCE = re.compile(r"```(\w*)\n(.*?)```", re.S)
ENV_VAR = re.compile(r"\bGSUITE_[A-Z][A-Z0-9_]*\b")
ID_PLACEHOLDER = re.compile(r"^[A-Z][A-Z0-9_]*_ID$")


def _conventional_types() -> dict[str, type]:
    """Variable names the skill uses for SDK objects without constructing them."""
    from gsuite_calendar import Calendar, CalendarEntity, Event
    from gsuite_contacts import Contact, Contacts
    from gsuite_core import GoogleAuth
    from gsuite_drive import Drive, File
    from gsuite_gmail import Draft, Gmail, Label, Message, Thread
    from gsuite_sheets import Sheets, Spreadsheet, Worksheet
    from gsuite_tasks import Task, TaskList, Tasks

    return {
        "auth": GoogleAuth,
        "gmail": Gmail,
        "msg": Message,
        "message": Message,
        "thread": Thread,
        "draft": Draft,
        "label": Label,
        "calendar": Calendar,
        "event": Event,
        "cal": CalendarEntity,
        "drive": Drive,
        "file": File,
        "sheets": Sheets,
        "spreadsheet": Spreadsheet,
        "ws": Worksheet,
        "tasks": Tasks,
        "task": Task,
        "tasklist": TaskList,
        "contacts": Contacts,
        "contact": Contact,
    }


def _code_blocks(text: str, *languages: str) -> list[str]:
    return [body for _, body in _located_blocks(text, *languages)]


def _located_blocks(text: str, *languages: str) -> list[tuple[int, str]]:
    """(line number of the block's first code line, code) for each fenced block."""
    return [
        (text.count("\n", 0, m.start(2)) + 1, m.group(2))
        for m in FENCE.finditer(text)
        if m.group(1) in languages
    ]


def _frontmatter(text: str) -> str:
    match = re.match(r"---\n(.*?)\n---\n", text, re.S)
    return match.group(1) if match else ""


# ---------------------------------------------------------------- settings


def _setting_names() -> set[str]:
    names = set()
    for name, field in Settings.model_fields.items():
        names.add(f"GSUITE_{name.upper()}")
        alias = field.validation_alias
        for choice in getattr(alias, "choices", [alias] if isinstance(alias, str) else []):
            if isinstance(choice, str) and choice.isupper():
                names.add(choice)
    return names


# ------------------------------------------------------------ type inference


def _unwrap(hint: typing.Any) -> type | None:
    """X | None -> X; list[X] / Iterator[X] -> X; a class -> itself."""
    origin = typing.get_origin(hint)
    if origin in (typing.Union, types.UnionType):
        classes = [_unwrap(a) for a in typing.get_args(hint) if a is not type(None)]
        classes = [c for c in classes if c is not None]
        return classes[0] if len(classes) == 1 else None
    if origin is not None:
        args = typing.get_args(hint)
        if origin in (list, tuple, set) or getattr(origin, "__name__", "") in (
            "Iterator",
            "Iterable",
            "Sequence",
            "AsyncIterator",
        ):
            return _unwrap(args[0]) if args else None
        return None
    return hint if inspect.isclass(hint) else None


def _return_type(cls: type, method: str) -> type | None:
    member = inspect.getattr_static(cls, method, None)
    func = member.fget if isinstance(member, property) else getattr(cls, method, None)
    if func is None:
        return None
    try:
        hints = typing.get_type_hints(func)
    except Exception:  # unresolvable forward references: give up on this value
        return None
    return _unwrap(hints.get("return"))


def _has_member(cls: type, name: str) -> bool:
    if hasattr(cls, name):
        return True
    return any(name in inspect.get_annotations(klass) for klass in cls.__mro__)


class SnippetChecker(ast.NodeVisitor):
    """Walks the Python blocks of one file, sharing variables between blocks."""

    def __init__(self, where: str, env: dict[str, type]) -> None:
        self.where = where
        self.env = env
        self.offset = 0
        self.problems: list[str] = []

    def problem(self, node: ast.AST, message: str) -> None:
        line = getattr(node, "lineno", 1) + self.offset - 1
        self.problems.append(f"{self.where}:{line}: {message}")

    # imports
    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        try:
            module = importlib.import_module(node.module or "")
        except ImportError as exc:
            self.problem(node, f"cannot import {node.module}: {exc}")
            return
        for alias in node.names:
            if not hasattr(module, alias.name):
                self.problem(node, f"{node.module} has no {alias.name}")
            elif inspect.isclass(obj := getattr(module, alias.name)):
                self.env[alias.asname or alias.name] = obj

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            try:
                importlib.import_module(alias.name)
            except ImportError as exc:
                self.problem(node, f"cannot import {alias.name}: {exc}")

    # bindings
    def visit_Assign(self, node: ast.Assign) -> None:
        self.generic_visit(node)
        value_type = self.type_of(node.value)
        for target in node.targets:
            if isinstance(target, ast.Name) and value_type is not None:
                self.env[target.id] = value_type

    def visit_For(self, node: ast.For) -> None:
        self.visit(node.iter)
        if isinstance(node.target, ast.Name) and (item := self.type_of(node.iter)):
            self.env[node.target.id] = item
        for statement in node.body + node.orelse:
            self.visit(statement)

    def visit_comprehension(self, node: ast.comprehension) -> None:
        self.visit(node.iter)
        if isinstance(node.target, ast.Name) and (item := self.type_of(node.iter)):
            self.env[node.target.id] = item
        for condition in node.ifs:
            self.visit(condition)

    def visit_With(self, node: ast.With) -> None:
        for item in node.items:
            self.visit(item.context_expr)
            if isinstance(item.optional_vars, ast.Name) and (
                bound := self.type_of(item.context_expr)
            ):
                self.env[item.optional_vars.id] = bound
        for statement in node.body:
            self.visit(statement)

    visit_AsyncWith = visit_With  # type: ignore[assignment]
    visit_AsyncFor = visit_For  # type: ignore[assignment]

    def type_of(self, node: ast.expr) -> type | None:
        if isinstance(node, ast.Await):
            return self.type_of(node.value)
        if isinstance(node, ast.Name):
            return self.env.get(node.id)
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                called = self.env.get(node.func.id)
                return called if inspect.isclass(called) else None
            if isinstance(node.func, ast.Attribute):
                owner = self.type_of(node.func.value)
                if owner is not None and _has_member(owner, node.func.attr):
                    if inspect.isclass(owner) and isinstance(
                        inspect.getattr_static(owner, node.func.attr, None), classmethod
                    ):
                        return _return_type(owner, node.func.attr) or owner
                    return _return_type(owner, node.func.attr)
        if isinstance(node, ast.Attribute):
            owner = self.type_of(node.value)
            member = owner and inspect.getattr_static(owner, node.attr, None)
            if isinstance(member, property):
                return _return_type(owner, node.attr)
        return None

    # uses
    def visit_Attribute(self, node: ast.Attribute) -> None:
        owner = self.type_of(node.value)
        if owner is not None and not _has_member(owner, node.attr):
            self.problem(node, f"{owner.__name__} has no attribute {node.attr!r}")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        self.generic_visit(node)
        if isinstance(node.func, ast.Attribute):
            owner = self.type_of(node.func.value)
            if owner is None or not _has_member(owner, node.func.attr):
                return
            target = getattr(owner, node.func.attr, None)
            label = f"{owner.__name__}.{node.func.attr}"
        elif isinstance(node.func, ast.Name) and inspect.isclass(self.env.get(node.func.id)):
            target = self.env[node.func.id]
            label = node.func.id
        else:
            return
        if not callable(target):
            return
        try:
            signature = inspect.signature(target)
        except (TypeError, ValueError):
            return
        try:
            hints = typing.get_type_hints(target.__init__ if inspect.isclass(target) else target)
        except Exception:
            hints = {}
        self.check_arguments(node, label, signature, hints)

    def check_arguments(
        self,
        node: ast.Call,
        label: str,
        signature: inspect.Signature,
        hints: dict[str, typing.Any],
    ) -> None:
        params = [p for p in signature.parameters.values() if p.name not in ("self", "cls")]
        if not any(p.kind is p.VAR_KEYWORD for p in params):
            names = {p.name for p in params if p.kind is not p.POSITIONAL_ONLY}
            for keyword in node.keywords:
                if keyword.arg is not None and keyword.arg not in names:
                    self.problem(node, f"{label}() has no keyword argument {keyword.arg!r}")
        positional = [p for p in params if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)]
        if not any(p.kind is p.VAR_POSITIONAL for p in params) and len(node.args) > len(positional):
            self.problem(node, f"{label}() takes at most {len(positional)} positional arguments")
        for param, arg in zip(positional, node.args, strict=False):
            self.check_literal(node, label, param, arg, hints.get(param.name))

    def check_literal(
        self,
        node: ast.Call,
        label: str,
        param: inspect.Parameter,
        arg: ast.expr,
        annotation: typing.Any,
    ) -> None:
        if not (isinstance(arg, ast.Constant) and isinstance(arg.value, str)):
            return
        if annotation is None and param.annotation is not param.empty:
            # get_type_hints failed (a TYPE_CHECKING-only name): use the raw one
            annotation = param.annotation
            if isinstance(annotation, str):
                annotation = list if annotation.startswith("list[") else None
        if annotation is list or typing.get_origin(annotation) is list:
            self.problem(
                node, f"{label}(): {param.name} takes a list, got the string {arg.value!r}"
            )
        if ID_PLACEHOLDER.match(arg.value) and ("title" in param.name or "name" in param.name):
            self.problem(
                node,
                f"{label}(): {param.name} is a title/name, got the ID placeholder {arg.value!r}",
            )


# ------------------------------------------------------------------- tests


@pytest.fixture(scope="module")
def cli() -> typing.Any:
    command = get_command(app)
    assert hasattr(command, "commands")
    return command


def test_skill_files_exist():
    assert (SKILL_DIR / "SKILL.md").exists()


def test_frontmatter():
    text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    front = _frontmatter(text)
    assert front, "SKILL.md needs a frontmatter block"
    problems = []

    env_block = re.search(r"env:\n((?:\s+- .+\n)+)", front + "\n")
    required = re.findall(r"- (\S+)", env_block.group(1)) if env_block else []
    primary = re.findall(r"primaryEnv:\s*(\S+)", front)
    for var in dict.fromkeys(required + primary):
        if not var.startswith("GSUITE_") or var not in _setting_names():
            problems.append(f"frontmatter env {var} is not a GSUITE_ setting")

    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    extras = set(pyproject["project"]["optional-dependencies"])
    for package in re.findall(r"package:\s*\"?([^\s\"]+)", front):
        name, _, extra_list = package.partition("[")
        if name != pyproject["project"]["name"]:
            problems.append(f"install package {name} is not {pyproject['project']['name']}")
        wanted = set(filter(None, extra_list.rstrip("]").split(",")))
        if unknown := wanted - extras:
            problems.append(f"install extras {sorted(unknown)} don't exist")
        if "gsuite" in front and not wanted & {"cli", "all"}:
            problems.append("the gsuite binary needs the [cli] (or [all]) extra")
    assert not problems, "\n".join(problems)


@pytest.mark.parametrize("doc", DOCS, ids=lambda p: str(p.relative_to(SKILL_DIR)))
def test_env_vars_are_settings(doc):
    unknown = sorted(set(ENV_VAR.findall(doc.read_text(encoding="utf-8"))) - _setting_names())
    assert not unknown, f"not GSUITE_ settings: {unknown}"


@pytest.mark.parametrize("doc", DOCS, ids=lambda p: str(p.relative_to(SKILL_DIR)))
def test_python_snippets(doc):
    checker = SnippetChecker(str(doc.relative_to(ROOT)), dict(_conventional_types()))
    for start, block in _located_blocks(doc.read_text(encoding="utf-8"), "python", "py"):
        checker.offset = start
        try:
            tree = ast.parse(block)
        except SyntaxError as exc:
            checker.problems.append(f"{checker.where}:{start}: syntax error: {exc}")
            continue
        for statement in tree.body:
            checker.visit(statement)
    assert not checker.problems, "\n".join(checker.problems)


def _command_lines(text: str) -> list[str]:
    lines = []
    for block in _code_blocks(text, "bash", "sh", "shell", "console", ""):
        for raw in block.splitlines():
            line = raw.strip().lstrip("$!").strip()
            line = re.sub(r"^(?:[A-Z_][A-Z0-9_]*=\S+\s+)+", "", line)  # leading VAR=value
            if line.startswith("gsuite "):
                lines.append(line.split(" #")[0].split(" |")[0].strip())
    return lines


@pytest.mark.parametrize("doc", DOCS, ids=lambda p: str(p.relative_to(SKILL_DIR)))
def test_cli_commands(doc, cli):
    problems = []
    for line in _command_lines(doc.read_text(encoding="utf-8")):
        tokens = shlex.split(line)[1:]
        command = cli
        path = ["gsuite"]
        while tokens and hasattr(command, "commands") and not tokens[0].startswith("-"):
            sub = command.commands.get(tokens[0])
            if sub is None:
                problems.append(f"{line}: unknown command {' '.join(path)} {tokens[0]}")
                break
            command, path = sub, [*path, tokens.pop(0)]
        else:
            options = {"--help"}
            for param in command.params:
                options.update(getattr(param, "opts", []))
                options.update(getattr(param, "secondary_opts", []))
            for token in tokens:
                if token.startswith("-") and token.split("=")[0] not in options:
                    problems.append(f"{line}: {' '.join(path)} has no option {token}")
    assert not problems, "\n".join(problems)
