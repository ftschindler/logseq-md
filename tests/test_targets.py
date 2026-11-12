"""Minting ids, scanning a graph for them, and resolving every target form (DESIGN.md sections 5 and 10)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest

from logseq_md import identity
from logseq_md.exits import BAD_ARGUMENTS, NOT_FOUND, Refusal
from logseq_md.graph import open_graph
from logseq_md.targets import Target, resolve

GRAPH = Path(__file__).resolve().parent / "fixtures" / "targets" / "graph"
PAGES, JOURNALS = GRAPH / "pages", GRAPH / "journals"

BEAN_JARS = "6512bd43-7a1c-4e2b-9f3d-1a2b3c4d5e6f"
LEAF_MOULD = "67c0f1a0-2b3c-4d5e-8f90-a1b2c3d4e5f6"
MEETING_PAGE = "65f0a3c2-4d5e-4f60-8a71-b2c3d4e5f607"
DUPLICATED = "67c1a000-1111-4222-8333-444455556666"


@pytest.fixture(scope="module")
def graph():
    return open_graph(str(GRAPH), {})


def first_line(target: Target) -> str:
    assert target.block is not None
    return target.page.document.lines[target.page.blocks[target.block].start].content


def refusal(graph, text: str, *, write: bool = False) -> Refusal:
    with pytest.raises(Refusal) as refused:
        resolve(graph, text, write=write)
    return refused.value


class TestMint:
    def test_the_prefix_is_the_clock_in_seconds_and_the_version_is_4(self) -> None:
        moment = datetime(2023, 9, 4, 12, 0, 0, tzinfo=UTC).timestamp()
        minted = identity.mint(clock=lambda: moment + 0.75)
        assert minted[:8] == f"{int(moment):08x}" == "64f5c6c0"
        assert uuid.UUID(minted).version == 4
        assert minted[14] == "4"

    def test_the_rest_is_the_random_uuid(self) -> None:
        random = uuid.UUID("0123abcd-89ab-4cde-8f01-23456789abcd")
        assert identity.mint(clock=lambda: 0, random=lambda: random) == "00000000-89ab-4cde-8f01-23456789abcd"

    def test_two_mints_in_one_second_differ(self) -> None:
        assert identity.mint(clock=lambda: 1) != identity.mint(clock=lambda: 1)


class TestScan:
    def test_maps_block_and_page_ids_to_where_they_live(self, graph) -> None:
        found = identity.scan(graph).found
        (bean,) = found[BEAN_JARS]
        assert (bean.path, bean.line) == (PAGES / "Seed Library.md", 2)
        (meeting,) = found[MEETING_PAGE]
        assert (meeting.path, meeting.block) == (PAGES / "Meeting%3A2.md", None)

    def test_reports_an_id_two_blocks_carry(self, graph) -> None:
        duplicates = identity.scan(graph).duplicates()
        assert list(duplicates) == [DUPLICATED]
        assert {where.path for where in duplicates[DUPLICATED]} == {
            PAGES / "Compost Bins.md",
            JOURNALS / "2025_03_01.md",
        }


class TestUuid:
    def test_resolves_to_the_block(self, graph) -> None:
        target = resolve(graph, BEAN_JARS)
        assert target.path == PAGES / "Seed Library.md"
        assert first_line(target) == "- TODO label the bean jars"

    def test_compares_without_case(self, graph) -> None:
        assert resolve(graph, LEAF_MOULD.upper()).path == JOURNALS / "2025_02_28.md"

    def test_a_page_level_id_resolves_to_the_page(self, graph) -> None:
        target = resolve(graph, MEETING_PAGE)
        assert (target.path, target.block) == (PAGES / "Meeting%3A2.md", None)

    def test_a_missing_id_is_not_found(self, graph) -> None:
        assert refusal(graph, "00000000-0000-4000-8000-000000000000").code == NOT_FOUND

    def test_a_duplicated_id_is_refused_naming_both_blocks(self, graph) -> None:
        refused = refusal(graph, DUPLICATED)
        assert refused.code == BAD_ARGUMENTS
        assert f"{PAGES / 'Compost Bins.md'}:1" in refused.message
        assert f"{JOURNALS / '2025_03_01.md'}:1" in refused.message


class TestDate:
    def test_an_iso_date_is_its_journal(self, graph) -> None:
        target = resolve(graph, "2025-02-28")
        assert (target.path, target.block) == (JOURNALS / "2025_02_28.md", None)

    def test_a_journal_title_is_a_page_name(self, graph) -> None:
        assert resolve(graph, "feb 28th, 2025").path == JOURNALS / "2025_02_28.md"

    def test_a_date_with_no_journal_is_not_found(self, graph) -> None:
        refused = refusal(graph, "2025-03-02")
        assert refused.code == NOT_FOUND
        assert "2025_03_02.md" in refused.message

    def test_an_impossible_date_is_tried_as_a_page_name(self, graph) -> None:
        assert refusal(graph, "2025-02-30").code == NOT_FOUND


class TestPageName:
    def test_compares_without_case(self, graph) -> None:
        target = resolve(graph, "seed library")
        assert (target.path, target.block) == (PAGES / "Seed Library.md", None)

    def test_a_colon_in_a_title_is_not_a_line_number(self, graph) -> None:
        assert resolve(graph, "Meeting:2").path == PAGES / "Meeting%3A2.md"

    def test_an_unknown_page_is_not_found(self, graph) -> None:
        assert refusal(graph, "Greenhouse").code == NOT_FOUND

    def test_a_name_two_files_hold_is_refused_naming_both(self, graph) -> None:
        refused = refusal(graph, "orchard/pruning")
        assert refused.code == BAD_ARGUMENTS
        assert str(PAGES / "Orchard___Pruning.md") in refused.message
        assert str(PAGES / "Orchard%2FPruning.md") in refused.message


class TestPageLine:
    def test_the_bullet_line_is_the_block(self, graph) -> None:
        assert first_line(resolve(graph, "Seed Library:2")) == "- TODO label the bean jars"

    def test_a_property_line_is_its_block(self, graph) -> None:
        assert first_line(resolve(graph, "Seed Library:3")) == "- TODO label the bean jars"

    def test_a_child_line_is_the_child(self, graph) -> None:
        assert first_line(resolve(graph, "Seed Library:4")) == "- sort them by sowing month"

    def test_a_preamble_line_is_the_page(self, graph) -> None:
        assert resolve(graph, "Seed Library:1").block is None

    def test_a_journal_title_takes_a_line(self, graph) -> None:
        assert first_line(resolve(graph, "Feb 28th, 2025:1")) == "- picked up two bags of leaf mould"

    @pytest.mark.parametrize("line", ["0", "6"])
    def test_a_line_outside_the_file_is_not_found(self, graph, line: str) -> None:
        assert refusal(graph, f"Seed Library:{line}").code == NOT_FOUND

    def test_a_write_is_refused_naming_ensure_id(self, graph) -> None:
        refused = refusal(graph, "Seed Library:2", write=True)
        assert refused.code == BAD_ARGUMENTS
        assert "ensure-id" in refused.message

    def test_a_write_still_takes_a_uuid(self, graph) -> None:
        assert resolve(graph, BEAN_JARS, write=True).path == PAGES / "Seed Library.md"

    def test_on_a_name_two_files_hold_is_refused(self, graph) -> None:
        assert refusal(graph, "Orchard/Pruning:1").code == BAD_ARGUMENTS
