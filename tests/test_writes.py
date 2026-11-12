"""The in-block writes, `ensure-id`, `set-property`, `set-content` and `set-marker`, on a copy of a fixture graph.

`tests/fixtures/writes/graph/` carries the variants the survey reported: property
lines at the conventional indent and at a deviant one, continuation lines in
non-canonical orders, wrapped content, tab, space and mixed prefixes, CRLF
endings, files with and without a final newline, and a page with no outline.
Every assertion here is on bytes.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

from logseq_md import identity, splice
from logseq_md.cli import main
from logseq_md.exits import BAD_ARGUMENTS, FILE_CHANGED, NOT_FOUND, OK

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "writes" / "graph"
ID = "7a20b1c3-0000-4d5e-8f60-0000000000{}"
MINTED = "6a5f0000-1111-4222-8333-444444444444"


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
    return all(
        (graph / path.relative_to(FIXTURE)).read_bytes() == path.read_bytes()
        for path in FIXTURE.rglob("*")
        if path.is_file()
    )


# ensure-id


def test_ensure_id_prints_an_existing_id_and_writes_nothing(capsys: pytest.CaptureFixture[str], graph: Path) -> None:
    assert run(capsys, graph, "ensure-id", ID.format("05").upper())[:2] == (OK, ID.format("05") + "\n")
    assert unchanged(graph)


def test_ensure_id_inserts_after_the_content_at_the_conventional_indent(
    capsys: pytest.CaptureFixture[str], graph: Path
) -> None:
    before = page(graph, "Kiln Log")
    assert run(capsys, graph, "ensure-id", "Kiln Log:33")[:2] == (OK, MINTED + "\n")
    assert page(graph, "Kiln Log") == before.replace(
        b"- a block with no id yet\n", b"- a block with no id yet\n  id:: " + MINTED.encode() + b"\n"
    )


def test_ensure_id_converges_across_a_person_editing_the_page(
    capsys: pytest.CaptureFixture[str], graph: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    code, first, _ = run(capsys, graph, "ensure-id", "Kiln Log:33")
    assert code == OK
    path = graph / "pages" / "Kiln Log.md"
    path.write_bytes(b"- a line the owner added on top\n" + path.read_bytes().replace(b"no id yet", b"no id, edited"))
    edited = path.read_bytes()
    monkeypatch.setattr(identity, "mint", lambda: pytest.fail("a second id was minted"))
    assert run(capsys, graph, "ensure-id", first.strip())[:2] == (OK, first)
    assert path.read_bytes() == edited


def test_a_write_refuses_when_the_file_changes_before_the_rename(
    capsys: pytest.CaptureFixture[str], graph: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = graph / "pages" / "Kiln Log.md"
    real = os.fsync

    def owner_saves(fd: int) -> None:
        real(fd)
        path.write_bytes(path.read_bytes() + b"\n- typed in the app meanwhile")

    monkeypatch.setattr(splice.os, "fsync", owner_saves)
    code, out, err = run(capsys, graph, "set-marker", ID.format("01"), "DONE")
    assert (code, out) == (FILE_CHANGED, "")
    assert "changed since it was read" in err
    assert path.read_bytes() == (FIXTURE / "pages" / "Kiln Log.md").read_bytes() + b"\n- typed in the app meanwhile"
    assert sorted(p.name for p in path.parent.iterdir()) == sorted(p.name for p in (FIXTURE / "pages").iterdir())


# set-property


@pytest.mark.parametrize(
    ("block", "old", "new"),
    [
        # A key already there changes in place.
        ("02", b"\t  glaze-batch:: seven\n", b"\t  glaze-batch:: eight\n"),
        # A new key follows the last property, at the block's deviant indent.
        ("03", b"\t    shelf-height:: low\n", b"\t    shelf-height:: low\n\t    glaze-batch:: eight\n"),
        # After a DEADLINE and an id, before the logbook: the last property, not the last line.
        (
            "05",
            b"  id:: " + ID.format("05").encode() + b"\n",
            b"  id:: " + ID.format("05").encode() + b"\n  glaze-batch:: eight\n",
        ),
    ],
)
def test_set_property(capsys: pytest.CaptureFixture[str], graph: Path, block: str, old: bytes, new: bytes) -> None:
    before = page(graph, "Kiln Log")
    assert run(capsys, graph, "set-property", ID.format(block), "glaze-batch", "eight")[0] == OK
    assert before.count(old) == 1
    assert page(graph, "Kiln Log") == before.replace(old, new)
    assert run(capsys, graph, "set-property", ID.format(block), "glaze-batch", "eight")[0] == OK
    assert page(graph, "Kiln Log") == before.replace(old, new)


def test_set_property_copies_the_first_property_indent_when_they_differ(
    capsys: pytest.CaptureFixture[str], graph: Path
) -> None:
    before = page(graph, "Kiln Log")
    assert run(capsys, graph, "set-property", ID.format("04"), "kiln-zone", "front")[0] == OK
    assert page(graph, "Kiln Log") == before.replace(b"\tkiln-zone:: rear", b"\tkiln-zone:: front")
    assert run(capsys, graph, "set-property", ID.format("04"), "fired", "")[0] == OK
    assert page(graph, "Kiln Log") == before.replace(b"\tkiln-zone:: rear", b"\tkiln-zone:: front\n\t  fired::")


def test_set_property_on_the_last_line_of_a_crlf_file_without_a_final_newline(
    capsys: pytest.CaptureFixture[str], graph: Path
) -> None:
    before = page(graph, "Dye Pot")
    assert run(capsys, graph, "set-property", ID.format("32"), "vat", "two")[0] == OK
    assert page(graph, "Dye Pot") == before + b"\r\n    vat:: two"


def test_set_property_refuses_id_and_multi_line_values(capsys: pytest.CaptureFixture[str], graph: Path) -> None:
    assert run(capsys, graph, "set-property", ID.format("02"), "id", MINTED)[0] == BAD_ARGUMENTS
    assert run(capsys, graph, "set-property", ID.format("02"), "note", "one\ntwo")[0] == BAD_ARGUMENTS
    assert run(capsys, graph, "set-property", ID.format("02"), "two words", "x")[0] == BAD_ARGUMENTS
    assert unchanged(graph)


def test_dry_run_prints_a_diff_and_writes_nothing(capsys: pytest.CaptureFixture[str], graph: Path) -> None:
    code, out, _ = run(capsys, graph, "set-property", "--dry-run", ID.format("12"), "heddle", "twelve")
    assert code == OK
    assert [line for line in out.splitlines() if line.startswith(("+", "-"))][2:] == ["+    heddle:: twelve"]
    assert out.splitlines()[0].endswith("Loom Notes.md")
    assert unchanged(graph)


# set-content


def test_set_content_replaces_the_wrapped_span_and_keeps_the_rest(
    capsys: pytest.CaptureFixture[str], graph: Path
) -> None:
    before = page(graph, "Loom Notes")
    assert run(capsys, graph, "set-content", ID.format("13"), "--text", "weft, revised\nwith one wrap")[0] == OK
    expected = before.replace(
        b"  - weft notes\n    a second wrapped line\n    and a third\n", b"  - weft, revised\n    with one wrap\n"
    )
    assert page(graph, "Loom Notes") == expected
    assert run(capsys, graph, "set-content", ID.format("13"), "--text", "weft, revised\nwith one wrap")[0] == OK
    assert page(graph, "Loom Notes") == expected


def test_set_content_on_a_one_line_span_wraps_at_the_conventional_indent(
    capsys: pytest.CaptureFixture[str], graph: Path
) -> None:
    before = page(graph, "Kiln Log")
    assert (
        run(capsys, graph, "set-content", ID.format("05"), "--text", "WAITING order kiln wash\nfrom the coast")[0] == OK
    )
    assert page(graph, "Kiln Log") == before.replace(
        b"- WAITING order more kiln wash\n", b"- WAITING order kiln wash\n  from the coast\n"
    )


@pytest.mark.parametrize("text", ["fine\n- now a sibling", "fine\nkey:: value", "```\nopen fence", "fine\n:LOGBOOK:"])
def test_set_content_refuses_text_that_would_restructure_the_page(
    capsys: pytest.CaptureFixture[str], graph: Path, text: str
) -> None:
    assert run(capsys, graph, "set-content", ID.format("13"), "--text", text)[0] == BAD_ARGUMENTS
    assert unchanged(graph)


# set-marker


@pytest.mark.parametrize(
    "case",
    [
        ("Kiln Log", "01", "DONE", b"\t- TODO check", b"\t- DONE check"),
        ("Kiln Log", "05", "none", b"- WAITING order", b"- order"),
        ("Loom Notes", "11", "LATER", b"- warp the loom", b"- LATER warp the loom"),
        (
            "Loom Notes",
            "14",
            "NOW",
            b"-\n  id:: " + ID.format("14").encode(),
            b"- NOW\n  id:: " + ID.format("14").encode(),
        ),
        ("Dye Pot", "32", "TODO", b"- CANCELED mordant", b"- TODO mordant"),
        ("Spindle", "21", "DOING", b"\t  - TODO ply", b"\t  - DOING ply"),
    ],
)
def test_set_marker(capsys: pytest.CaptureFixture[str], graph: Path, case: tuple[str, str, str, bytes, bytes]) -> None:
    name, block, marker, old, new = case
    before = page(graph, name)
    assert before.count(old) == 1
    assert run(capsys, graph, "set-marker", ID.format(block), marker)[0] == OK
    assert page(graph, name) == before.replace(old, new)
    assert run(capsys, graph, "set-marker", ID.format(block), marker)[0] == OK
    assert page(graph, name) == before.replace(old, new)


def test_set_marker_refuses_a_word_logseq_does_not_have(capsys: pytest.CaptureFixture[str], graph: Path) -> None:
    assert run(capsys, graph, "set-marker", ID.format("01"), "todo")[0] == BAD_ARGUMENTS
    assert run(capsys, graph, "set-marker", ID.format("01"), "STARTED")[0] == BAD_ARGUMENTS
    assert unchanged(graph)


def test_set_marker_refuses_a_bullet_that_opens_a_code_fence(capsys: pytest.CaptureFixture[str], graph: Path) -> None:
    # "- TODO ```text" no longer opens the fence, so the fenced bullet below would become a block.
    code, _, err = run(capsys, graph, "set-marker", ID.format("23"), "TODO")
    assert code == BAD_ARGUMENTS
    assert "change the outline" in err
    assert unchanged(graph)


# targets every write refuses


@pytest.mark.parametrize(
    ("argv", "code", "says"),
    [
        (("set-marker", "Kiln Log:2", "DONE"), BAD_ARGUMENTS, "ensure-id"),
        (("set-content", "Kiln Log", "--text", "x"), BAD_ARGUMENTS, "names a page"),
        (("ensure-id", "Kiln Log"), BAD_ARGUMENTS, "names a page"),
        (("set-property", ID.format("41"), "k", "v"), BAD_ARGUMENTS, "Glaze Recipes.md: has no outline"),
        (("ensure-id", "Glaze Recipes:1"), BAD_ARGUMENTS, "has no outline"),
        (("set-marker", ID.format("99"), "DONE"), NOT_FOUND, "no block carries this id"),
    ],
)
def test_refusals(capsys: pytest.CaptureFixture[str], graph: Path, argv: tuple[str, ...], code: int, says: str) -> None:
    got, _, err = run(capsys, graph, *argv)
    assert got == code
    assert says in err
    assert unchanged(graph)
