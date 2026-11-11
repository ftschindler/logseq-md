"""The block model (DESIGN.md section 4): structure alongside the lines, never in their place."""

from __future__ import annotations

from pathlib import Path

import pytest

from logseq_md.blocks import Block, Kind, Page, Property, Reference, RefKind, parse
from logseq_md.lines import read

FIXTURES = Path(__file__).resolve().parent / "fixtures"
BLOCKS = FIXTURES / "blocks"


def _utf8(path: Path) -> bool:
    with path.open("rb") as handle:
        data = handle.read()
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return True


ALL = [path for path in sorted(FIXTURES.rglob("*.md")) if _utf8(path)]


def page(name: str) -> Page:
    return parse(read(BLOCKS / name))


def text(page: Page, number: int) -> str:
    line = page.document.lines[number]
    return line.indent + line.content


def by_text(page: Page, start: str) -> Block:
    return next(
        block for block in page.blocks if text(page, block.start).lstrip(" \t").removeprefix("- ").startswith(start)
    )


def kinds(page: Page, block: Block) -> list[tuple[str, Kind]]:
    return [(text(page, block.start + offset).strip(), kind) for offset, kind in enumerate(block.kinds)]


@pytest.mark.parametrize("path", ALL, ids=lambda path: path.relative_to(FIXTURES).as_posix())
def test_preamble_and_blocks_tile_the_file(path: Path) -> None:
    parsed = parse(read(path))
    covered = list(range(parsed.preamble_end))
    assert len(parsed.preamble_kinds) == parsed.preamble_end
    for block in parsed.blocks:
        assert block.start == (covered[-1] + 1 if covered else 0)
        assert block.end - block.start == len(block.kinds)
        assert block.kinds[0] is Kind.BULLET
        assert Kind.BULLET not in block.kinds[1:]
        covered += range(block.start, block.end)
    assert covered == list(range(len(parsed.document.lines)))


@pytest.mark.parametrize("path", ALL, ids=lambda path: path.relative_to(FIXTURES).as_posix())
def test_parent_and_children_link_both_ways(path: Path) -> None:
    parsed = parse(read(path))
    for block in parsed.blocks:
        for child in block.children:
            assert parsed.blocks[child].parent == block.index
            assert parsed.blocks[child].depth == block.depth + 1
        if block.parent is None:
            assert block.depth == 1
        else:
            assert block.index in parsed.blocks[block.parent].children


def test_tabs_nest_nine_deep_and_return_to_the_root() -> None:
    parsed = page("tabs-nine-deep.md")
    assert [block.depth for block in parsed.blocks] == [*range(1, 10), 1]
    assert [block.parent for block in parsed.blocks] == [None, *range(8), None]
    assert parsed.roots == (0, 9)


def test_two_spaces_nest_like_a_tab() -> None:
    parsed = page("spaces.md")
    assert [block.depth for block in parsed.blocks] == [1, 2, 3, 2, 1]
    assert parsed.blocks[0].children == (1, 3)


def test_a_prefix_mixing_tabs_and_spaces_nests_by_its_width() -> None:
    parsed = page("mixed-prefix.md")
    depths = {text(parsed, block.start).strip(): block.depth for block in parsed.blocks}
    assert depths == {
        "- mixed prefixes for the canoe trip": 1,
        "- paddles": 2,
        "- spare blade": 3,
        "- shaped TAB TAB SP SP": 4,
        "- shaped TAB TAB SP SP SP SP": 5,
        "- shaped TAB SP SP": 3,
        "- shaped TAB TAB TAB SP SP": 4,
        "- life jackets": 2,
    }
    assert (
        parsed.blocks[by_text(parsed, "shaped TAB TAB TAB SP SP").index].parent
        == by_text(parsed, "shaped TAB SP SP").index
    )


