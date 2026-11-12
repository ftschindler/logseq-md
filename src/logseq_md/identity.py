"""Block ids: minting one the way Logseq does, and finding every one a graph holds.

DESIGN.md section 5. A Logseq id is a DataScript squuid: a random version 4
UUID whose first eight hex digits are replaced by the creation time in Unix
seconds, so ids sort by age. `mint` takes its clock and its randomness as
arguments, so a test pins both.

`scan` reads every page and journal and maps each `id::` value to where it
lives. It is built per invocation and never stored (DESIGN.md section 3, rule
5). An id found on two blocks is kept as two locations rather than one winning,
so that whoever asks can refuse.
"""

from __future__ import annotations

import re
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from logseq_md import blocks, lines
from logseq_md.graph import Graph

#: Logseq's own key for a block's identity; one of the two the opacity rule allows.
ID = "id"

UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.IGNORECASE)


def mint(clock: Callable[[], float] = time.time, random: Callable[[], uuid.UUID] = uuid.uuid4) -> str:
    """A squuid: `random`'s version 4 UUID with its first 32 bits set to `clock`'s whole seconds."""
    rest = str(random())[8:]
    return f"{int(clock()) & 0xFFFFFFFF:08x}{rest}"


@dataclass(frozen=True)
class Location:
    """Where an id lives: its file, the parsed page, and the block, or None for a page-level id."""

    path: Path
    page: blocks.Page
    block: int | None

    @property
    def line(self) -> int:
        """The 1-based line of the block's bullet, or 1 for a page-level id."""
        return 1 if self.block is None else self.page.blocks[self.block].start + 1

    def __str__(self) -> str:
        return f"{self.path}:{self.line}"


@dataclass(frozen=True)
class Ids:
    """Every id in a graph, lower-cased, mapped to each place it was found."""

    found: dict[str, tuple[Location, ...]]

    def duplicates(self) -> dict[str, tuple[Location, ...]]:
        return {key: where for key, where in self.found.items() if len(where) > 1}


def scan(graph: Graph) -> Ids:
    """Parse every file in the graph and collect its `id::` values. Never cached."""
    found: dict[str, list[Location]] = {}
    for path in graph.files():
        page = blocks.parse(lines.read(path))
        for prop in page.page_properties:
            if prop.key == ID and UUID.fullmatch(prop.value.strip()):
                found.setdefault(prop.value.strip().lower(), []).append(Location(path, page, None))
        for block in page.blocks:
            for prop in block.properties:
                if prop.key == ID and UUID.fullmatch(prop.value.strip()):
                    found.setdefault(prop.value.strip().lower(), []).append(Location(path, page, block.index))
    return Ids({key: tuple(where) for key, where in found.items()})
