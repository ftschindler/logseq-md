"""A page's lines as blocks, with the structure kept alongside the lines rather than in their place.

This implements DESIGN.md section 4. A block is a range of line indices into the
`Document` it was parsed from; nothing here copies or rewrites a line, so the
round-trip gate is untouched by construction. Within a block's own range every
line has exactly one kind: the bullet, wrapped content, a property, a
`DEADLINE:` or `SCHEDULED:` line, or a drawer line. Children are not in their
parent's range: they are blocks of their own, linked by index.

Properties are recognised by their shape and their position under a bullet,
never by a computed indent, and their keys are kept as found and never
interpreted. Code fences, backtick and tilde, are tracked across the page, so a
fenced line is content however much it looks like a bullet, property or drawer.

Lines before the first bullet are the page's preamble: page-level properties
and prose. A page with no bullet at all parses to no blocks, and says so.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

from logseq_md.lines import Document

#: Logseq's markers, a closed set (DESIGN.md section 7, "The five writes").
MARKERS = ("TODO", "DOING", "DONE", "LATER", "NOW", "WAITING", "CANCELED")


class Kind(Enum):
    """What one line is."""

    BULLET = "bullet"
    CONTENT = "content"
    PROPERTY = "property"
    SCHEDULING = "scheduling"
    DRAWER = "drawer"
    PAGE_PROPERTY = "page-property"
    PROSE = "prose"


class RefKind(Enum):
    """What a reference in content points at, as written."""

    PAGE = "page"
    TAG = "tag"
    BLOCK = "block"
    EMBED = "embed"


@dataclass(frozen=True)
class Property:
    """One property line: its index, its key and its raw value, as found."""

    line: int
    key: str
    value: str


@dataclass(frozen=True)
class Reference:
    """A reference in content: its kind, its target as written, and where it starts.

    `column` counts characters from the start of the line, indent included.
    Nothing here resolves the target.
    """

    kind: RefKind
    target: str
    line: int
    column: int


@dataclass(frozen=True)
class Block:
    """A bullet and its continuation lines, as the range `start` to `end`, exclusive.

    `kinds[i]` is the kind of line `start + i`. `content_end` closes the content
    span: the bullet line and the wrapped lines after it, up to the first
    property, drawer, scheduling line or child.
    """

    index: int
    start: int
    end: int
    depth: int
    prefix: str
    parent: int | None
    children: tuple[int, ...]
    kinds: tuple[Kind, ...]
    content_end: int
    marker: str | None
    properties: tuple[Property, ...]
    references: tuple[Reference, ...]


@dataclass(frozen=True)
class Page:
    """A document with its blocks.

    `preamble_end` is the first bullet's line, or the line count when there is
    none, in which case `outline` is false and `blocks` is empty. `fences` holds
    each code fence as the range of lines from its opening marker to its closing
    one, or to the end of the file when it never closes.
    """

    document: Document
    blocks: tuple[Block, ...]
    preamble_end: int
    preamble_kinds: tuple[Kind, ...]
    page_properties: tuple[Property, ...]
    references: tuple[Reference, ...]
    fences: tuple[range, ...]

    @property
    def fenced(self) -> frozenset[int]:
        return frozenset(number for fence in self.fences for number in fence)

    @property
    def outline(self) -> bool:
        return bool(self.blocks)

    @property
    def roots(self) -> tuple[int, ...]:
        return tuple(block.index for block in self.blocks if block.parent is None)


_BULLET = re.compile(r"-(?:[ \t]|$)")
_PROPERTY = re.compile(r"([A-Za-z0-9_][^\s:]*?)::(?:[ \t]|$)(.*)")
_DRAWER = re.compile(r":([A-Za-z][A-Za-z0-9_-]*):[ \t]*$")
_DRAWER_END = ":END:"
_SCHEDULING = ("DEADLINE:", "SCHEDULED:")
_FENCE = re.compile(r"`{3,}|~{3,}")

_UUID = r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
_REFERENCES = re.compile(
    r"(?P<embed>\{\{embed \(\((?P<embed_id>" + _UUID + r")\)\)\}\})"
    r"|(?P<block>\(\((?P<block_id>" + _UUID + r")\)\))"
    r"|(?:(?<=\s)|^)#\[\[(?P<multi_tag>[^\[\]]+)\]\]"
    r"|\[\[(?P<page>[^\[\]]+)\]\]"
    r"|(?:(?<=\s)|^)#(?P<tag>[^\s#\[\],;.!?\"'()]+)"
)


def width(prefix: str) -> int:
    """An indent's depth as a number to compare, a tab counting as one level and two spaces as one."""
    return 2 * prefix.count("\t") + prefix.count(" ")


