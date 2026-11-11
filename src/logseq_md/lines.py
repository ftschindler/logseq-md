"""A file held as lines that write back to the identical bytes.

This is the source representation every later structure sits beside rather
than replaces. A line keeps its indent prefix, its content and its exact ending,
so serialising lines nobody touched returns the bytes that were read, including
a missing final newline, a lone carriage return and a leading byte order mark.

Nothing here knows what a bullet, a property or a drawer is.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from logseq_md.exits import UNREADABLE, Refusal

BOM = "\ufeff"

#: A line is everything up to and including its ending. `\r\n` is tried before
#: a lone `\r`, so a Windows ending is one ending rather than two. The final
#: alternative matches a last line with no ending at all.
_LINE = re.compile(r"([^\r\n]*)(\r\n|\n|\r|)")
_INDENT = re.compile(r"[ \t]*")


@dataclass(frozen=True)
class Line:
    """One line: leading spaces and tabs, the rest, and the ending as found."""

    indent: str
    content: str
    ending: str

    def text(self) -> str:
        return self.indent + self.content + self.ending


@dataclass(frozen=True)
class Document:
    """A whole file as lines, and whether it began with a byte order mark."""

    lines: tuple[Line, ...]
    bom: bool = False

    def to_bytes(self) -> bytes:
        text = "".join(line.text() for line in self.lines)
        return ((BOM if self.bom else "") + text).encode("utf-8")


def split(text: str) -> tuple[Line, ...]:
    """Split decoded text into lines, losing nothing."""
    lines: list[Line] = []
    position = 0
    while position < len(text):
        match = _LINE.match(text, position)
        assert match is not None  # the pattern matches the empty string
        body, ending = match.group(1), match.group(2)
        indent = _INDENT.match(body)
        assert indent is not None
        lines.append(Line(indent.group(0), body[indent.end() :], ending))
        position = match.end()
    return tuple(lines)


def parse(data: bytes, *, name: str) -> Document:
    """Decode bytes strictly as UTF-8 and split them, or refuse naming `name`."""
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise Refusal(UNREADABLE, f"{name}: not valid UTF-8 (byte {error.start})") from error
    bom = text.startswith(BOM)
    return Document(split(text[1:] if bom else text), bom)


def read(path: Path) -> Document:
    """Read a file in binary, so no platform translates its line endings."""
    with path.open("rb") as handle:
        return parse(handle.read(), name=str(path))
