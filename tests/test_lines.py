"""The line model: a file held as lines that write back to the identical bytes."""

from __future__ import annotations

from pathlib import Path

import pytest

from logseq_md.exits import UNREADABLE, Refusal
from logseq_md.lines import Line, parse, read

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "lines"


def test_a_line_keeps_indent_content_and_ending() -> None:
    document = parse(b"\t  - a\r\nb", name="x")
    assert document.lines == (Line("\t  ", "- a", "\r\n"), Line("", "b", ""))


@pytest.mark.parametrize(
    ("data", "endings"),
    [
        (b"a\nb", ["\n", ""]),
        (b"a\r\nb\r\n", ["\r\n", "\r\n"]),
        (b"a\rb\r", ["\r", "\r"]),
        (b"a\r\nb\nc\rd", ["\r\n", "\n", "\r", ""]),
        (b"\r\n\n\r", ["\r\n", "\n", "\r"]),
    ],
)
def test_every_ending_is_kept_as_found(data: bytes, endings: list[str]) -> None:
    assert [line.ending for line in parse(data, name="x").lines] == endings


def test_an_empty_file_has_no_lines_and_writes_back_empty() -> None:
    document = parse(b"", name="x")
    assert document.lines == ()
    assert document.to_bytes() == b""


def test_a_blank_line_is_all_indent() -> None:
    assert parse(b" \t \n", name="x").lines == (Line(" \t ", "", "\n"),)


def test_a_byte_order_mark_is_retained_and_not_part_of_the_first_line() -> None:
    data = (FIXTURES / "bom.md").read_bytes()
    document = parse(data, name="bom.md")
    assert document.bom
    assert document.lines[0].content.startswith("- ")
    assert document.to_bytes() == data


def test_a_file_that_is_not_utf8_is_refused_with_its_name() -> None:
    path = FIXTURES / "not-utf8.md"
    with pytest.raises(Refusal) as refused:
        read(path)
    assert refused.value.code == UNREADABLE
    assert str(path) in refused.value.message


def test_mixed_tabs_and_spaces_in_one_prefix_are_kept_in_order() -> None:
    document = read(FIXTURES / "mixed-prefix.md")
    assert "\t\t  " in [line.indent for line in document.lines]