def test_properties_are_recognised_by_shape_at_any_indent_and_kept_as_found() -> None:
    parsed = page("properties.md")
    first = parsed.blocks[0]
    assert [(prop.key, prop.value) for prop in first.properties] == [
        ("id", "6a10c2f4-1e2d-4b3a-9c8d-7e6f5a4b3c21"),
        ("collapsed", "true"),
        ("fern-colour", "moss green"),
        ("empty-note", ""),
        ("kiln.firing-cone", "six"),
    ]
    assert first.content_end == first.start + 1
    deeper = by_text(parsed, "a deviant property indent")
    level = by_text(parsed, "a deviant indent at the bullet's own prefix")
    assert [prop.key for prop in deeper.properties] == ["tuning-fork"]
    assert [prop.key for prop in level.properties] == ["sprocket"]
    assert deeper.children == ()


def test_continuation_lines_keep_whatever_order_they_were_written_in() -> None:
    parsed = page("continuation-orders.md")
    shapes = [
        " > ".join(
            "id" if t.startswith("id::") else "collapsed" if t.startswith("collapsed::") else t.split()[0]
            for t, kind in kinds(parsed, block)[1:]
            if kind is not Kind.DRAWER or t == ":LOGBOOK:"
        )
        for block in parsed.blocks
    ]
    assert shapes == [
        "id > collapsed",
        "id > DEADLINE:",
        "id > SCHEDULED:",
        "DEADLINE: > SCHEDULED:",
        "SCHEDULED: > DEADLINE:",
        "DEADLINE: > :LOGBOOK:",
        "collapsed > DEADLINE:",
        "collapsed > DEADLINE: > :LOGBOOK:",
        "collapsed > :LOGBOOK:",
        "DEADLINE: > id > :LOGBOOK:",
        "id > DEADLINE: > SCHEDULED:",
        "id > SCHEDULED: > DEADLINE:",
        "id > DEADLINE: > :LOGBOOK:",
        "DEADLINE: > DEADLINE:",
        "id > collapsed > DEADLINE:",
        "collapsed > SCHEDULED: > DEADLINE:",
        "SCHEDULED: > :LOGBOOK:",
    ]
    assert all(block.content_end == block.start + 1 for block in parsed.blocks)


def test_the_content_span_is_the_bullet_and_its_wrapped_lines_up_to_the_first_property() -> None:
    parsed = page("wrapped.md")
    kite, spars = parsed.blocks
    assert kinds(parsed, kite) == [
        ("- the kite string first line", Kind.BULLET),
        ("wraps onto a second line", Kind.CONTENT),
        ("and a third about the tail", Kind.CONTENT),
        ("id:: 6a10c2f4-1e2d-4b3a-9c8d-7e6f5a4b3c30", Kind.PROPERTY),
        ("a line after the property that is not in the span", Kind.CONTENT),
    ]
    assert kite.content_end == kite.start + 3
    assert spars.content_end == spars.start + 1
    assert kinds(parsed, spars)[1:] == [
        ("DEADLINE: <2031-03-01 Sat>", Kind.SCHEDULING),
        ("a line after the deadline", Kind.CONTENT),
    ]


def test_markers_are_the_seven_and_only_as_a_whole_word() -> None:
    parsed = page("tasks.md")
    assert [block.marker for block in parsed.blocks] == [
        "TODO",
        "DOING",
        "DONE",
        "LATER",
        "NOW",
        "WAITING",
        "CANCELED",
        None,
        None,
        "TODO",
        "DONE",
        "WAITING",
    ]


def test_drawers_run_to_their_end_whatever_their_name() -> None:
    parsed = page("tasks.md")
    planed = by_text(parsed, "DONE plane")
    assert planed.kinds[1:] == (Kind.DRAWER,) * 6
    waiting = by_text(parsed, "WAITING on")
    assert waiting.kinds[1:] == (Kind.SCHEDULING, Kind.DRAWER, Kind.DRAWER, Kind.DRAWER)
    assert waiting.properties == ()


