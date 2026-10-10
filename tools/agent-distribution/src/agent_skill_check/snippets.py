"""Check the Python blocks of a skill against the library they document.

Types are inferred from imports, constructors, return annotations, loop and
`with` targets, and a map of conventional variable names (``gmail -> Gmail``)
for objects the skill uses without building them in the same block.
"""

from __future__ import annotations

import ast
import importlib
import inspect
import re
import types
import typing

ID_PLACEHOLDER = re.compile(r"^[A-Z][A-Z0-9_]*_ID$")


def unwrap(hint: typing.Any) -> type | None:
    """X | None -> X; list[X] / Iterator[X] -> X; a class -> itself."""
    origin = typing.get_origin(hint)
    if origin in (typing.Union, types.UnionType):
        classes = [unwrap(a) for a in typing.get_args(hint) if a is not type(None)]
        classes = [c for c in classes if c is not None]
        return classes[0] if len(classes) == 1 else None
    if origin is not None:
        args = typing.get_args(hint)
        container = getattr(origin, "__name__", "")
        if origin in (list, tuple, set) or container in (
            "Iterator",
            "Iterable",
            "Sequence",
            "AsyncIterator",
        ):
            return unwrap(args[0]) if args else None
        return None
    return hint if inspect.isclass(hint) else None


def return_type(cls: type, method: str) -> type | None:
    member = inspect.getattr_static(cls, method, None)
    func = member.fget if isinstance(member, property) else getattr(cls, method, None)
    if func is None:
        return None
    try:
        hints = typing.get_type_hints(func)
    except Exception:  # unresolvable forward references: give up on this value
        return None
    return unwrap(hints.get("return"))


def has_member(cls: type, name: str) -> bool:
    if hasattr(cls, name):
        return True
    return any(name in inspect.get_annotations(klass) for klass in cls.__mro__)


class SnippetChecker(ast.NodeVisitor):
    """Walks the Python blocks of one file, sharing variables between blocks."""

    def __init__(self, where: str, env: dict[str, type]) -> None:
        self.where = where
        self.env = dict(env)
        self.offset = 1
        self.problems: list[str] = []

    def check_block(self, code: str, first_line: int) -> None:
        self.offset = first_line
        try:
            tree = ast.parse(code)
        except SyntaxError as exc:
            self.problems.append(f"{self.where}:{first_line}: syntax error: {exc}")
            return
        for statement in tree.body:
            self.visit(statement)

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

    def visit_For(self, node: ast.For | ast.AsyncFor) -> None:
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

    def visit_With(self, node: ast.With | ast.AsyncWith) -> None:
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
                if owner is not None and has_member(owner, node.func.attr):
                    if isinstance(inspect.getattr_static(owner, node.func.attr, None), classmethod):
                        return return_type(owner, node.func.attr) or owner
                    return return_type(owner, node.func.attr)
        if isinstance(node, ast.Attribute):
            owner = self.type_of(node.value)
            member = owner and inspect.getattr_static(owner, node.attr, None)
            if isinstance(member, property):
                return return_type(owner, node.attr)
        return None

    # uses
    def visit_Attribute(self, node: ast.Attribute) -> None:
        owner = self.type_of(node.value)
        if owner is not None and not has_member(owner, node.attr):
            self.problem(node, f"{owner.__name__} has no attribute {node.attr!r}")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        self.generic_visit(node)
        if isinstance(node.func, ast.Attribute):
            owner = self.type_of(node.func.value)
            if owner is None or not has_member(owner, node.func.attr):
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
