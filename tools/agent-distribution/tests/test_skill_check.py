"""SkillCheck against a tiny library, its Click and argparse CLIs, and a demo skill."""

import shutil
from pathlib import Path

import demo_lib
import pytest

from agent_skill_check import SkillCheck

FIXTURE = Path(__file__).parent / "fixtures" / "skills" / "demo"


def make_check(skill_dir: Path, cli=None) -> SkillCheck:
    return SkillCheck(
        skill_dir,
        types={"sheet": demo_lib.Sheet, "client": demo_lib.Client},
        cli=demo_lib.cli if cli is None else cli,
        prog="demo",
        env_prefix="DEMO_",
        env_names=demo_lib.SETTINGS,
        package="demo-lib",
        extras={"cli", "all"},
        cli_extras={"cli", "all"},
    )


@pytest.fixture
def skill(tmp_path) -> Path:
    target = tmp_path / "demo"
    shutil.copytree(FIXTURE, target)
    return target


def mutate(skill: Path, old: str, new: str, file: str = "SKILL.md") -> None:
    path = skill / file
    text = path.read_text()
    assert old in text, old
    path.write_text(text.replace(old, new))


@pytest.mark.parametrize("name", SkillCheck.CHECKS)
def test_valid_skill_passes(name):
    assert make_check(FIXTURE).run(name) == []


def test_unknown_check():
    with pytest.raises(ValueError):
        make_check(FIXTURE).run("nope")


@pytest.mark.parametrize(
    ("old", "new", "check", "expected"),
    [
        ("sheet.update(", "sheet.updat(", "python", "Sheet has no attribute 'updat'"),
        ("notify=True)", "notify=True, cc=1)", "python", "no keyword argument 'cc'"),
        ('[["x"]]', '"x"', "python", "values takes a list"),
        ('open_by_key("abc")', 'open("SHEET_ID")', "python", "ID placeholder"),
        ("row.label", "row.labl", "python", "Row has no attribute 'labl'"),
        ("from demo_lib import Client", "from demo_lib import Klient", "python", "no Klient"),
        ("--range A1:B2", "--rango A1:B2", "commands", "has no option --rango"),
        ("demo rows add", "demo rows remove", "commands", "unknown command demo rows remove"),
        ("--no-notify", "--quiet", "commands", "has no option --quiet"),
        ("        - DEMO_TOKEN", "        - TOKEN", "frontmatter", "doesn't start with DEMO_"),
        ("        - DEMO_TOKEN", "        - DEMO_SECRET", "frontmatter", "not a known setting"),
        ('"demo-lib[cli]"', "demo-lib", "frontmatter", "needs one of the extras"),
        ('"demo-lib[cli]"', '"demo-lib[gui]"', "frontmatter", "['gui'] don't exist"),
        ("optionally `DEMO_TIMEOUT`", "optionally `DEMO_TIMEOUTS`", "env_vars", "DEMO_TIMEOUTS"),
        ("name: demo\n", "name: Demo\n", "spec", "demo"),
    ],
)
def test_mutations_are_caught(skill, old, new, check, expected):
    mutate(skill, old, new)
    problems = make_check(skill).run(check)
    assert any(expected in p for p in problems), problems


def test_reference_files_share_variables_and_report_their_lines(skill):
    mutate(skill, 'sheet.get("A1:B2")', 'sheet.gett("A1:B2")', "references/more.md")
    (problem,) = make_check(skill).run("python")
    assert problem.startswith("demo/references/more.md:4:")


def test_argparse_cli(skill):
    parser = demo_lib.parser()
    check = make_check(skill, cli=parser)
    mutate(skill, "demo rows add --name Ana --no-notify\n", "demo read K --json\n")
    assert check.run("commands") == []
    mutate(skill, "demo read K --json", "demo read K --xml")
    assert any("has no option --xml" in p for p in check.run("commands"))


def test_shell_lines_ignore_prompts_env_and_pipes(skill):
    line = "$ DEMO_TOKEN=x demo read K -o json | jq .  # c"
    mutate(skill, "demo rows add --name Ana --no-notify", line)
    assert make_check(skill).run("commands") == []