def find_references(text: str, line: int, offset: int) -> list[Reference]:
    """Every reference in `text`, which starts at column `offset` of `line`."""
    found: list[Reference] = []
    for match in _REFERENCES.finditer(text):
        group = match.lastgroup
        if group in ("embed", "embed_id"):
            kind, target = RefKind.EMBED, match.group("embed_id")
        elif group in ("block", "block_id"):
            kind, target = RefKind.BLOCK, match.group("block_id")
        elif group == "multi_tag":
            kind, target = RefKind.TAG, match.group("multi_tag")
        elif group == "page":
            kind, target = RefKind.PAGE, match.group("page")
        else:
            kind, target = RefKind.TAG, match.group("tag")
        found.append(Reference(kind, target, line, offset + match.start()))
    return found


def marker_of(text: str) -> str | None:
    """The marker a block's text starts with, if any."""
    return next((marker for marker in MARKERS if text == marker or text.startswith(marker + " ")), None)


@dataclass
class _Open:
    """A block being parsed, before its range and children are known."""

    start: int
    depth: int
    prefix: str
    parent: int | None
    kinds: list[Kind]
    marker: str | None
    properties: list[Property]
    references: list[Reference]
    children: list[int]


def parse(document: Document) -> Page:  # noqa: PLR0912, PLR0915 - one pass, one state machine
    """Parse a document into a page. Never fails: any line has a kind."""
    lines = document.lines
    fence: str | None = None
    in_drawer = False
    fence_starts: list[int] = []
    fence_ends: list[int] = []
    opened: list[_Open] = []
    stack: list[int] = []
    preamble_kinds: list[Kind] = []
    page_properties: list[Property] = []
    page_references: list[Reference] = []

    for number, line in enumerate(lines):
        content = line.content
        current = opened[-1] if opened else None

        if fence is not None:
            if _FENCE.match(content) and content.startswith(fence):
                fence = None
                fence_ends.append(number + 1)
            if current is None:
                preamble_kinds.append(Kind.PROSE)
            else:
                current.kinds.append(Kind.CONTENT)
            continue

        if _BULLET.match(content):
            in_drawer = False
            while stack and width(opened[stack[-1]].prefix) >= width(line.indent):
                stack.pop()
            parent = stack[-1] if stack else None
            text = content[1:].lstrip(" \t")
            offset = len(line.indent) + len(content) - len(text)
            index = len(opened)
            opened.append(
                _Open(
                    start=number,
                    depth=len(stack) + 1,
                    prefix=line.indent,
                    parent=parent,
                    kinds=[Kind.BULLET],
                    marker=marker_of(text),
                    properties=[],
                    references=[],
                    children=[],
                )
            )
            if parent is not None:
                opened[parent].children.append(index)
            stack.append(index)
            opening = _FENCE.match(text)
            if opening:
                fence = opening.group(0)
                fence_starts.append(number)
            else:
                opened[index].references += find_references(text, number, offset)
            continue

        if current is None:
            prop = _PROPERTY.match(content)
            if prop:
                preamble_kinds.append(Kind.PAGE_PROPERTY)
                page_properties.append(Property(number, prop.group(1), prop.group(2)))
                continue
            preamble_kinds.append(Kind.PROSE)
            opening = _FENCE.match(content)
            if opening:
                fence = opening.group(0)
                fence_starts.append(number)
            else:
                page_references += find_references(content, number, len(line.indent))
            continue

        if in_drawer:
            current.kinds.append(Kind.DRAWER)
            if content.rstrip(" \t") == _DRAWER_END:
                in_drawer = False
            continue

        if not content:
            current.kinds.append(Kind.CONTENT)
            continue

        prop = _PROPERTY.match(content)
        if prop:
            current.kinds.append(Kind.PROPERTY)
            current.properties.append(Property(number, prop.group(1), prop.group(2)))
            continue

        if _DRAWER.match(content):
            current.kinds.append(Kind.DRAWER)
            in_drawer = True
            continue

        if content.startswith(_SCHEDULING):
            current.kinds.append(Kind.SCHEDULING)
            continue

        current.kinds.append(Kind.CONTENT)
        opening = _FENCE.match(content)
        if opening:
            fence = opening.group(0)
            fence_starts.append(number)
        else:
            current.references += find_references(content, number, len(line.indent))

    blocks = tuple(_close(index, block) for index, block in enumerate(opened))
    preamble_end = blocks[0].start if blocks else len(lines)
    return Page(
        document=document,
        blocks=blocks,
        preamble_end=preamble_end,
        preamble_kinds=tuple(preamble_kinds),
        page_properties=tuple(page_properties),
        references=tuple(page_references),
        fences=tuple(range(start, end) for start, end in zip(fence_starts, [*fence_ends, len(lines)], strict=False)),
    )


def _close(index: int, block: _Open) -> Block:
    kinds = tuple(block.kinds)
    span = 1
    while span < len(kinds) and kinds[span] is Kind.CONTENT:
        span += 1
    return Block(
        index=index,
        start=block.start,
        end=block.start + len(kinds),
        depth=block.depth,
        prefix=block.prefix,
        parent=block.parent,
        children=tuple(block.children),
        kinds=kinds,
        content_end=block.start + span,
        marker=block.marker,
        properties=tuple(block.properties),
        references=tuple(block.references),
    )
