"""The splice: replace line ranges in a file and leave every other byte as it was.

DESIGN.md section 7. A write names the lines it changes as `Edit`s, ranges of
line indices with the text that replaces them, and `apply` builds the new
document from the old one by copying every other line untouched, ending
included. Nothing here builds a tree or serialises one.

New lines take the file's own line ending: the ending of the lines they
replace, else of the line they follow, else of the first line that has one,
and `\\n` only in a file that has no ending anywhere. A file without a final
newline keeps not having one: an insertion after its last line moves the
missing ending onto the new last line, and the old last line gains the ending
that now separates the two. An empty file, or one being created, has none either.

`commit` writes atomically: to a temporary file in the same directory, then a
rename over the original, which `Path.replace` does on Windows too. `create`
makes a file that is not there yet, and refuses when one appeared meanwhile. Just before
the rename it reads the file again and compares it byte for byte with what the
write started from, refusing with exit 3 if anything moved.
"""

from __future__ import annotations

import difflib
import itertools
import os
import re
import shutil
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from logseq_md.exits import FILE_CHANGED, Refusal
from logseq_md.lines import Document, Line

_INDENT = re.compile(r"[ \t]*")
_NEWLINE = "\n"


@dataclass(frozen=True)
class Edit:
    """Replace lines `start` to `end`, exclusive, with `texts`: each a whole line, indent included, no ending.

    `start == end` inserts before line `start`; `start == len(lines)` appends.
    """

    start: int
    end: int
    texts: tuple[str, ...]


def _line(text: str, ending: str) -> Line:
    indent = _INDENT.match(text)
    assert indent is not None  # the pattern matches the empty string
    return Line(indent.group(0), text[indent.end() :], ending)


def _ending(lines: Sequence[Line], edit: Edit) -> str:
    """The ending new lines take: the replaced lines', the preceding line's, the file's, or `\\n`."""
    for line in lines[edit.start : edit.end]:
        if line.ending:
            return line.ending
    if edit.start > 0 and lines[edit.start - 1].ending:
        return lines[edit.start - 1].ending
    return next((line.ending for line in lines if line.ending), _NEWLINE)


def apply(document: Document, edits: Sequence[Edit]) -> Document:
    """The document with every edit applied. Edits must not overlap; their order does not matter."""
    lines = list(document.lines)
    ordered = sorted(edits, key=lambda edit: (edit.start, edit.end))
    for before, after in itertools.pairwise(ordered):
        if after.start < before.end or (after.start == before.start and before.start == before.end):
            raise ValueError(f"overlapping edits: {before} and {after}")
    for edit in reversed(ordered):
        if not 0 <= edit.start <= edit.end <= len(lines) or not edit.texts:
            raise ValueError(f"not an edit this document can take: {edit}")
        ending = _ending(lines, edit)
        new = [_line(text, ending) for text in edit.texts]
        if edit.end == len(lines):
            if edit.start < edit.end:
                # The replaced range held the last line: its ending, or its lack of one, stays last.
                new[-1] = Line(new[-1].indent, new[-1].content, lines[-1].ending)
            elif not lines or not lines[-1].ending:
                # Appending after a last line with no ending, or to no lines at all: the new last line has none.
                if lines:
                    lines[-1] = Line(lines[-1].indent, lines[-1].content, ending)
                new[-1] = Line(new[-1].indent, new[-1].content, "")
        lines[edit.start : edit.end] = new
    return Document(tuple(lines), document.bom)


def diff(path: Path, before: bytes, after: bytes) -> str:
    """A unified diff from `before` to `after`, marking a last line that has no newline as git does."""
    old = before.decode("utf-8").splitlines(keepends=True)
    new = after.decode("utf-8").splitlines(keepends=True)
    out: list[str] = []
    for line in difflib.unified_diff(old, new, f"a/{path.as_posix()}", f"b/{path.as_posix()}", n=3):
        out.append(line)
        if not line.endswith(("\n", "\r")):
            out.append("\n\\ No newline at end of file\n")
    return "".join(out)


def commit(path: Path, before: bytes, after: bytes) -> None:
    """Write `after` over `path` atomically, refusing with exit 3 if `path` no longer holds `before`."""
    handle, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(handle, "wb") as out:
            out.write(after)
            out.flush()
            os.fsync(out.fileno())
        shutil.copymode(path, temporary)
        with path.open("rb") as current:
            if current.read() != before:
                raise Refusal(FILE_CHANGED, f"{path}: changed since it was read; read it again and retry")
        Path(temporary).replace(path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


def create(path: Path, after: bytes) -> None:
    """Write `after` as a new file at `path`, atomically, refusing with exit 3 if one appeared meanwhile.

    The bytes go to a temporary file first and are then hard-linked into place,
    which fails rather than overwrites when the name is taken, on Windows too.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(handle, "wb") as out:
            out.write(after)
            out.flush()
            os.fsync(out.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError as error:
            raise Refusal(FILE_CHANGED, f"{path}: created since it was looked for; read it again and retry") from error
    finally:
        Path(temporary).unlink(missing_ok=True)
