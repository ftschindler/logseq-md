"""One resolver for every `<target>` form in DESIGN.md section 10.

A target is tried as, in order:

1. a uuid, found through the graph-wide id scan in `identity`;
2. a journal date written `YYYY-MM-DD`;
3. `page:line`, but only when the text before the last colon names an existing
   page, since a colon is legal in a page title. The line counts from 1. A line
   inside a block's range names that block; a line before the first bullet
   names the page;
4. a page name, compared the way Logseq compares them. A journal's title, such
   as `Feb 28th, 2025`, is a page name too.

A miss is exit 1. A name two files hold, or an id two blocks carry, is exit 2
listing every candidate, because answering from one of them would be a guess.
A `page:line` handed to a write verb is exit 2 naming `ensure-id`: a line number
does not survive the owner editing the page between two runs.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from logseq_md import blocks, identity, lines, names
from logseq_md.exits import BAD_ARGUMENTS, NOT_FOUND, Refusal
from logseq_md.graph import Graph

_DATE = re.compile(r"(\d{4})-(\d{2})-(\d{2})")
_PAGE_LINE = re.compile(r"(.+):(\d+)")


@dataclass(frozen=True)
class Target:
    """What a target resolved to: a file, its parsed page, and a block, or None for the page itself."""

    path: Path
    page: blocks.Page
    block: int | None


def resolve(graph: Graph, text: str, *, write: bool = False) -> Target:
    """Resolve `text` to a block or a page, or refuse. `write` refuses `page:line`."""
    text = text.strip()
    if identity.UUID.fullmatch(text):
        return _by_id(graph, text.lower())
    day = iso_date(text)
    if day is not None:
        path = graph.journal_path(day)
        if not path.is_file():
            raise Refusal(NOT_FOUND, f"{text}: no journal at {path}")
        return Target(path, blocks.parse(lines.read(path)), None)
    pages = _pages(graph)
    page_line = _PAGE_LINE.fullmatch(text)
    if page_line and names.page_key(page_line.group(1)) in pages:
        if write:
            raise Refusal(
                BAD_ARGUMENTS,
                f"{text}: a page:line target is for reading only; run ensure-id on it and write to the id",
            )
        return _by_line(_one(pages, page_line.group(1)), int(page_line.group(2)), text)
    if names.page_key(text) not in pages:
        raise Refusal(NOT_FOUND, f"{text}: no such page, journal or block")
    path = _one(pages, text)
    return Target(path, blocks.parse(lines.read(path)), None)


def iso_date(text: str) -> date | None:
    match = _DATE.fullmatch(text)
    if not match:
        return None
    try:
        return date(*(int(part) for part in match.groups()))
    except ValueError:
        return None


def _by_id(graph: Graph, key: str) -> Target:
    where = identity.scan(graph).found.get(key, ())
    if not where:
        raise Refusal(NOT_FOUND, f"{key}: no block carries this id")
    if len(where) > 1:
        raise Refusal(BAD_ARGUMENTS, f"{key}: carried by {len(where)} blocks: " + ", ".join(map(str, where)))
    return Target(where[0].path, where[0].page, where[0].block)


def _pages(graph: Graph) -> dict[str, list[Path]]:
    """Every file in the graph, by the key its page name compares by."""
    found: dict[str, list[Path]] = {}
    for path in graph.files():
        found.setdefault(names.page_key(graph.page_name(path)), []).append(path)
    return found


def _one(pages: dict[str, list[Path]], name: str) -> Path:
    paths = pages[names.page_key(name)]
    if len(paths) > 1:
        raise Refusal(BAD_ARGUMENTS, f"{name}: held by {len(paths)} files: " + ", ".join(map(str, paths)))
    return paths[0]


def _by_line(path: Path, number: int, text: str) -> Target:
    page = blocks.parse(lines.read(path))
    index = number - 1
    if not 0 <= index < len(page.document.lines):
        raise Refusal(NOT_FOUND, f"{text}: {path} has {len(page.document.lines)} lines")
    block = next((b.index for b in page.blocks if b.start <= index < b.end), None)
    return Target(path, page, block)