def test_a_fenced_line_is_content_however_it_looks() -> None:
    parsed = page("fences.md")
    assert parsed.preamble_kinds == (Kind.PROSE,) * 4
    assert [text(parsed, block.start).strip() for block in parsed.blocks] == [
        "- ```python",
        "- a block with a tilde fence below",
        "- a longer fence closes only on its own length",
    ]
    backtick, tilde, longer = parsed.blocks
    assert backtick.kinds[1:] == (Kind.CONTENT,) * 4
    assert backtick.properties == ()
    assert [prop.key for prop in tilde.properties] == ["real-key"]
    assert tilde.kinds[1:] == (*(Kind.CONTENT,) * 5, Kind.PROPERTY)
    assert longer.kinds[1:] == (Kind.CONTENT,) * 4
    assert [(fence.start, fence.stop) for fence in parsed.fences] == [(1, 4), (4, 9), (10, 15), (17, 21)]


def test_a_fence_that_never_closes_runs_to_the_end_of_the_file() -> None:
    parsed = page("unclosed-fence.md")
    assert len(parsed.blocks) == 1
    assert parsed.blocks[0].properties == ()
    assert [(fence.start, fence.stop) for fence in parsed.fences] == [(1, 4)]


def test_references_are_found_with_their_positions_and_not_in_property_values() -> None:
    parsed = page("references.md")
    (block,) = parsed.blocks
    assert block.references == (
        Reference(RefKind.PAGE, "Birdwatching Log", 0, 6),
        Reference(RefKind.TAG, "heron", 0, 31),
        Reference(RefKind.TAG, "wading birds", 0, 42),
        Reference(RefKind.BLOCK, "6a10c2f4-1e2d-4b3a-9c8d-7e6f5a4b3c21", 1, 7),
        Reference(RefKind.EMBED, "6a10c2f4-1e2d-4b3a-9c8d-7e6f5a4b3c22", 1, 52),
    )
    line = text(parsed, 0)
    assert line[6:].startswith("[[Birdwatching Log]]")
    assert line[31:].startswith("#heron")
    assert line[42:].startswith("#[[wading birds]]")
    assert text(parsed, 1)[52:].startswith("{{embed ((")


@pytest.mark.parametrize(
    ("name", "kinds_"),
    [
        ("page-properties-only.md", (Kind.PAGE_PROPERTY,) * 3),
        ("prose-only.md", (Kind.PROSE,) * 3),
        ("properties-and-prose.md", (Kind.PAGE_PROPERTY, Kind.PROSE)),
    ],
)
def test_a_page_with_no_bullet_has_no_outline(name: str, kinds_: tuple[Kind, ...]) -> None:
    parsed = page(name)
    assert not parsed.outline
    assert parsed.blocks == ()
    assert parsed.preamble_kinds == kinds_


def test_page_properties_before_an_outline_belong_to_the_page() -> None:
    parsed = page("page-properties-then-outline.md")
    assert parsed.outline
    assert parsed.page_properties == (Property(0, "lantern-type", "storm"), Property(1, "lantern-fuel", "paraffin"))
    assert parsed.preamble_end == 3
    assert [block.depth for block in parsed.blocks] == [1, 2]


def test_blank_lines_belong_to_the_block_above_and_do_not_end_it() -> None:
    parsed = page("blank-lines.md")
    first, second, child = parsed.blocks
    assert first.kinds == (Kind.BULLET, Kind.CONTENT, Kind.CONTENT)
    assert first.content_end == first.end
    assert second.children == (child.index,)
    assert child.end == len(parsed.document.lines)


def test_crlf_endings_do_not_reach_the_structure() -> None:
    parsed = page("crlf.md")
    route, ferry = parsed.blocks
    assert route.properties == (Property(1, "ferry-route", "harbour loop"),)
    assert ferry.marker == "DONE"
    assert ferry.parent == route.index


def test_an_indent_that_jumps_levels_nests_one_level() -> None:
    parsed = page("indent-jump.md")
    assert [block.depth for block in parsed.blocks] == [1, 2, 2, 2, 3]
    assert parsed.blocks[0].children == (1, 2, 3)
    assert parsed.blocks[4].parent == 3
