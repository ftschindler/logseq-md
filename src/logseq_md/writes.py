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
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from logseq_md import blocks, identity, splice, targets
from logseq_md.exits import BAD_ARGUMENTS, Refusal
from logseq_md.graph import Graph
from logseq_md.lines import Document

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


def check_key(key: str) -> None:
    """Refuse a key Logseq would not read as one, and `id`, which only ensure-id writes."""
    if not _KEY.fullmatch(key):
        raise Refusal(BAD_ARGUMENTS, f"{key!r}: not a property key Logseq would read")
    if key.lower() == identity.ID:
        raise Refusal(BAD_ARGUMENTS, f"{key}: a block's id is given by ensure-id, never set")


def carrying(block: blocks.Block, key: str) -> blocks.Property | None:
    """The block's one property line with `key`, None without one, refusing when there are several."""
    found = [prop for prop in block.properties if prop.key == key]
    if len(found) > 1:
        raise Refusal(
            BAD_ARGUMENTS, f"{key}: on {len(found)} lines of this block: " + ", ".join(str(p.line + 1) for p in found)
        )
    return found[0] if found else None


def plan_set_property(page: blocks.Page, block: blocks.Block, key: str, value: str) -> splice.Edit | None:
    """Replace the value on the line carrying `key`, or insert one after the last property."""
    check_key(key)
    if _LINE_BREAK.search(value):
        raise Refusal(BAD_ARGUMENTS, "a property value is one line")
    prop = carrying(block, key)
    found = [prop] if prop else []
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
    run_edits(target.path, target.page, [] if edit is None else [edit], dry_run=dry_run)


def run_edits(path: Path, page: blocks.Page, edits: list[splice.Edit], *, dry_run: bool, create: bool = False) -> None:
    """Write every edit to `path` in one splice, or print the diff. `create` writes a file that is not there yet."""
    if not edits:
        return
    before = page.document.to_bytes()
    after = splice.apply(page.document, edits).to_bytes()
    if dry_run:
        sys.stdout.write(splice.diff(_shown(path), before, after))
    elif create:
        splice.create(path, after)
    else:
        splice.commit(path, before, after)


# append-child (DESIGN.md section 7, "Position" and "Indentation on insert")

_LAST_UNIT = re.compile(r"(\t| +)$")
_DEFAULT_STEP = "\t"


@dataclass(frozen=True)
class Append:
    """Where an append-child goes: a file, its page (empty when `create`), and the parent block or None for the page."""

    path: Path
    page: blocks.Page
    parent: int | None
    create: bool = False


def append_target(graph: Graph, text: str, *, create: bool) -> Append:
    """Resolve append-child's target: a block by id, a page, or a journal date, made with `create` if absent."""
    if create:
        day = targets.iso_date(text.strip())
        if day is None:
            raise Refusal(BAD_ARGUMENTS, f"{text}: --create makes a journal, so it takes a date written YYYY-MM-DD")
        path = graph.journal_path(day)
        if not path.exists():
            return Append(path, blocks.parse(Document(())), None, create=True)
    target = targets.resolve(graph, text, write=True)
    blank = not any(line.indent or line.content for line in target.page.document.lines)
    if not (target.page.outline or blank):
        raise Refusal(BAD_ARGUMENTS, f"{target.path}: has no outline, so no block in it can be written")
    return Append(target.path, target.page, target.block)


def _subtree_end(page: blocks.Page, block: blocks.Block) -> int:
    while block.children:
        block = page.blocks[block.children[-1]]
    return block.end


