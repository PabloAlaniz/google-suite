"""The agent skill (skills/gsuite-sdk) must match the SDK and CLI it documents.

Agents run the skill's snippets as written, so a renamed method or flag breaks
them silently. agent-skill-check runs the Agent Skills spec validator and
checks every Python call, CLI command and option, GSUITE_* variable and the
OpenClaw install line against the code.
"""

import tomllib
from pathlib import Path

import pytest
from typer.main import get_command

from gsuite_calendar import Calendar, CalendarEntity, Event
from gsuite_cli.main import app
from gsuite_contacts import Contact, Contacts
from gsuite_core import GoogleAuth, Settings
from gsuite_drive import Drive, File
from gsuite_gmail import Draft, Gmail, Label, Message, Thread
from gsuite_sheets import Sheets, Spreadsheet, Worksheet
from gsuite_tasks import Task, TaskList, Tasks

# Installed with `uv sync --group skill`; the lowest-deps job (pip extras only) skips it
agent_skill_check = pytest.importorskip("agent_skill_check")

ROOT = Path(__file__).resolve().parents[2]


def _env_names() -> set[str]:
    names = set()
    for name, field in Settings.model_fields.items():
        names.add(f"GSUITE_{name.upper()}")
        for alias in getattr(field.validation_alias, "choices", None) or []:
            if isinstance(alias, str) and alias.isupper():
                names.add(alias)
    return names


CHECK = agent_skill_check.SkillCheck(
    ROOT / "skills" / "gsuite-sdk",
    # Variable names the skill uses for SDK objects without constructing them
    types={
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
    },
    cli=get_command(app),
    prog="gsuite",
    env_prefix="GSUITE_",
    env_names=_env_names(),
    package="gsuite-sdk",
    extras=set(
        tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"][
            "optional-dependencies"
        ]
    ),
    cli_extras={"cli", "all"},
)


@pytest.mark.parametrize("name", agent_skill_check.SkillCheck.CHECKS)
def test_skill(name):
    problems = CHECK.run(name)
    assert not problems, "\n".join(problems)
