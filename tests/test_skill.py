"""The skill in `skills/logseq-md/`: its version, its examples and its evidence guard.

The examples are what a model copies, so each one runs here against a copy of
`tests/fixtures/writes/graph/`, whose ids they name. The evidence guard is
`.scripts/check_evidence.py`, loaded by path and pointed at crafted trees.
"""

from __future__ import annotations

import importlib.util
import json
import re
import shlex
import shutil
from pathlib import Path
from types import ModuleType

import pytest

from logseq_md.cli import main
from logseq_md.exits import OK

REPO_ROOT = Path(__file__).resolve().parent.parent
SKILL = REPO_ROOT / "skills" / "logseq-md"
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "writes" / "graph"


def load(name: str) -> ModuleType:
    path = REPO_ROOT / ".scripts" / name
    spec = importlib.util.spec_from_file_location(path.stem, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


version = load("version.py")
evidence_check = load("check_evidence.py")


def test_the_skill_version_is_the_package_version() -> None:
    package = version.read_version((REPO_ROOT / "pyproject.toml").read_bytes().decode("utf-8"))
    assert (SKILL / "VERSION").read_bytes() == f"{package}\n".encode()


def examples() -> list[str]:
    """Every `uvx logseq-md` line inside a fenced block of SKILL.md."""
    text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    blocks = re.findall(r"^```sh\n(.*?)^```", text, flags=re.MULTILINE | re.DOTALL)
    return [line for block in blocks for line in block.splitlines() if line.startswith("uvx logseq-md ")]


def test_the_skill_has_examples() -> None:
    assert len(examples()) >= 5


@pytest.mark.parametrize("example", examples())
def test_every_example_in_the_skill_runs(
    example: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    graph = tmp_path / "graph"
    shutil.copytree(FIXTURE, graph)
    monkeypatch.setenv("LOGSEQ_MD_GRAPH", str(graph))
    code = main(shlex.split(example)[2:])
    assert code == OK, capsys.readouterr().err


# --- the evidence guard -------------------------------------------------


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def recorded(root: Path, *, outcome: str = "pass") -> list[Path]:
    """A skill with probes, and evidence covering both as they are now."""
    files = [
        write(root / "skills" / "notes" / "SKILL.md", "---\nname: notes\ndescription: Notes.\n---\n"),
        write(root / "tests" / "probes" / "notes.json", '{"probes": []}\n'),
    ]
    document = {
        "schema_version": evidence_check.SCHEMA_VERSION,
        "kit": "notes",
        "files": [{"path": p.relative_to(root).as_posix(), "sha256": evidence_check.sha256_of(p)} for p in files],
        "runs": [{"prompt": "...", "reply": "...", "assertions": []}],
        "outcome": outcome,
    }
    write(root / "tests" / "evidence" / "notes.json", json.dumps(document))
    return files


def test_matching_evidence_passes(tmp_path: Path) -> None:
    recorded(tmp_path)
    assert evidence_check.check_all(tmp_path) == []


def test_a_skill_without_evidence_is_caught(tmp_path: Path) -> None:
    write(tmp_path / "skills" / "notes" / "SKILL.md", "---\nname: notes\n---\n")
    assert any("no evidence" in problem for problem in evidence_check.check_all(tmp_path))


def test_a_skill_edited_after_recording_is_caught(tmp_path: Path) -> None:
    skill, _ = recorded(tmp_path)
    skill.write_text("---\nname: notes\ndescription: Changed.\n---\n", encoding="utf-8")
    assert any("has changed since" in problem for problem in evidence_check.check_all(tmp_path))


def test_probes_edited_after_recording_are_caught(tmp_path: Path) -> None:
    _, probes = recorded(tmp_path)
    probes.write_text('{"probes": [{"prompt": "new"}]}\n', encoding="utf-8")
    assert any("has changed since" in problem for problem in evidence_check.check_all(tmp_path))


def test_a_file_added_after_recording_is_caught(tmp_path: Path) -> None:
    recorded(tmp_path)
    write(tmp_path / "skills" / "notes" / "references.md", "# More\n")
    assert any("not covered by the evidence" in problem for problem in evidence_check.check_all(tmp_path))


def test_the_version_file_is_not_covered(tmp_path: Path) -> None:
    recorded(tmp_path)
    write(tmp_path / "skills" / "notes" / "VERSION", "0.2.0\n")
    assert evidence_check.check_all(tmp_path) == []


def test_a_recorded_failure_fails_the_check(tmp_path: Path) -> None:
    recorded(tmp_path, outcome="fail")
    assert any("recorded outcome is 'fail'" in problem for problem in evidence_check.check_all(tmp_path))
