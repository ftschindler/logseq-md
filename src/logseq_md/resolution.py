"""Resolution: what a block's references point at, and what points at a page.

DESIGN.md section 6, "Resolution". A `((uuid))` or `{{embed ((uuid))}}` resolves
to the block carrying that `id::`, found through the graph-wide id scan. A
`[[page]]`, `#tag` or `#[[tag]]` resolves to the path the page's name maps to
through the graph's own `:file/name-format`.

Nothing is substituted silently. Every reference is reported with a status:

- `resolved`: found; a block reference carries the block it found.
- `dangling`: no block carries the id, or no file holds the page. A dangling
  block reference in a synced graph usually means another device has it.
- `ambiguous`: two or more blocks carry the id; every one is listed.
- `cycle`: the id is already being resolved further up this chain, so it is
  reported where it is met rather than followed.

References resolve one level deep by default; `depth` goes further. A depth
bounds every chain and the cycle check stops each one early, so no read can
fail to terminate.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from logseq_md import blocks, enumeration, identity, names
from logseq_md.exits import NOT_FOUND, Refusal
from logseq_md.graph import Graph

RESOLVED = "resolved"
DANGLING = "dangling"
AMBIGUOUS = "ambiguous"
CYCLE = "cycle"

_BLOCK_KINDS = (blocks.RefKind.BLOCK, blocks.RefKind.EMBED)


@dataclass(frozen=True)
class Resolved:
    """One reference and what it resolved to.

    `path` and `line` say where the reference is written, the line counting
    from 1. For a page or tag, `page_path` is the file its name maps to. For a
    block reference, `found` is where the block lives when `status` is
    `resolved`, every candidate when it is `ambiguous`, and `references` are
    the block's own references when the depth allowed going further, else None.
    """

    reference: blocks.Reference
    path: Path
    status: str
    page_path: Path | None = None
    found: tuple[identity.Location, ...] = ()
    references: tuple[Resolved, ...] | None = None


class Resolver:
    """Resolves references against one graph, scanning its ids once per invocation."""

    def __init__(self, graph: Graph) -> None:
        self.graph = graph
        self.ids = identity.scan(graph)
        self.files = frozenset(graph.files())

    def resolve(
        self,
        path: Path,
        references: Iterable[blocks.Reference],
        depth: int,
        chain: frozenset[str] = frozenset(),
    ) -> tuple[Resolved, ...]:
        """Resolve `references`, written in `path`, `depth` levels deep.

        `chain` holds the ids already being resolved above this point, which
        is where a cycle is detected.
        """
        if depth < 1:
            return ()
        return tuple(self._one(path, reference, depth, chain) for reference in references)

    def _one(self, path: Path, reference: blocks.Reference, depth: int, chain: frozenset[str]) -> Resolved:
        if reference.kind not in _BLOCK_KINDS:
            target = self.graph.page_path(reference.target)
            status = RESOLVED if target in self.files else DANGLING
            return Resolved(reference, path, status, page_path=target)
        key = reference.target.lower()
        if key in chain:
            return Resolved(reference, path, CYCLE)
        where = self.ids.found.get(key, ())
        if not where:
            return Resolved(reference, path, DANGLING)
        if len(where) > 1:
            return Resolved(reference, path, AMBIGUOUS, found=where)
        found = where[0]
        nested = None
        if depth > 1:
            nested = self.resolve(found.path, _references_of(found), depth - 1, chain | {key})
        return Resolved(reference, path, RESOLVED, found=where, references=nested)


def _references_of(location: identity.Location) -> tuple[blocks.Reference, ...]:
    if location.block is None:
        return location.page.references
    return location.page.blocks[location.block].references


def chain_of(block: blocks.Block | None) -> frozenset[str]:
    """The id a shown block carries, as the start of its references' chain."""
    if block is None:
        return frozenset()
    return frozenset(
        prop.value.strip().lower()
        for prop in block.properties
        if prop.key == identity.ID and identity.UUID.fullmatch(prop.value.strip())
    )


def backlinks(graph: Graph, name: str) -> list[tuple[Path, blocks.Page, int]]:
    """Every block linking to the page `name` by `[[...]]`, `#tag` or `#[[...]]`, in file then line order.

    A name that no file holds and nothing links to is exit 1, so a typo is not
    mistaken for a page nobody links to. A page with no file that something
    links to is answered: Logseq creates such a page on the first link.
    """
    found = [(hit.path, hit.page, hit.block) for hit in enumeration.find(graph, enumeration.Filters(tag=name))]
    if not found and not any(names.same_page(graph.page_name(path), name) for path in graph.files()):
        raise Refusal(NOT_FOUND, f"{name}: no such page, and nothing links to it")
    return found
