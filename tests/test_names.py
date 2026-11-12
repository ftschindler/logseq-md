"""Page names, filenames and journal dates (DESIGN.md section 4, "Pages, journals and namespaces")."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from logseq_md import names
from logseq_md.graph import Graph, read_config

GRAPHS = Path(__file__).resolve().parent / "fixtures" / "graphs"
NAMED = ("triple-lowbar", "legacy", "awkward-config", "unreadable-config")

#: Every escaping variant in the triple-lowbar fixture, and the page name it holds.
TRIPLE_LOWBAR = {
    "Orchard___Pruning___Winter": "Orchard/Pruning/Winter",
    "pear_grafting": "pear_grafting",
    "Seed Trays": "Seed Trays",
    "Hydrometer v2.3": "Hydrometer v2.3",
    "Gew\u00e4chshaus": "Gew\u00e4chshaus",
    "Ratio%3A Flour to Water": "Ratio: Flour to Water",
    "Why%3F Not%2A": "Why? Not*",
    "Bucket %23 Seven": "Bucket # Seven",
    "%2Edotfile habit": ".dotfile habit",
    "AUX___": "AUX",
    "Draft v1.___": "Draft v1.",
    "snake%5F%5F%5Fcase": "snake___case",
    "Alpha%5F___Beta": "Alpha_/Beta",
    "50% Rye": "50% Rye",
    "%2525 Margin": "%25 Margin",
}

LEGACY = {
    "Orchard%2FPruning": "Orchard/Pruning",
    "Ratio%3A Flour": "Ratio: Flour",
    "Bucket %23 Nine": "Bucket # Nine",
    "pear_grafting": "pear_grafting",
}


def graph(name: str) -> Graph:
    root = GRAPHS / name
    return Graph(root, read_config(root))


@pytest.mark.parametrize("name", NAMED)
def test_every_fixture_filename_maps_to_a_name_or_date_and_back(name: str) -> None:
    model = graph(name)
    files = list(model.files())
    assert files
    for path in files:
        if model.is_journal(path):
            day = model.journal_date(path)
            assert day is not None, path.name
            assert model.journal_path(day) == path
        else:
            assert model.page_path(model.page_name(path)) == path, path.name


@pytest.mark.parametrize(("body", "page"), TRIPLE_LOWBAR.items())
def test_triple_lowbar_names(body: str, page: str) -> None:
    assert (GRAPHS / "triple-lowbar" / "pages" / f"{body}.md").is_file()
    assert names.file_body_to_page(body, names.TRIPLE_LOWBAR) == page
    assert names.page_to_file_body(page, names.TRIPLE_LOWBAR) == body


def test_the_triple_lowbar_table_covers_the_fixture() -> None:
    assert {path.stem for path in (GRAPHS / "triple-lowbar" / "pages").iterdir()} == set(TRIPLE_LOWBAR)


@pytest.mark.parametrize(("body", "page"), LEGACY.items())
def test_legacy_names(body: str, page: str) -> None:
    assert (GRAPHS / "legacy" / "pages" / f"{body}.md").is_file()
    assert names.file_body_to_page(body, names.LEGACY) == page
    assert names.page_to_file_body(page, names.LEGACY) == body


def test_a_legacy_dot_reads_as_a_namespace() -> None:
    # Logseq's own rule for the format before triple lowbars; it does not survive the trip back.
    assert names.file_body_to_page("Kitchen.Knives", names.LEGACY) == "Kitchen/Knives"


def test_boundary_slashes_and_empty_namespaces_are_dropped() -> None:
    assert names.page_to_file_body("/Orchard/", names.TRIPLE_LOWBAR) == "Orchard"
    assert names.file_body_to_page("___Orchard______Pear", names.TRIPLE_LOWBAR) == "Orchard/Pear"


def test_page_names_compare_case_insensitively_after_normalising() -> None:
    assert names.same_page("Seed Trays", "seed trays")
    assert names.same_page("Gew\u00e4chshaus", "gewa\u0308chshaus")
    assert not names.same_page("Seed Trays", "Seed Tray")


def test_a_journal_converts_both_ways_under_the_defaults() -> None:
    model = graph("triple-lowbar")
    path = model.root / "journals" / "2025_02_28.md"
    assert model.journal_date(path) == date(2025, 2, 28)
    assert model.page_name(path) == "Feb 28th, 2025"
    assert model.config.journal_title.parse("Feb 28th, 2025") == date(2025, 2, 28)


def test_a_journal_converts_under_custom_formats() -> None:
    model = graph("awkward-config")
    path = model.root / "journals" / "2024-12-31.md"
    assert model.journal_date(path) == date(2024, 12, 31)
    assert model.page_name(path) == "Tuesday, December 31st of 2024"
    assert model.config.journal_title.parse("Tuesday, December 31st of 2024") == date(2024, 12, 31)


@pytest.mark.parametrize(
    ("pattern", "text"),
    [("yyyy_MM_dd", "2025_02_30"), ("yyyy_MM_dd", "2025_2_28"), ("MMM do, yyyy", "Feb 28nd, 2025")],
)
def test_a_name_that_is_not_a_date_parses_to_none(pattern: str, text: str) -> None:
    assert names.DateFormat(pattern).parse(text) is None


@pytest.mark.parametrize(
    ("day", "ordinal"), [(1, "1st"), (2, "2nd"), (3, "3rd"), (4, "4th"), (11, "11th"), (22, "22nd")]
)
def test_ordinals(day: int, ordinal: str) -> None:
    assert names.DateFormat("do").format(date(2025, 1, day)) == ordinal


def test_an_unknown_date_token_is_refused() -> None:
    with pytest.raises(ValueError, match="'Q'"):
        names.DateFormat("yyyy-Q")
