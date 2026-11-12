"""Enumeration: `blocks`, `pages` and `properties` over a minimal graph.

The graph under `tests/fixtures/enumeration/graph/` has a task under every
marker on one page, tags written all three ways, a property key the tool has
never heard of, journals across three dates and a page of prose with no
bullets.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from logseq_md import blocks
from logseq_md.cli import main
from logseq_md.exits import BAD_ARGUMENTS, NOT_FOUND, OK

GRAPH = Path(__file__).resolve().parent / "fixtures" / "enumeration" / "graph"
STUDIO = str(GRAPH / "pages" / "Pottery Studio.md")
JAN, FEB, MAR = (str(GRAPH / "journals" / f"2025_{day}.md") for day in ("01_10", "02_14", "03_20"))


def run(capsys: pytest.CaptureFixture[str], *argv: str) -> tuple[int, str, str]:
    code = main([*argv[:1], "--graph", str(GRAPH), *argv[1:]])
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def blocks_json(capsys: pytest.CaptureFixture[str], *flags: str) -> list[dict]:
    code, out, _ = run(capsys, "blocks", "--json", *flags)
    assert code == OK
    return json.loads(out)


def where(records: list[dict]) -> list[tuple[str, int]]:
    return [(record["path"], record["line"]) for record in records]


@pytest.mark.parametrize("marker", blocks.MARKERS)
def test_each_marker_filters_alone(capsys: pytest.CaptureFixture[str], marker: str) -> None:
    found = blocks_json(capsys, "--marker", marker)
    assert found
    assert {record["marker"] for record in found} == {marker}


def test_marker_is_case_insensitive_and_unknown_is_exit_2(capsys: pytest.CaptureFixture[str]) -> None:
    assert len(blocks_json(capsys, "--marker", "todo")) == 3
    assert run(capsys, "blocks", "--marker", "SOMEDAY")[0] == BAD_ARGUMENTS


def test_tag_matches_hash_bracketed_and_page_links_ignoring_case(capsys: pytest.CaptureFixture[str]) -> None:
    assert where(blocks_json(capsys, "--tag", "KILN")) == [(STUDIO, 2), (JAN, 1), (FEB, 1)]
    assert where(blocks_json(capsys, "--tag", "market stall")) == [(STUDIO, 6)]
    assert where(blocks_json(capsys, "--tag", "Clay Supplier")) == [(STUDIO, 5)]


def test_has_property_takes_a_key_the_tool_does_not_know(capsys: pytest.CaptureFixture[str]) -> None:
    assert where(blocks_json(capsys, "--has-property", "glaze-batch")) == [(STUDIO, 10), (FEB, 2)]
    assert where(blocks_json(capsys, "--has-property", "a-key-nobody-wrote")) == []


def test_since_and_until_select_journals_and_leave_pages_out(capsys: pytest.CaptureFixture[str]) -> None:
    assert {r["path"] for r in blocks_json(capsys, "--since", "2025-02-14")} == {FEB, MAR}
    assert {r["path"] for r in blocks_json(capsys, "--until", "2025-02-14")} == {JAN, FEB}
    between = blocks_json(capsys, "--since", "2025-02-01", "--until", "2025-02-28")
    assert {r["path"] for r in between} == {FEB}
    assert between[0]["date"] == "2025-02-14"


def test_a_bad_date_is_exit_2(capsys: pytest.CaptureFixture[str]) -> None:
    assert run(capsys, "blocks", "--since", "14.02.2025")[0] == BAD_ARGUMENTS
    assert run(capsys, "blocks", "--until", "2025-02-30")[0] == BAD_ARGUMENTS


def test_page_takes_a_page_name_or_a_journal_title(capsys: pytest.CaptureFixture[str]) -> None:
    assert {r["path"] for r in blocks_json(capsys, "--page", "pottery studio")} == {STUDIO}
    assert where(blocks_json(capsys, "--page", "Mar 20th, 2025")) == [(MAR, 1)]
    assert run(capsys, "blocks", "--page", "No Such Page")[0] == NOT_FOUND


def test_filters_compose_as_a_conjunction(capsys: pytest.CaptureFixture[str]) -> None:
    assert where(blocks_json(capsys, "--marker", "TODO", "--tag", "kiln")) == [(STUDIO, 2), (JAN, 1)]
    assert where(blocks_json(capsys, "--marker", "TODO", "--tag", "kiln", "--since", "2025-01-01")) == [(JAN, 1)]
    assert where(blocks_json(capsys, "--marker", "TODO", "--has-property", "glaze-batch")) == [(FEB, 2)]
    assert where(blocks_json(capsys, "--marker", "DONE", "--page", "Pottery Studio", "--tag", "kiln")) == []


def test_the_json_shape(capsys: pytest.CaptureFixture[str]) -> None:
    [found] = blocks_json(capsys, "--marker", "TODO", "--page", "Pottery Studio")
    assert found == {
        "path": STUDIO,
        "page": "Pottery Studio",
        "date": None,
        "line": 2,
        "id": "6790a1b2-0000-4c11-8a22-000000000001",
        "marker": "TODO",
        "content": "TODO glaze the twelve teal mugs #kiln",
        "properties": [{"key": "id", "value": "6790a1b2-0000-4c11-8a22-000000000001"}],
        "ancestors": [
            {
                "line": 1,
                "id": None,
                "marker": None,
                "content": "Kiln firing schedule for the spring market",
                "properties": [],
            }
        ],
    }


def test_children_add_the_subtree_and_the_drop_list_applies(capsys: pytest.CaptureFixture[str]) -> None:
    [later] = blocks_json(capsys, "--marker", "LATER", "--children")
    assert later["children"] == [
        {"line": 7, "id": None, "marker": None, "content": "the lightbox needs new bulbs first", "properties": [],
         "children": []}
    ]  # fmt: skip
    [kept] = blocks_json(capsys, "--marker", "LATER", "--children", "--keep", "collapsed")
    assert kept["children"][0]["properties"] == [{"key": "collapsed", "value": "true"}]
    [loose] = [r for r in blocks_json(capsys, "--page", "Pottery Studio", "--raw") if r["line"] == 13]
    assert loose["properties"] == [{"key": "excalidraw-plugin", "value": "sketch-14"}]
    [stripped] = [r for r in blocks_json(capsys, "--page", "Pottery Studio") if r["line"] == 13]
    assert stripped["properties"] == []


def test_text_shows_the_ancestors_then_the_block(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, _ = run(capsys, "blocks", "--marker", "LATER", "--children")
    assert code == OK
    assert out == (
        f"{STUDIO}:6  [Pottery Studio]\n"
        "- Kiln firing schedule for the spring market\n"
        "\t- LATER photograph the speckled bowls #[[Market Stall]]\n"
        "\t\t- the lightbox needs new bulbs first\n"
    )


def test_text_keeps_the_dropped_line_with_raw(capsys: pytest.CaptureFixture[str]) -> None:
    _, out, _ = run(capsys, "blocks", "--marker", "LATER", "--children", "--raw")
    assert out.endswith("\t\t- the lightbox needs new bulbs first\n\t\t  collapsed:: true\n")


def test_paths_prints_each_file_once(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, _ = run(capsys, "blocks", "--marker", "TODO", "--paths")
    assert code == OK
    assert out.splitlines() == [STUDIO, JAN, FEB]


def test_pages_lists_every_file_including_prose(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, _ = run(capsys, "pages", "--json")
    assert code == OK
    found = {record["name"]: record for record in json.loads(out)}
    assert sorted(found) == ["Feb 14th, 2025", "Jan 10th, 2025", "Mar 20th, 2025", "Pottery Studio", "Slab Roller"]
    assert found["Slab Roller"] == {
        "path": str(GRAPH / "pages" / "Slab Roller.md"),
        "name": "Slab Roller",
        "date": None,
        "outline": False,
        "blocks": 0,
    }
    assert found["Jan 10th, 2025"]["date"] == "2025-01-10"
    _, text, _ = run(capsys, "pages")
    assert "Slab Roller\t" in text
    assert "no outline" in text
    _, paths, _ = run(capsys, "pages", "--paths")
    assert len(paths.splitlines()) == 5


def test_properties_prints_the_drop_list(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["properties"]) == OK
    assert capsys.readouterr().out.splitlines() == ["collapsed", "excalidraw-plugin"]
    assert main(["properties", "--json"]) == OK
    assert json.loads(capsys.readouterr().out) == {"dropped": ["collapsed", "excalidraw-plugin"]}


def test_blocks_help_documents_the_json_shape(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        main(["blocks", "--help"])
    printed = capsys.readouterr().out
    for field in ('"ancestors"', '"children"', '"properties"', '"marker"', '"date"', "a page has no date"):
        assert field in printed
