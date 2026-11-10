"""The gate (DESIGN.md section 9): every fixture reads and writes back byte for byte.

It covers every markdown file under `tests/fixtures/`, so a fixture any later
stage adds is part of the gate the moment it lands. A fixture that is not valid
UTF-8 is there to be refused, and the gate checks that it is.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from logseq_md.exits import UNREADABLE, Refusal
from logseq_md.lines import read

FIXTURES = Path(__file__).resolve().parent / "fixtures"
ALL = sorted(FIXTURES.rglob("*.md"))


def _is_utf8(data: bytes) -> bool:
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return True


def test_there_are_fixtures_to_gate() -> None:
    assert ALL


@pytest.mark.parametrize("path", ALL, ids=lambda path: path.relative_to(FIXTURES).as_posix())
def test_round_trip_is_byte_identical(path: Path, tmp_path: Path) -> None:
    with path.open("rb") as handle:
        original = handle.read()
    if not _is_utf8(original):
        with pytest.raises(Refusal) as refused:
            read(path)
        assert refused.value.code == UNREADABLE
        return
    written = tmp_path / path.name
    with written.open("wb") as handle:
        handle.write(read(path).to_bytes())
    with written.open("rb") as handle:
        assert handle.read() == original
