"""The three read output shapes, owned here so every read verb prints the same way.

DESIGN.md section 6, "What a read returns": text for people, `--json` for
scripts, `--paths` for piping. Every block arrives with its ancestor chain;
`--children` adds its subtree. Property stripping lives here too, so `show` and
`backlinks` drop the same keys `blocks` does: the drop list in `policy`, unless
`--raw` keeps everything or `--keep <key>` rescues one key.

Text output is the file's own lines, so a reader sees the block as it is
written: the ancestors' content lines, then the block, then its subtree when
asked for. It is not a contract. The JSON shape below is the one documented in
`--help` and pinned by a test.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TextIO

from logseq_md import blocks, identity, policy
from logseq_md.graph import Graph

BLOCKS_JSON = """\
--json prints a list, one object per block:
  {"path": "...", "page": "...", "date": "YYYY-MM-DD" or null, "line": N,
   "id": "..." or null, "marker": "TODO" or null, "content": "...",
   "properties": [{"key": "...", "value": "..."}],
   "ancestors": [<node>, ...], "children": [<node>, ...]}
"ancestors" runs from the page's top level down to the parent. A <node> has
"line", "id", "marker", "content" and "properties"; under "children" it also
has "children". "children" is present only with --children. "line" counts
from 1; "content" is the bullet's text and its wrapped lines, without the
bullet."""

PAGES_JSON = """\
--json prints a list, one object per file:
  {"path": "...", "name": "...", "date": "YYYY-MM-DD" or null,
   "outline": true or false, "blocks": N}
"outline" is false for a page with no bullets, which has no blocks."""


@dataclass(frozen=True)
class Options:
    """What a read verb was asked to include."""

    children: bool = False
    raw: bool = False
    keep: frozenset[str] = frozenset()

    def shows(self, key: str) -> bool:
        """Whether a property with this key is printed. Keys compare as Logseq's do, ignoring case."""
        folded = key.lower()
        return self.raw or folded in self.keep or folded not in policy.DROPPED


@dataclass(frozen=True)
class Hit:
    """One block a read matched: its file, the parsed page, and the block's index."""

    path: Path
    page: blocks.Page
    block: int


def options(children: bool, raw: bool, keep: Sequence[str] | None) -> Options:
    return Options(children, raw, frozenset(key.lower() for key in keep or ()))


def content(page: blocks.Page, block: blocks.Block) -> str:
    """The block's text and wrapped lines, without the bullet or any indent."""
    lines = page.document.lines[block.start : block.content_end]
    first = lines[0].content[1:].lstrip(" \t")
    return "\n".join([first, *(line.content for line in lines[1:])])


def block_id(block: blocks.Block) -> str | None:
    return next((prop.value.strip() for prop in block.properties if prop.key == identity.ID), None)


def _node(page: blocks.Page, block: blocks.Block, opts: Options) -> dict[str, Any]:
    return {
        "line": block.start + 1,
        "id": block_id(block),
        "marker": block.marker,
        "content": content(page, block),
        "properties": [{"key": p.key, "value": p.value} for p in block.properties if opts.shows(p.key)],
    }


def _subtree(page: blocks.Page, index: int, opts: Options) -> list[dict[str, Any]]:
    return [
        {**_node(page, page.blocks[child], opts), "children": _subtree(page, child, opts)}
        for child in page.blocks[index].children
    ]


def ancestors(page: blocks.Page, index: int) -> list[blocks.Block]:
    """The block's ancestors, from the top level down to its parent."""
    chain: list[blocks.Block] = []
    parent = page.blocks[index].parent
    while parent is not None:
        chain.append(page.blocks[parent])
        parent = page.blocks[parent].parent
    return chain[::-1]


def block_json(graph: Graph, hit: Hit, opts: Options) -> dict[str, Any]:
    block = hit.page.blocks[hit.block]
    day = graph.journal_date(hit.path)
    record: dict[str, Any] = {
        "path": str(hit.path),
        "page": graph.page_name(hit.path),
        "date": day.isoformat() if day else None,
        **_node(hit.page, block, opts),
        "ancestors": [_node(hit.page, parent, opts) for parent in ancestors(hit.page, hit.block)],
    }
    if opts.children:
        record["children"] = _subtree(hit.page, hit.block, opts)
    return record


def _descendants(page: blocks.Page, index: int) -> list[blocks.Block]:
    found: list[blocks.Block] = []
    for child in page.blocks[index].children:
        found += [page.blocks[child], *_descendants(page, child)]
    return found


def _lines(page: blocks.Page, block: blocks.Block, opts: Options, end: int | None = None) -> list[str]:
    hidden = {prop.line for prop in block.properties if not opts.shows(prop.key)}
    return [
        line.indent + line.content
        for number, line in enumerate(page.document.lines[block.start : end or block.end], start=block.start)
        if number not in hidden
    ]


def block_text(graph: Graph, hit: Hit, opts: Options) -> str:
    page = hit.page
    block = page.blocks[hit.block]
    out = [f"{hit.path}:{block.start + 1}  [{graph.page_name(hit.path)}]"]
    for parent in ancestors(page, hit.block):
        out += _lines(page, parent, opts, parent.content_end)
    out += _lines(page, block, opts)
    if opts.children:
        for child in _descendants(page, hit.block):
            out += _lines(page, child, opts)
    return "\n".join(out)


def unique_paths(paths: Iterable[Path]) -> list[str]:
    return list(dict.fromkeys(str(path) for path in paths))


def emit_blocks(graph: Graph, hits: Sequence[Hit], shape: str, opts: Options, out: TextIO) -> None:
    """Print matched blocks in one of the three shapes: `text`, `json` or `paths`."""
    if shape == "json":
        json.dump([block_json(graph, hit, opts) for hit in hits], out, indent=2, ensure_ascii=False)
        out.write("\n")
    elif shape == "paths":
        for path in unique_paths(hit.path for hit in hits):
            out.write(path + "\n")
    else:
        out.write("\n\n".join(block_text(graph, hit, opts) for hit in hits) + ("\n" if hits else ""))


def emit_pages(graph: Graph, pages: Sequence[tuple[Path, blocks.Page]], shape: str, out: TextIO) -> None:
    """Print pages and journals in one of the three shapes."""
    if shape == "json":
        records = []
        for path, page in pages:
            day = graph.journal_date(path)
            records.append(
                {
                    "path": str(path),
                    "name": graph.page_name(path),
                    "date": day.isoformat() if day else None,
                    "outline": page.outline,
                    "blocks": len(page.blocks),
                }
            )
        json.dump(records, out, indent=2, ensure_ascii=False)
        out.write("\n")
    elif shape == "paths":
        for path, _page in pages:
            out.write(f"{path}\n")
    else:
        for path, page in pages:
            note = f"{len(page.blocks)} block{'' if len(page.blocks) == 1 else 's'}" if page.outline else "no outline"
            out.write(f"{graph.page_name(path)}\t{path}\t{note}\n")
