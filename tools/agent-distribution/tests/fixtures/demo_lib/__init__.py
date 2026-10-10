"""A tiny library the test skill documents."""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field

import click


@dataclass
class Row:
    name: str
    tags: list[str] = field(default_factory=list)

    @property
    def label(self) -> str:
        return self.name.upper()


class Sheet:
    def get(self, range: str = "A1") -> list[list[str]]:
        return [[range]]

    def update(self, range: str, values: list[list[str]]) -> None:
        pass

    def rows(self) -> list[Row]:
        return [Row("a")]


class Client:
    def __init__(self, token: str | None = None) -> None:
        self.token = token

    def open(self, title: str) -> Sheet:
        return Sheet()

    def open_by_key(self, key: str) -> Sheet:
        return Sheet()

    def find(self, name: str) -> Row | None:
        return None

    def send(self, to: list[str], subject: str, notify: bool = False) -> bool:
        return True


@click.group()
def cli() -> None:
    """demo CLI."""


@cli.command("read")
@click.argument("key")
@click.option("--range", "-r", default="A1")
@click.option("--output", "-o", default="table")
def read(key: str, range: str, output: str) -> None:
    pass


@cli.group("rows")
def rows() -> None:
    pass


@rows.command("add")
@click.option("--name", required=True)
@click.option("--notify/--no-notify", default=False)
def add(name: str, notify: bool) -> None:
    pass


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="demo")
    sub = p.add_subparsers(dest="cmd")
    r = sub.add_parser("read")
    r.add_argument("key")
    r.add_argument("--range", "-r")
    r.add_argument("--json", action="store_true")
    r.add_argument("--output", "-o")
    rows = sub.add_parser("rows").add_subparsers(dest="rows_cmd")
    add = rows.add_parser("add")
    add.add_argument("--name")
    add.add_argument("--notify", action="store_true")
    add.add_argument("--no-notify", action="store_false", dest="notify")
    return p


SETTINGS = {"DEMO_TOKEN", "DEMO_TIMEOUT"}
