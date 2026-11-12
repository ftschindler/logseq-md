"""`append-child`, `--record-as` and `--create`, on a copy of a fixture graph.

`tests/fixtures/insertion/graph/` carries what DESIGN.md section 9 lists for
insertion: files with and without a final newline, CRLF, a parent with
properties, a logbook, existing children and a following sibling, and tab-,
space- and mixed-indented files, including children extended by two spaces under
a tab prefix, the variant the survey found beside tabs. Every assertion is on bytes.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from logseq_md import identity
from logseq_md.cli import main
from logseq_md.exits import BAD_ARGUMENTS, NOT_FOUND, OK, RECORD_GONE

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "insertion" / "graph"
ID = "5b30c2d4-0000-4e6f-8a70-0000000000{}"
MINTED = "6a5f0000-1111-4222-8333-555555555555"


@pytest.fixture
def graph(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    copy = tmp_path / "graph"
    shutil.copytree(FIXTURE, copy)
    monkeypatch.setattr(identity, "mint", lambda: MINTED)
    return copy


def run(capsys: pytest.CaptureFixture[str], graph: Path, *argv: str) -> tuple[int, str, str]:
    code = main([argv[0], "--graph", str(graph), *argv[1:]])
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def page(graph: Path, name: str) -> bytes:
    return (graph / "pages" / f"{name}.md").read_bytes()


def unchanged(graph: Path) -> bool:
    copied = sorted(path.relative_to(graph) for path in graph.rglob("*") if path.is_file())
    original = sorted(path.relative_to(FIXTURE) for path in FIXTURE.rglob("*") if path.is_file())
    return copied == original and all((graph / path).read_bytes() == (FIXTURE / path).read_bytes() for path in original)


@pytest.mark.parametrize(
    "case",
    [
        # After the properties, the logbook and the whole subtree, before the next sibling.
        (
            "Bench Notes",
            "01",
            b"\t- honed a micro bevel\n- oiling",
            b"\t- honed a micro bevel\n\t- new note\n- oiling",
        ),
        # No children: after the logbook, extending the prefix as the file does at that depth.
        ("Bench Notes", "02", b"\t:END:\n- a bare block", b"\t:END:\n\t- new note\n- a bare block"),
        # The last line of a file with a final newline.
        ("Bench Notes", "04", b"\tid:: " + ID.format("04").encode() + b"\n", None),
        # Space-indented, no final newline: two spaces, read from the other top-level block.
        ("Garden Plan", "13", b"  id:: " + ID.format("13").encode(), None),
        # CRLF, no final newline: two spaces under a tab, as the sibling block's children have.
        ("Pantry", "22", b"\t  id:: " + ID.format("22").encode(), None),
        # No evidence at the depth: the prefix extended by its trailing run of spaces.
        ("Workshop", "31", b"\t    id:: " + ID.format("31").encode() + b"\n", None),
        # Blank lines belong to the block above them, so the child goes after them.
        ("Review", "44", b"\n\n- the sibling", b"\n\n  - new note\n- the sibling"),
    ],
)
def test_append_child(
    capsys: pytest.CaptureFixture[str], graph: Path, case: tuple[str, str, bytes, bytes | None]
) -> None:
    name, block, old, new = case
    expected = {
        "04": old + b"\t- new note\n",
        "13": old + b"\n  - new note",
        "22": old + b"\r\n\t\t  - new note",
        "31": old + b"\t    - new note\n",
    }
    before = page(graph, name)
    assert before.count(old) == 1
    assert run(capsys, graph, "append-child", ID.format(block), "--text", "new note")[:2] == (OK, "")
    assert page(graph, name) == before.replace(old, new if new is not None else expected[block])


def test_multi_line_text_is_one_block_with_wrapped_lines(capsys: pytest.CaptureFixture[str], graph: Path) -> None:
    before = page(graph, "Garden Plan")
    assert run(capsys, graph, "append-child", ID.format("11"), "--text", "garlic too\nin the autumn")[0] == OK
    assert page(graph, "Garden Plan") == before.replace(
        b"compost was\n", b"compost was\n  - garlic too\n    in the autumn\n"
    )


def test_a_page_target_appends_a_top_level_block(capsys: pytest.CaptureFixture[str], graph: Path) -> None:
    before = page(graph, "Garden Plan")
    assert run(capsys, graph, "append-child", "Garden Plan", "--text", "order seeds")[0] == OK
    assert page(graph, "Garden Plan") == before + b"\n- order seeds"


def test_a_journal_date_appends_after_its_trailing_blank_line(capsys: pytest.CaptureFixture[str], graph: Path) -> None:
    path = graph / "journals" / "2032_05_03.md"
    before = path.read_bytes()
    assert run(capsys, graph, "append-child", "2032-05-03", "--text", "watered them")[0] == OK
    assert path.read_bytes() == before + b"- watered them\n"


def test_a_blank_page_gets_its_first_block(capsys: pytest.CaptureFixture[str], graph: Path) -> None:
    assert run(capsys, graph, "append-child", "Empty", "--text", "a start")[0] == OK
    assert page(graph, "Empty") == b"\n\n- a start\n"


def test_create_makes_a_missing_journal(capsys: pytest.CaptureFixture[str], graph: Path) -> None:
    path = graph / "journals" / "2032_05_04.md"
    assert run(capsys, graph, "append-child", "2032-05-04", "--text", "new day")[0] == NOT_FOUND
    assert not path.exists()
    assert run(capsys, graph, "append-child", "2032-05-04", "--create", "--text", "new day")[0] == OK
    assert path.read_bytes() == b"- new day"
    assert sorted(p.name for p in path.parent.iterdir()) == ["2032_05_03.md", "2032_05_04.md"]
    assert run(capsys, graph, "append-child", "2032-05-04", "--create", "--text", "later")[0] == OK
    assert path.read_bytes() == b"- new day\n- later"


def test_create_dry_run_prints_the_new_file_and_writes_nothing(capsys: pytest.CaptureFixture[str], graph: Path) -> None:
    code, out, _ = run(capsys, graph, "append-child", "--dry-run", "2032-05-04", "--create", "--text", "new day")
    assert code == OK
    assert "+- new day" in out.splitlines()
    assert unchanged(graph)


def test_record_as_appends_records_then_updates(capsys: pytest.CaptureFixture[str], graph: Path) -> None:
    before = page(graph, "Bench Notes")
    code, out, _ = run(capsys, graph, "append-child", ID.format("02"), "--text", "first pass", "--record-as", "my-note")
    assert (code, out) == (OK, MINTED + "\n")
    once = before.replace(
        b"\tid:: " + ID.format("02").encode() + b"\n",
        b"\tid:: " + ID.format("02").encode() + b"\n\tmy-note:: " + MINTED.encode() + b"\n",
    ).replace(b"\t:END:\n- a bare", b"\t:END:\n\t- first pass\n\t  id:: " + MINTED.encode() + b"\n- a bare")
    assert page(graph, "Bench Notes") == once
    code, out, _ = run(
        capsys, graph, "append-child", ID.format("02"), "--text", "second pass", "--record-as", "my-note"
    )
    assert (code, out) == (OK, MINTED + "\n")
    assert page(graph, "Bench Notes") == once.replace(b"first pass", b"second pass")
    assert page(graph, "Bench Notes").count(b"pass") == 1


def test_record_as_on_a_childless_block_puts_the_property_before_the_child(
    capsys: pytest.CaptureFixture[str], graph: Path
) -> None:
    before = page(graph, "Garden Plan")
    assert run(capsys, graph, "append-child", ID.format("13"), "--text", "mint", "--record-as", "k")[0] == OK
    assert page(graph, "Garden Plan") == before + (
        b"\n  k:: " + MINTED.encode() + b"\n  - mint\n    id:: " + MINTED.encode()
    )


def test_record_as_updates_an_existing_note(capsys: pytest.CaptureFixture[str], graph: Path) -> None:
    before = page(graph, "Review")
    code, out, _ = run(
        capsys, graph, "append-child", ID.format("41"), "--text", "cleared both", "--record-as", "status-note"
    )
    assert (code, out) == (OK, ID.format("42") + "\n")
    assert page(graph, "Review") == before.replace(b"cleared the left corner", b"cleared both")


def test_record_as_refuses_when_the_recorded_block_is_gone(capsys: pytest.CaptureFixture[str], graph: Path) -> None:
    code, _, err = run(capsys, graph, "append-child", ID.format("43"), "--text", "x", "--record-as", "status-note")
    assert code == RECORD_GONE
    assert ID.format("49") in err
    assert unchanged(graph)


def test_deleting_the_note_by_hand_then_running_again_is_exit_4(
    capsys: pytest.CaptureFixture[str], graph: Path
) -> None:
    assert run(capsys, graph, "append-child", ID.format("03"), "--text", "a note", "--record-as", "k")[0] == OK
    path = graph / "pages" / "Bench Notes.md"
    path.write_bytes(path.read_bytes().replace(b"\t- a note\n\t  id:: " + MINTED.encode() + b"\n", b""))
    edited = path.read_bytes()
    code, _, err = run(capsys, graph, "append-child", ID.format("03"), "--text", "again", "--record-as", "k")
    assert code == RECORD_GONE
    assert MINTED in err
    assert path.read_bytes() == edited


@pytest.mark.parametrize(
    ("argv", "code", "says"),
    [
        (("Reading List", "--text", "x"), BAD_ARGUMENTS, "has no outline"),
        (("Bench Notes:1", "--text", "x"), BAD_ARGUMENTS, "ensure-id"),
        (("Garden Plan", "--text", "x", "--record-as", "k"), BAD_ARGUMENTS, "records on a block"),
        (("Garden Plan", "--create", "--text", "x"), BAD_ARGUMENTS, "takes a date"),
        ((ID.format("01"), "--text", "x", "--record-as", "id"), BAD_ARGUMENTS, "ensure-id"),
        ((ID.format("01"), "--text", "x", "--record-as", "two words"), BAD_ARGUMENTS, "not a property key"),
        ((ID.format("01"), "--text", "fine\n- a second block"), BAD_ARGUMENTS, "change the outline"),
        ((ID.format("01"), "--text", "```open fence"), BAD_ARGUMENTS, "change the outline"),
        ((ID.format("99"), "--text", "x"), NOT_FOUND, "no block carries this id"),
    ],
)
def test_refusals(capsys: pytest.CaptureFixture[str], graph: Path, argv: tuple[str, ...], code: int, says: str) -> None:
    got, _, err = run(capsys, graph, "append-child", *argv)
    assert got == code
    assert says in err
    assert unchanged(graph)
