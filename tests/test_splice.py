"""The splice (DESIGN.md section 7): new lines take the file's endings, and nothing else moves."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from logseq_md import splice
from logseq_md.exits import FILE_CHANGED, Refusal
from logseq_md.lines import parse


def spliced(data: bytes, *edits: splice.Edit) -> bytes:
    return splice.apply(parse(data, name="t"), edits).to_bytes()


def test_an_insertion_takes_the_ending_of_the_line_it_follows() -> None:
    assert spliced(b"- a\r\n- b\n", splice.Edit(1, 1, ("  k:: v",))) == b"- a\r\n  k:: v\r\n- b\n"
    assert spliced(b"- a\r- b\r", splice.Edit(1, 1, ("  k:: v",))) == b"- a\r  k:: v\r- b\r"


def test_an_insertion_at_the_start_takes_the_first_lines_ending() -> None:
    assert spliced(b"- a\r\n", splice.Edit(0, 0, ("- z",))) == b"- z\r\n- a\r\n"


def test_appending_to_a_file_without_a_final_newline_keeps_it_without_one() -> None:
    assert spliced(b"- a\r\n- b", splice.Edit(2, 2, ("  k:: v",))) == b"- a\r\n- b\r\n  k:: v"
    assert spliced(b"- a\n- b\n", splice.Edit(2, 2, ("  k:: v",))) == b"- a\n- b\n  k:: v\n"
    # A one-line file has no ending to copy, so it gets the newline Logseq writes.
    assert spliced(b"- a", splice.Edit(1, 1, ("  k:: v",))) == b"- a\n  k:: v"


def test_replacing_the_last_line_keeps_its_missing_ending() -> None:
    assert spliced(b"- a\n- b", splice.Edit(1, 2, ("- c", "  d"))) == b"- a\n- c\n  d"


def test_the_byte_order_mark_and_untouched_lines_survive() -> None:
    data = "\ufeff- a\n\t  - b  \n- c".encode()
    assert spliced(data, splice.Edit(2, 3, ("- C",))) == "\ufeff- a\n\t  - b  \n- C".encode()


def test_two_edits_apply_against_the_original_line_numbers() -> None:
    out = spliced(b"- a\n- b\n- c\n", splice.Edit(2, 3, ("- C",)), splice.Edit(0, 1, ("- A",)))
    assert out == b"- A\n- b\n- C\n"
    with pytest.raises(ValueError, match="overlapping"):
        spliced(b"- a\n- b\n", splice.Edit(0, 2, ("x",)), splice.Edit(1, 2, ("y",)))


def test_the_diff_marks_a_last_line_with_no_newline() -> None:
    out = splice.diff(Path("p.md"), b"- a\n- b", b"- a\n- b\n  k:: v")
    assert out.splitlines() == [
        "--- a/p.md",
        "+++ b/p.md",
        "@@ -1,2 +1,3 @@",
        " - a",
        "-- b",
        "\\ No newline at end of file",
        "+- b",
        "+  k:: v",
        "\\ No newline at end of file",
    ]


def test_commit_replaces_the_file_and_leaves_no_temporary(tmp_path: Path) -> None:
    path = tmp_path / "p.md"
    path.write_bytes(b"- a")
    splice.commit(path, b"- a", b"- b")
    assert path.read_bytes() == b"- b"
    assert [p.name for p in tmp_path.iterdir()] == ["p.md"]


def test_commit_refuses_when_the_file_moved(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "p.md"
    path.write_bytes(b"- a")
    real = os.fsync

    def edited_meanwhile(fd: int) -> None:
        real(fd)
        path.write_bytes(b"- a, edited by hand")

    monkeypatch.setattr(splice.os, "fsync", edited_meanwhile)
    with pytest.raises(Refusal) as refused:
        splice.commit(path, b"- a", b"- b")
    assert refused.value.code == FILE_CHANGED
    assert path.read_bytes() == b"- a, edited by hand"
    assert [p.name for p in tmp_path.iterdir()] == ["p.md"]
