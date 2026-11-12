"""The mutation half of the gate (DESIGN.md section 9).

For every block in every fixture, plan one write of each kind, apply it, and
assert that every byte outside the spliced line range is unchanged and that the
page still parses to the same number of blocks. One of them, `ensure-id`, is
committed to a temporary copy of the file, so the bytes asserted are the bytes
on disk. `append-child`, with and without `--record-as`, is planned under every
block and page, and must add lines and change nothing else, with every new
child's prefix equal to its siblings'.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from logseq_md import blocks, splice, writes
from logseq_md.exits import Refusal
from logseq_md.lines import Document, read

FIXTURES = Path(__file__).resolve().parent / "fixtures"
MINTED = "6a5f0000-1111-4222-8333-444444444444"


def _outlines() -> list[Path]:
    found = []
    for path in sorted(FIXTURES.rglob("*.md")):
        try:
            page = blocks.parse(read(path))
        except Refusal:
            continue
        if page.outline:
            found.append(path)
    return found


OUTLINES = _outlines()

Plan = Callable[[blocks.Page, blocks.Block], "splice.Edit | None"]
PLANS: dict[str, Plan] = {
    "ensure-id": lambda page, block: writes.plan_ensure_id(page, block, lambda: MINTED)[1],
    "set-property": lambda page, block: writes.plan_set_property(page, block, "gate-key", "gate value"),
    "set-content": lambda page, block: writes.plan_set_content(page, block, "gate text\nwrapped"),
    "set-marker": lambda page, block: writes.plan_set_marker(page, block, "DONE" if block.marker != "DONE" else None),
}


def _offset(document: Document, line: int) -> int:
    head = len(document.to_bytes()) - len(b"".join(item.text().encode() for item in document.lines))
    return head + sum(len(item.text().encode()) for item in document.lines[:line])


def test_there_are_outlines_to_mutate() -> None:
    assert len(OUTLINES) > 10


@pytest.mark.parametrize("path", OUTLINES, ids=lambda path: path.relative_to(FIXTURES).as_posix())
@pytest.mark.parametrize("verb", PLANS)
def test_a_write_changes_only_its_own_lines(path: Path, verb: str) -> None:
    page = blocks.parse(read(path))
    before = page.document.to_bytes()
    planned = 0
    for block in page.blocks:
        try:
            edit = PLANS[verb](page, block)
        except Refusal:
            continue  # a refusal writes nothing, which is the property under test
        if edit is None:
            continue
        planned += 1
        after = splice.apply(page.document, [edit]).to_bytes()
        assert after.startswith(before[: _offset(page.document, edit.start)])
        assert after.endswith(before[_offset(page.document, edit.end) :])
        assert len(blocks.parse(splice.apply(page.document, [edit])).blocks) == len(page.blocks)
    assert planned or verb == "ensure-id"


@pytest.mark.parametrize("path", OUTLINES, ids=lambda path: path.relative_to(FIXTURES).as_posix())
def test_ensure_id_on_disk_changes_only_the_new_line(path: Path, tmp_path: Path) -> None:
    original = path.read_bytes()
    copy = tmp_path / path.name
    for index in range(len(blocks.parse(read(path)).blocks)):
        copy.write_bytes(original)
        page = blocks.parse(read(copy))
        try:
            _, edit = writes.plan_ensure_id(page, page.blocks[index], lambda: MINTED)
        except Refusal:
            continue
        if edit is None:
            continue
        splice.commit(copy, original, splice.apply(page.document, [edit]).to_bytes())
        written = copy.read_bytes()
        cut = _offset(page.document, edit.start)
        assert written.startswith(original[:cut])
        assert written.endswith(original[cut:])
        assert written.count(MINTED.encode()) == original.count(MINTED.encode()) + 1


@pytest.mark.parametrize("path", OUTLINES, ids=lambda path: path.relative_to(FIXTURES).as_posix())
@pytest.mark.parametrize("record", [False, True], ids=["append-child", "record-as"])
def test_an_append_inserts_lines_and_changes_nothing_else(path: Path, record: bool) -> None:
    page = blocks.parse(read(path))
    before = b"".join(line.text().encode() for line in page.document.lines)
    for parent in [*page.blocks, None]:
        if parent is None and record:
            continue
        options = {"child_id": MINTED, "record_as": "gate-key"} if record else {}
        try:
            edits = writes.plan_append_child(page, parent, "gate text\nwrapped", **options)
        except Refusal:
            continue
        after = blocks.parse(splice.apply(page.document, edits))
        added = {start + offset for start, size in _inserted(edits) for offset in range(size)}
        kept = b"".join(line.text().encode() for i, line in enumerate(after.document.lines) if i not in added)
        # The one byte change a splice may make: a last line without an ending gains one.
        assert kept == before or (kept.rstrip(b"\r\n") == before and not before.endswith((b"\n", b"\r")))
        if parent is not None and parent.children:
            child = next(b for b in after.blocks if b.parent == parent.index and b.index > parent.children[-1])
            assert child.prefix == page.blocks[parent.children[-1]].prefix


def _inserted(edits: list[splice.Edit]) -> list[tuple[int, int]]:
    """Each edit's new lines as (first index in the new document, count). Append edits replace nothing."""
    out, shift = [], 0
    for edit in sorted(edits, key=lambda edit: edit.start):
        out.append((edit.start + shift, len(edit.texts)))
        shift += len(edit.texts) - (edit.end - edit.start)
    return out
