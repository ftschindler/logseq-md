"""The in-block writes: `ensure-id`, `set-property`, `set-content` and `set-marker`.

DESIGN.md sections 5 and 7. Each verb is a planner, taking a parsed page and a
block and returning the one `splice.Edit` that reaches the end state it was
asked for, or None when the block is already there. A second run therefore
plans nothing and writes nothing (DESIGN.md section 3, rule 4). `run` carries a
plan to the file, or prints it as a diff.

Property keys are copied, never read: the only key compared by name is
Logseq's own `id`, which `ensure-id` mints and no other verb may set. A new
property line is indented like the block's existing property lines, or by the
conventional rule, the block's prefix and two spaces, when it has none.

No planner writes a `:LOGBOOK:` line or moves a line it did not write.
"""

from __future__ import annotations

import re
import sys
from collections.abc import Callable
from pathlib import Path

from logseq_md import blocks, identity, splice, targets
from logseq_md.exits import BAD_ARGUMENTS, Refusal
from logseq_md.graph import Graph

_KEY = re.compile(r"[A-Za-z0-9_][^\s:]*")
_LINE_BREAK = re.compile(r"\r\n|\n|\r")
_NONE = "none"


def block_for_write(graph: Graph, text: str, *, page_line: bool = False) -> tuple[targets.Target, blocks.Block]:
    """Resolve a write's target to its file and one block in it, or refuse.

    Only `ensure-id` passes `page_line`: it is how a block without an id gets
    one, and every other write takes the id it prints.
    """
    target = targets.resolve(graph, text, write=not page_line)
    if not target.page.outline:
        raise Refusal(BAD_ARGUMENTS, f"{target.path}: has no outline, so no block in it can be written")
    if target.block is None:
        raise Refusal(BAD_ARGUMENTS, f"{text}: names a page, not a block; give a block's id or page:line")
    return target, target.page.blocks[target.block]


def _property_prefix(page: blocks.Page, block: blocks.Block) -> str:
    if block.properties:
        return page.document.lines[block.properties[0].line].indent
    return block.prefix + "  "


def _property_text(key: str, value: str) -> str:
    return f"{key}:: {value}" if value else f"{key}::"


def plan_ensure_id(page: blocks.Page, block: blocks.Block, mint: Callable[[], str]) -> tuple[str, splice.Edit | None]:
    """The block's id and no edit, or a freshly minted id and the edit inserting it after the content."""
    for prop in block.properties:
        if prop.key == identity.ID:
            value = prop.value.strip()
            if not identity.UUID.fullmatch(value):
                raise Refusal(BAD_ARGUMENTS, f"line {prop.line + 1}: carries an id that is not a uuid")
            return value, None
    new = mint()
    text = _property_prefix(page, block) + _property_text(identity.ID, new)
    return new, splice.Edit(block.content_end, block.content_end, (text,))


def plan_set_property(page: blocks.Page, block: blocks.Block, key: str, value: str) -> splice.Edit | None:
    """Replace the value on the line carrying `key`, or insert one after the last property."""
    if not _KEY.fullmatch(key):
        raise Refusal(BAD_ARGUMENTS, f"{key!r}: not a property key Logseq would read")
    if key.lower() == identity.ID:
        raise Refusal(BAD_ARGUMENTS, f"{key}: a block's id is given by ensure-id, never set")
    if _LINE_BREAK.search(value):
        raise Refusal(BAD_ARGUMENTS, "a property value is one line")
    found = [prop for prop in block.properties if prop.key == key]
    if len(found) > 1:
        raise Refusal(
            BAD_ARGUMENTS, f"{key}: on {len(found)} lines of this block: " + ", ".join(str(p.line + 1) for p in found)
        )
    if found:
        line = page.document.lines[found[0].line]
        text = line.indent + _property_text(key, value)
        if text == line.indent + line.content:
            return None
        return splice.Edit(found[0].line, found[0].line + 1, (text,))
    after = block.properties[-1].line + 1 if block.properties else block.content_end
    return splice.Edit(after, after, (_property_prefix(page, block) + _property_text(key, value),))


def _bullet(page: blocks.Page, block: blocks.Block) -> tuple[str, str]:
    """The bullet line split into what precedes the text (prefix, dash, separator) and the text."""
    line = page.document.lines[block.start]
    text = line.content[1:].lstrip(" \t")
    head = line.indent + line.content[: len(line.content) - len(text)]
    return (head if head != line.indent + "-" else head + " "), text


def plan_set_content(page: blocks.Page, block: blocks.Block, text: str) -> splice.Edit | None:
    """Replace the content span, keeping the bullet's spacing and the span's continuation indent."""
    head, _ = _bullet(page, block)
    first, *rest = _LINE_BREAK.split(text)
    wrapped = (
        page.document.lines[block.start + 1].indent if block.content_end > block.start + 1 else block.prefix + "  "
    )
    texts = (head + first if first else head.rstrip(" \t"), *(wrapped + line for line in rest))
    current = tuple(line.indent + line.content for line in page.document.lines[block.start : block.content_end])
    if texts == current:
        return None
    return _keeping_outline(page, block, splice.Edit(block.start, block.content_end, texts))


def _keeping_outline(page: blocks.Page, block: blocks.Block, edit: splice.Edit) -> splice.Edit:
    """The edit, unless the new content would parse as more than this block's content span.

    A line of new text that reads as a bullet, a property, a drawer or an open
    code fence would restructure the page, which no content write may do.
    """
    after = blocks.parse(splice.apply(page.document, [edit]))
    span = block.content_end - block.start
    new_span = span - (edit.end - edit.start) + len(edit.texts)

    def shape(found: blocks.Block, cut: int) -> tuple:
        return found.depth, found.parent, found.kinds[cut:]

    same = len(after.blocks) == len(page.blocks) and all(
        shape(new, new_span if new.index == block.index else 0) == shape(old, span if old.index == block.index else 0)
        for new, old in zip(after.blocks, page.blocks, strict=False)
    )
    if not same or after.blocks[block.index].content_end - block.start != new_span:
        raise Refusal(BAD_ARGUMENTS, "the text would change the outline, not only this block's content")
    return edit


def parse_marker(text: str) -> str | None:
    """A marker to set, or None for `none`, refusing anything outside Logseq's seven."""
    if text == _NONE:
        return None
    if text not in blocks.MARKERS:
        raise Refusal(BAD_ARGUMENTS, f"{text}: not one of {', '.join(blocks.MARKERS)}, or {_NONE}")
    return text


def plan_set_marker(page: blocks.Page, block: blocks.Block, marker: str | None) -> splice.Edit | None:
    """Replace, add or remove the marker word at the start of the block's text."""
    if block.marker == marker:
        return None
    head, text = _bullet(page, block)
    rest = text[len(block.marker) :].lstrip(" ") if block.marker else text
    new = " ".join(word for word in (marker, rest) if word)
    edit = splice.Edit(block.start, block.start + 1, ((head + new) if new else head.rstrip(" \t"),))
    return _keeping_outline(page, block, edit)


def run(target: targets.Target, edit: splice.Edit | None, *, dry_run: bool) -> None:
    """Write the edit to the target's file, or print it as a diff with `dry_run`. No edit writes nothing."""
    if edit is None:
        return
    before = target.page.document.to_bytes()
    after = splice.apply(target.page.document, [edit]).to_bytes()
    if dry_run:
        sys.stdout.write(splice.diff(_shown(target.path), before, after))
        return
    splice.commit(target.path, before, after)


def _shown(path: Path) -> Path:
    try:
        return path.relative_to(Path.cwd())
    except ValueError:
        return path
