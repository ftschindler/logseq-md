"""The fixture tooling: the survey, the leak check and the offline evidence check.

Each runs here against a small synthetic graph built in `tmp_path`, never a real
one. Loaded by path, because their file names are commands rather than modules.
"""

from __future__ import annotations

import ast
import importlib.util
import json
import shutil
from pathlib import Path
from types import ModuleType

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / ".scripts"


def load(name: str) -> ModuleType:
    path = SCRIPTS / name
    spec = importlib.util.spec_from_file_location(path.stem, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


survey_graph = load("survey_graph.py")
check_fixture_leaks = load("check_fixture_leaks.py")
check_fixture_evidence = load("check_fixture_evidence.py")


def write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as handle:
        handle.write(data)


@pytest.fixture
def graph(tmp_path: Path) -> Path:
    root = tmp_path / "graph"
    write(
        root / "logseq" / "config.edn", b'{:file/name-format :triple-lowbar\n :journal/file-name-format "yyyy_MM_dd"}\n'
    )
    write(
        root / "journals" / "2024_01_02.md",
        b"- TODO water the ferns #garden\n"
        b"\t- DONE buy compost\n"
        b"\t  id:: 65a1b2c3-0000-4000-8000-000000000001\n"
        b"\t  secret-key:: [[Somewhere]]\n"
        b"\t  :LOGBOOK:\n"
        b"\t  CLOCK: [2024-01-02 Tue 10:00:00]--[2024-01-02 Tue 10:05:00] =>  00:05:00\n"
        b"\t  :END:\n"
        b"\t\t  - see ((65a1b2c3-0000-4000-8000-000000000001))\n"
        b"\t- ((65a1b2c3-0000-4000-8000-0000000000ff))",
    )
    write(root / "pages" / "Kitchen___Knives.md", b"- ```\r\n  - not a bullet\r\n  ```\r\n")
    write(root / "pages" / "prose.md", b"title:: Prose\n")
    write(root / "pages" / "empty.md", b"")
    write(root / "logseq" / "bak" / "pages" / "old.md", b"- a line the owner wrote once\n")
    return root


class TestSurvey:
    def test_counts_constructs(self, graph: Path) -> None:
        counts = survey_graph.survey(graph).counts
        assert counts["files"] == 4
        assert counts["files empty"] == 1
        assert counts["files without a final newline"] == 1
        assert counts["files with b'\\r\\n' endings"] == 1
        assert counts["marker TODO"] == 1
        assert counts["marker DONE"] == 1
        assert counts["code fences `"] == 1
        assert counts["fenced lines that look like bullets"] == 1
        assert counts["namespaced filenames (___)"] == 1
        assert counts["pages with no bullets: page properties only"] == 1
        assert counts["#tags"] == 1
        assert counts["dangling ((uuid)) targets"] == 1
        assert counts["round-trip byte-identical"] == 4
        assert counts["lines with a mixed tab/space prefix"] >= 1

    def test_reads_config_and_skips_bak(self, graph: Path) -> None:
        result = survey_graph.survey(graph)
        assert result.name_format == ":triple-lowbar"
        assert result.counts["files in logseq/"] == 0

    def test_never_prints_a_custom_key_or_text(self, graph: Path) -> None:
        printed = survey_graph.report(survey_graph.survey(graph))
        assert "secret-key" not in printed
        assert "custom-1" in printed
        assert "ferns" not in printed
        assert "Knives" not in printed

    def test_the_name_check_maps_filenames_back(self, graph: Path) -> None:
        names = survey_graph.survey(graph).names
        assert names["page filenames that map back"] == 3
        assert names["journal filenames that map back"] == 1
        assert names["page filenames with a ___ namespace separator"] == 1

    def test_a_name_check_failure_is_reported_as_a_shape(self, graph: Path) -> None:
        write(graph / "journals" / "Field Notes 7.md", b"- an entry\n")
        result = survey_graph.survey(graph)
        assert result.names["journal filenames that do not"] == 1
        assert result.name_failures == {"journal: a a 9": 1}
        assert "Field" not in survey_graph.report(result)

    def test_the_id_scan_counts_ids_and_duplicates(self, graph: Path) -> None:
        write(graph / "pages" / "copy.md", b"- a copy\n  id:: 65a1b2c3-0000-4000-8000-000000000001\n")
        scan = survey_graph.survey(graph).id_scan
        assert (scan["distinct ids"], scan["ids on more than one block"]) == (1, 1)
        assert float(str(scan["seconds"])) >= 0

    def test_the_write_check_plans_every_write_and_writes_nothing(self, graph: Path) -> None:
        before = {path: path.read_bytes() for path in graph.rglob("*") if path.is_file()}
        checked = survey_graph.survey(graph).write_check
        assert checked["set-property: only its own lines"] > 0
        assert checked["set-marker: refused"] == 1  # the bullet that opens a fence
        assert not [key for key in checked if "OTHER BYTES" in key]
        assert {path: path.read_bytes() for path in graph.rglob("*") if path.is_file()} == before

    def test_the_indentation_report_counts_each_extension_by_shape(self, graph: Path) -> None:
        assert survey_graph.survey(graph).indentation == {"extended by TAB": 1, "extended by TAB SP SP": 1}

    def test_the_append_check_plans_every_append_and_writes_nothing(self, graph: Path) -> None:
        before = {path: path.read_bytes() for path in graph.rglob("*") if path.is_file()}
        checked = survey_graph.survey(graph).append_check
        assert checked["append-child: only inserted lines"] > 0
        assert checked["--record-as: prefix matches the siblings'"] > 0
        assert not [key for key in checked if "OTHER BYTES" in key or "DIFFERS" in key]
        assert {path: path.read_bytes() for path in graph.rglob("*") if path.is_file()} == before

    def test_logbook_and_prefixes_are_shapes(self, graph: Path) -> None:
        result = survey_graph.survey(graph)
        assert result.clock_per_logbook == {1: 1}
        assert result.prefixes["TAB TAB SP SP"] == 1

    def test_the_block_model_agrees_with_the_survey(self, graph: Path) -> None:
        rows = dict(survey_graph.survey(graph).compare())
        assert rows["bullets"] == "5 == 5"
        assert rows["wrapped content lines (after the content span)"] == "0 == 0"
        assert {key: row for key, row in rows.items() if " == " not in row} == {}

    def test_a_disagreement_is_reported(self, graph: Path) -> None:
        result = survey_graph.survey(graph)
        result.parser["bullets"] += 1
        assert dict(result.compare())["bullets"] == "5 != 6"


class TestLeakCheck:
    @pytest.fixture
    def repo(self, tmp_path: Path) -> Path:
        root = tmp_path / "repo"
        write(
            root / "tests" / "fixtures" / "topic" / "a.md",
            b"- an invented line\n\t- \n\t  id:: x\n```\n- ```\n\t  :LOGBOOK:\n:END:\n---\n",
        )
        (root / ".scripts").mkdir(parents=True)
        shutil.copy(SCRIPTS / "check_fixture_leaks.py", root / ".scripts" / "check_fixture_leaks.py")
        return root

    def test_passes_on_structure_only_overlap(self, graph: Path, repo: Path) -> None:
        assert check_fixture_leaks.check(graph, repo) == 0

    def test_catches_a_planted_line_at_any_depth(
        self, graph: Path, repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        write(repo / "tests" / "fixtures" / "topic" / "b.md", b"\t\t- TODO water the ferns #garden\n")
        assert check_fixture_leaks.check(graph, repo) == 1
        err = capsys.readouterr().err
        assert "tests/fixtures/topic/b.md:1" in err
        assert "ferns" not in err

    def test_records_evidence_without_graph_detail(self, graph: Path, repo: Path) -> None:
        assert check_fixture_leaks.check(graph, repo, record=True) == 0
        evidence = json.loads((repo / "tests" / "evidence" / "fixtures-topic.json").read_text(encoding="utf-8"))
        assert evidence["outcome"] == "pass"
        assert evidence["graph_files_scanned"] == 5
        assert [entry["path"] for entry in evidence["files"]] == ["tests/fixtures/topic/a.md"]
        assert str(graph) not in json.dumps(evidence)


class TestEvidenceCheck:
    @pytest.fixture
    def recorded(self, graph: Path, tmp_path: Path) -> Path:
        root = tmp_path / "repo"
        write(root / "tests" / "fixtures" / "topic" / "a.md", b"- an invented line\n")
        (root / ".scripts").mkdir(parents=True)
        shutil.copy(SCRIPTS / "check_fixture_leaks.py", root / ".scripts" / "check_fixture_leaks.py")
        leaks = load_copy(root / ".scripts" / "check_fixture_leaks.py")
        assert leaks.check(graph, root, record=True) == 0
        return root

    def test_green_when_the_evidence_describes_the_fixtures(self, recorded: Path) -> None:
        assert check_fixture_evidence.check_all(recorded) == []

    def test_red_when_evidence_is_missing(self, recorded: Path) -> None:
        write(recorded / "tests" / "fixtures" / "other" / "c.md", b"- x\n")
        assert any("no evidence" in problem for problem in check_fixture_evidence.check_all(recorded))

    def test_red_when_a_fixture_changed(self, recorded: Path) -> None:
        write(recorded / "tests" / "fixtures" / "topic" / "a.md", b"- edited\n")
        assert any("changed since" in problem for problem in check_fixture_evidence.check_all(recorded))

    def test_red_when_the_leak_script_changed(self, recorded: Path) -> None:
        script = recorded / ".scripts" / "check_fixture_leaks.py"
        write(script, script.read_bytes() + b"\n# edited\n")
        assert any(
            "check_fixture_leaks.py changed" in problem for problem in check_fixture_evidence.check_all(recorded)
        )

    def test_red_when_the_file_set_differs(self, recorded: Path) -> None:
        write(recorded / "tests" / "fixtures" / "topic" / "new.md", b"- x\n")
        assert any("not covered" in problem for problem in check_fixture_evidence.check_all(recorded))

    def test_red_when_the_outcome_is_not_pass(self, recorded: Path) -> None:
        path = recorded / "tests" / "evidence" / "fixtures-topic.json"
        evidence = json.loads(path.read_text(encoding="utf-8"))
        evidence["outcome"] = "fail"
        path.write_text(json.dumps(evidence), encoding="utf-8")
        assert any("not 'pass'" in problem for problem in check_fixture_evidence.check_all(recorded))

    def test_the_repository_itself_is_green(self) -> None:
        assert check_fixture_evidence.check_all() == []


def load_copy(path: Path) -> ModuleType:
    """A copy of the leak script, so the hash it records is of the copy it runs from."""
    spec = importlib.util.spec_from_file_location("leaks_copy", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


WRITE_CALLS = {
    "write",
    "write_text",
    "write_bytes",
    "writelines",
    "mkdir",
    "unlink",
    "rename",
    "replace",
    "rmdir",
    "touch",
}


def graph_reading_offences(source: str, allowed: set[str]) -> list[str]:
    """Write calls, and opens not in "rb", outside the functions allowed to write."""
    tree = ast.parse(source)
    found: list[str] = []
    for function in ast.walk(tree):
        if not isinstance(function, ast.FunctionDef) or function.name in allowed:
            continue
        for node in ast.walk(function):
            if not isinstance(node, ast.Call):
                continue
            name = node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", "")
            if name in WRITE_CALLS and not (
                isinstance(node.func, ast.Attribute) and ast.unparse(node.func.value) == "sys.stdout"
            ):
                found.append(f"{function.name}:{node.lineno} {name}")
            if name == "open":
                modes = [arg for arg in node.args if isinstance(arg, ast.Constant)]
                if [m.value for m in modes] != ["rb"]:
                    found.append(f"{function.name}:{node.lineno} open without 'rb'")
    return found


@pytest.mark.parametrize(
    ("script", "allowed"),
    [("survey_graph.py", set()), ("check_fixture_leaks.py", {"write_evidence"})],
)
def test_graph_reading_code_contains_no_write_call(script: str, allowed: set[str]) -> None:
    assert graph_reading_offences((SCRIPTS / script).read_text(encoding="utf-8"), allowed) == []


def test_the_write_check_catches_a_write() -> None:
    planted = "def f(p):\n    p.open('wb')\n    p.write_bytes(b'')\n    open(p)\n"
    assert graph_reading_offences(planted, set()) == [
        "f:2 open without 'rb'",
        "f:3 write_bytes",
        "f:4 open without 'rb'",
    ]
