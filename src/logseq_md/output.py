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
from typing import TYPE_CHECKING, Any, TextIO

from logseq_md import blocks, identity, policy
from logseq_md.graph import Graph

if TYPE_CHECKING:
    from logseq_md.resolution import Resolved
    from logseq_md.targets import Target

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

REFERENCE_JSON = """\
A <reference> is where it is written and what it resolved to:
  {"kind": "block" | "embed" | "page" | "tag", "target": "...",
   "path": "...", "line": N, "status": "resolved" | "dangling" | "ambiguous" | "cycle",
   "page_path": "..." or null, "found": [<found>, ...], "references": [<reference>, ...] or null}
"page_path" is the file a page or tag maps to, whether or not it exists; it is
"dangling" when it does not. A block reference is "dangling" when no block
carries the id, "ambiguous" when several do, and "cycle" when the id is already
being resolved further up, where it is reported rather than followed. "found"
holds the block, or every candidate: "path", "page", "line", "id", "marker",
"content" and "properties". "references" are the found block's own references,
resolved when --depth went further, else null."""

SHOW_JSON = (
    """\
--json prints one object. For a block, the object --json of blocks prints, plus
"references": [<reference>, ...] for the block and, with --children, its subtree.
For a page:
  {"path": "...", "page": "...", "date": "YYYY-MM-DD" or null, "outline": true or false,
   "content": "...", "properties": [{"key": "...", "value": "..."}],
   "blocks": [<node>, ...], "references": [<reference>, ...]}
"content" is the text before the first bullet, without its page properties.
"blocks" are the top-level blocks; with --children each has "children".

"""
    + REFERENCE_JSON
)


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


def descendants(page: blocks.Page, index: int) -> list[blocks.Block]:
    found: list[blocks.Block] = []
    for child in page.blocks[index].children:
        found += [page.blocks[child], *descendants(page, child)]
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
        for child in descendants(page, hit.block):
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


def _found_json(graph: Graph, location: identity.Location, opts: Options) -> dict[str, Any]:
    record: dict[str, Any] = {"path": str(location.path), "page": graph.page_name(location.path)}
    if location.block is None:
        return {**record, "line": 1, "id": None, "marker": None, "content": "", "properties": []}
    return {**record, **_node(location.page, location.page.blocks[location.block], opts)}


def references_json(graph: Graph, resolved: Sequence[Resolved], opts: Options) -> list[dict[str, Any]]:
    return [
        {
            "kind": item.reference.kind.value,
            "target": item.reference.target,
            "path": str(item.path),
            "line": item.reference.line + 1,
            "status": item.status,
            "page_path": str(item.page_path) if item.page_path else None,
            "found": [_found_json(graph, location, opts) for location in item.found],
            "references": None if item.references is None else references_json(graph, item.references, opts),
        }
        for item in resolved
    ]


def _written(reference: blocks.Reference) -> str:
    kind = reference.kind
    if kind is blocks.RefKind.EMBED:
        return f"{{{{embed (({reference.target}))}}}}"
    if kind is blocks.RefKind.BLOCK:
        return f"(({reference.target}))"
    return f"[[{reference.target}]]" if kind is blocks.RefKind.PAGE else f"#[[{reference.target}]]"


def references_text(graph: Graph, resolved: Sequence[Resolved], level: int = 1) -> list[str]:
    """One entry per reference, its resolution indented under it, nested references further in."""
    out: list[str] = []
    pad = "  " * level
    for item in resolved:
        head = f"{pad}{_written(item.reference)}  at {item.path}:{item.reference.line + 1}"
        if item.page_path is not None:
            note = "" if item.status != "dangling" else "  (dangling: no such file)"
            out.append(f"{head}  -> {item.page_path}{note}")
            continue
        if item.status != "resolved":
            detail = {
                "dangling": "dangling: no block carries this id",
                "cycle": "cycle: already being resolved above, not followed",
                "ambiguous": "ambiguous: carried by " + ", ".join(map(str, item.found)),
            }[item.status]
            out.append(f"{head}  -> {detail}")
            continue
        location = item.found[0]
        out.append(f"{head}  -> {location}  [{graph.page_name(location.path)}]")
        if location.block is not None:
            block = location.page.blocks[location.block]
            out += [f"{pad}  | {line}" for line in content(location.page, block).split("\n")]
        if item.references:
            out += references_text(graph, item.references, level + 1)
    return out


def _with_references(text: str, graph: Graph, resolved: Sequence[Resolved]) -> str:
    return text if not resolved else "\n".join([text, "references:", *references_text(graph, resolved)])


def show(graph: Graph, target: Target, resolved: Sequence[Resolved], shape: str, opts: Options) -> str:
    """One block with its ancestors, or a page with its blocks, and its references resolved, as printed."""
    if shape == "paths":
        return f"{target.path}\n"
    if target.block is not None:
        hit = Hit(target.path, target.page, target.block)
        if shape == "json":
            record = {**block_json(graph, hit, opts), "references": references_json(graph, resolved, opts)}
            return json.dumps(record, indent=2, ensure_ascii=False) + "\n"
        return _with_references(block_text(graph, hit, opts), graph, resolved) + "\n"
    path, page = target.path, target.page
    hidden = {prop.line for prop in page.page_properties}
    if shape == "json":
        day = graph.journal_date(path)
        record = {
            "path": str(path),
            "page": graph.page_name(path),
            "date": day.isoformat() if day else None,
            "outline": page.outline,
            "content": "\n".join(
                line.indent + line.content
                for number, line in enumerate(page.document.lines[: page.preamble_end])
                if number not in hidden
            ),
            "properties": [{"key": p.key, "value": p.value} for p in page.page_properties if opts.shows(p.key)],
            "blocks": [
                {
                    **_node(page, page.blocks[root], opts),
                    **({"children": _subtree(page, root, opts)} if opts.children else {}),
                }
                for root in page.roots
            ],
            "references": references_json(graph, resolved, opts),
        }
        return json.dumps(record, indent=2, ensure_ascii=False) + "\n"
    dropped = {prop.line for prop in page.page_properties if not opts.shows(prop.key)}
    lines = [f"{path}  [{graph.page_name(path)}]"]
    lines += [
        line.indent + line.content
        for number, line in enumerate(page.document.lines[: page.preamble_end])
        if number not in dropped
    ]
    for root in page.roots:
        lines += _lines(page, page.blocks[root], opts)
        if opts.children:
            for child in descendants(page, root):
                lines += _lines(page, child, opts)
    return _with_references("\n".join(lines), graph, resolved) + "\n"