def child_prefix(page: blocks.Page, parent: blocks.Block | None) -> str:
    """The prefix a new child takes, copied from the file rather than computed by a rule.

    An existing child's prefix; else the most common child prefix under any block
    with the parent's own prefix; else the parent's prefix extended by what it ends
    in, a tab or its trailing run of spaces. A top-level block copies the last
    top-level bullet, and a root with no evidence at its depth takes a tab, as
    Logseq does.
    """
    if parent is None:
        return page.blocks[page.roots[-1]].prefix if page.outline else ""
    if parent.children:
        return page.blocks[parent.children[-1]].prefix
    seen = Counter(
        page.blocks[other.children[-1]].prefix
        for other in page.blocks
        if other.children and other.prefix == parent.prefix
    )
    if seen:
        return seen.most_common(1)[0][0]
    unit = _LAST_UNIT.search(parent.prefix)
    return parent.prefix + (unit.group(1) if unit else _DEFAULT_STEP)


def plan_append_child(
    page: blocks.Page,
    parent: blocks.Block | None,
    text: str,
    *,
    child_id: str | None = None,
    record_as: str | None = None,
) -> list[splice.Edit]:
    """The edits appending `text` as the parent's last child, or the page's last top-level block.

    With `record_as`, `child_id` goes on the new block as its id, and on the
    parent as the value of the property named by `record_as`, in the same
    splice. The result is re-parsed, and refused when it would be anything but
    one new block exactly where it was meant to go.
    """
    prefix = child_prefix(page, parent)
    first, *rest = _LINE_BREAK.split(text)
    texts = [f"{prefix}- {first}" if first else f"{prefix}-", *(f"{prefix}  {line}" for line in rest)]
    if child_id is not None:
        texts.append(f"{prefix}  {_property_text(identity.ID, child_id)}")
    # Blank lines belong to the block above them, so the new block goes after them too.
    end = len(page.document.lines) if parent is None else _subtree_end(page, parent)
    owned: splice.Edit | None = None
    record: tuple[str, str] | None = None
    if record_as is not None:
        assert parent is not None and child_id is not None
        record = (record_as, child_id)
        owned = plan_set_property(page, parent, record_as, child_id)
        assert owned is not None and owned.start == owned.end
    if owned is None:
        edits = [splice.Edit(end, end, tuple(texts))]
    elif owned.start == end:
        edits = [splice.Edit(end, end, owned.texts + tuple(texts))]
    else:
        edits = [owned, splice.Edit(end, end, tuple(texts))]
    placed = (end + (len(owned.texts) if owned else 0), len(texts))
    _one_new_child(page, parent, edits, placed, record)
    return edits


def _one_new_child(
    page: blocks.Page,
    parent: blocks.Block | None,
    edits: list[splice.Edit],
    placed: tuple[int, int],
    record: tuple[str, str] | None,
) -> None:
    """Refuse unless the edits add one block, `placed` as (first line, line count), under `parent`, and no other shape.

    `record` is the key and the child's id, which the child carries as its id and the parent under the key.
    """
    start, size = placed
    after = blocks.parse(splice.apply(page.document, edits))
    new = next((block for block in after.blocks if block.start == start), None)
    refusal = Refusal(BAD_ARGUMENTS, "the text would change the outline, not only add one block")
    if new is None or len(after.blocks) != len(page.blocks) + 1:
        raise refusal
    kinds = (blocks.Kind.BULLET, *[blocks.Kind.CONTENT] * (size - 1 - (record is not None)))
    if record is not None:
        kinds += (blocks.Kind.PROPERTY,)
    if new.kinds != kinds or new.parent != (None if parent is None else parent.index) or new.children:
        raise refusal

    def moved(index: int) -> int:
        return index + (index >= new.index)

    for old in page.blocks:
        now = after.blocks[moved(old.index)]
        if (now.depth, now.parent) != (old.depth, None if old.parent is None else moved(old.parent)):
            raise refusal
        if (parent is None or old.index != parent.index) and now.kinds != old.kinds:
            raise refusal
    if record is not None:
        assert parent is not None
        recorded = carrying(after.blocks[parent.index], record[0])
        if recorded is None or recorded.value.strip() != record[1]:
            raise refusal


def _shown(path: Path) -> Path:
    try:
        return path.relative_to(Path.cwd())
    except ValueError:
        return path
