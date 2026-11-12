"""Enumeration: every block in a graph that matches all the filters given.

DESIGN.md section 6, "Searching": filters compose as a conjunction, and every
one of them is a Logseq concept. A marker, a tag, a property's presence by a
key the caller names, a journal date range, a page. The key in
`--has-property` is compared and never read: the tool does not know what any
key means.

`--since` and `--until` select journals by the date their file is for. A page
has no date, so either flag leaves pages out.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from logseq_md import blocks, lines, names
from logseq_md.exits import BAD_ARGUMENTS, NOT_FOUND, Refusal
from logseq_md.graph import Graph
from logseq_md.output import Hit

_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
#: A reference that names a page: `[[page]]`, `#tag` and `#[[tag]]`.
_PAGE_REFERENCES = (blocks.RefKind.PAGE, blocks.RefKind.TAG)


@dataclass(frozen=True)
class Filters:
    marker: str | None = None
    tag: str | None = None
    has_property: str | None = None
    since: date | None = None
    until: date | None = None
    page: str | None = None


def parse_date(flag: str, text: str | None) -> date | None:
    if text is None:
        return None
    try:
        if not _DATE.fullmatch(text):
            raise ValueError(text)
        return date.fromisoformat(text)
    except ValueError:
        raise Refusal(BAD_ARGUMENTS, f"{flag} {text}: not a date (YYYY-MM-DD)") from None


def parse_marker(text: str | None) -> str | None:
    if text is None:
        return None
    if text.upper() not in blocks.MARKERS:
        raise Refusal(BAD_ARGUMENTS, f"--marker {text}: not one of {', '.join(blocks.MARKERS)}")
    return text.upper()


def pages(graph: Graph) -> Iterator[tuple[Path, blocks.Page]]:
    """Every page and journal, parsed, including those with no outline."""
    for path in graph.files():
        yield path, blocks.parse(lines.read(path))


def _file_matches(graph: Graph, path: Path, filters: Filters) -> bool:
    if filters.page is not None and not names.same_page(graph.page_name(path), filters.page):
        return False
    if filters.since is None and filters.until is None:
        return True
    day = graph.journal_date(path)
    if day is None:
        return False
    return (filters.since is None or day >= filters.since) and (filters.until is None or day <= filters.until)


def _block_matches(block: blocks.Block, filters: Filters) -> bool:
    if filters.marker is not None and block.marker != filters.marker:
        return False
    if filters.tag is not None and not any(
        ref.kind in _PAGE_REFERENCES and names.same_page(ref.target, filters.tag) for ref in block.references
    ):
        return False
    if filters.has_property is not None:
        wanted = filters.has_property.lower()
        if not any(prop.key.lower() == wanted for prop in block.properties):
            return False
    return True


def find(graph: Graph, filters: Filters) -> list[Hit]:
    """Every block matching all of `filters`, in file order then line order.

    A `--page` that names no page in the graph is exit 1 rather than an empty
    list, so a typo is not mistaken for a page with nothing on it.
    """
    if filters.page is not None and not any(
        names.same_page(graph.page_name(path), filters.page) for path in graph.files()
    ):
        raise Refusal(NOT_FOUND, f"--page {filters.page}: no such page or journal")
    hits: list[Hit] = []
    for path, page in pages(graph):
        if _file_matches(graph, path, filters):
            hits += [Hit(path, page, block.index) for block in page.blocks if _block_matches(block, filters)]
    return hits
