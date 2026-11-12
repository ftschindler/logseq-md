"""Resolution: `show` and `backlinks` over a minimal graph.

The graph under `tests/fixtures/resolution/graph/` has a reference chain three
deep (Apiary line 2 to Hive Notes lines 1, 5 and 7), a two-block cycle (Hive
Notes lines 3 and 9), a reference no block answers, an embed, a link to a page
with a file and one to a page without, and three ways of linking to a page.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from logseq_md.cli import main
from logseq_md.exits import BAD_ARGUMENTS, NOT_FOUND, OK

GRAPH = Path(__file__).resolve().parent / "fixtures" / "resolution" / "graph"
APIARY = str(GRAPH / "pages" / "Apiary.md")
NOTES = str(GRAPH / "pages" / "Hive Notes.md")
FOUNDRY = str(GRAPH / "pages" / "Wax Foundry.md")
JOURNAL = str(GRAPH / "journals" / "2025_04_02.md")
ID = "6650c3d4-0000-4a11-8b22-0000000000{}"
CHAIN, CYCLE = ID.format("01"), ID.format("02")


def run(capsys: pytest.CaptureFixture[str], *argv: str) -> tuple[int, str, str]:
    code = main([*argv[:1], "--graph", str(GRAPH), *argv[1:]])
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def show_json(capsys: pytest.CaptureFixture[str], *argv: str) -> dict:
    code, out, _ = run(capsys, "show", "--json", *argv)
    assert code == OK
    return json.loads(out)


def chain(first: dict) -> list[tuple[str, int | None]]:
    """Follow the first reference at each level: (status, line found at) down the chain."""
    steps = []
    reference: dict | None = first
    while reference is not None:
        steps.append((reference["status"], reference["found"][0]["line"] if reference["found"] else None))
        nested = reference["references"]
        reference = nested[0] if nested else None
    return steps


def test_one_level_by_default(capsys: pytest.CaptureFixture[str]) -> None:
    record = show_json(capsys, CHAIN)
    assert (record["path"], record["line"]) == (APIARY, 2)
    assert [node["line"] for node in record["ancestors"]] == [1]
    (reference,) = record["references"]
    assert chain(reference) == [("resolved", 1)]
    assert reference["found"][0]["path"] == NOTES
    assert reference["found"][0]["content"].startswith("Rain is forecast")


def test_depth_follows_a_chain_three_deep(capsys: pytest.CaptureFixture[str]) -> None:
    assert chain(show_json(capsys, CHAIN, "--depth", "3")["references"][0]) == [
        ("resolved", 1),
        ("resolved", 5),
        ("resolved", 7),
    ]
    # Deeper than the chain goes ends with a block that references nothing.
    deep = show_json(capsys, CHAIN, "--depth", "50")["references"][0]
    assert chain(deep) == [("resolved", 1), ("resolved", 5), ("resolved", 7)]


def test_depth_zero_resolves_nothing_and_negative_is_exit_2(capsys: pytest.CaptureFixture[str]) -> None:
    assert show_json(capsys, CHAIN, "--depth", "0")["references"] == []
    assert run(capsys, "show", CHAIN, "--depth", "-1")[0] == BAD_ARGUMENTS


def test_a_cycle_is_reported_where_it_is_met(capsys: pytest.CaptureFixture[str]) -> None:
    reference = show_json(capsys, CYCLE, "--depth", "1000")["references"][0]
    assert chain(reference) == [("resolved", 3), ("resolved", 9), ("cycle", None)]
    code, out, _ = run(capsys, "show", CYCLE, "--depth", "1000")
    assert code == OK
    assert out.count("cycle: already being resolved above") == 1


def test_a_block_cycling_to_itself_through_one_hop(capsys: pytest.CaptureFixture[str]) -> None:
    # Shown directly, the first block of the pair is the start of the chain.
    reference = show_json(capsys, ID.format("0b"), "--depth", "5")["references"][0]
    assert chain(reference) == [("resolved", 9), ("cycle", None)]


def page_references(capsys: pytest.CaptureFixture[str]) -> dict[str, dict]:
    record = show_json(capsys, "Apiary", "--children")
    return {reference["target"]: reference for reference in record["references"]}


def test_a_dangling_reference_is_reported_not_dropped(capsys: pytest.CaptureFixture[str]) -> None:
    dangling = page_references(capsys)[ID.format("ff")]
    assert (dangling["status"], dangling["found"], dangling["line"]) == ("dangling", [], 6)
    out = run(capsys, "show", "Apiary", "--children")[1]
    assert f"(({ID.format('ff')}))  at {APIARY}:6  -> dangling" in out


def test_an_embed_resolves_like_a_reference(capsys: pytest.CaptureFixture[str]) -> None:
    embed = page_references(capsys)[ID.format("0d")]
    assert (embed["kind"], embed["status"]) == ("embed", "resolved")
    assert embed["found"][0]["content"] == "Friday is the last dry day this week"
    assert "| Friday is the last dry day this week" in run(capsys, "show", "Apiary", "--children")[1]


def test_a_page_link_becomes_a_path_and_a_missing_file_dangles(capsys: pytest.CaptureFixture[str]) -> None:
    found = page_references(capsys)
    assert (found["Wax Foundry"]["status"], found["Wax Foundry"]["page_path"]) == ("resolved", FOUNDRY)
    missing = found["Propolis Tincture"]
    assert missing["status"] == "dangling"
    assert missing["page_path"] == str(GRAPH / "pages" / "Propolis Tincture.md")


def test_a_page_shows_its_top_level_blocks_and_its_outline_with_children(
    capsys: pytest.CaptureFixture[str],
) -> None:
    record = show_json(capsys, "Apiary")
    assert [node["line"] for node in record["blocks"]] == [1, 8]
    assert "children" not in record["blocks"][0]
    # Without --children only the top-level blocks' references are resolved.
    assert [reference["target"] for reference in record["references"]] == ["Wax Foundry", "Propolis Tincture"]
    nested = show_json(capsys, "Apiary", "--children")["blocks"][0]["children"]
    assert [node["line"] for node in nested] == [2, 4, 6, 7]


def test_a_missing_target_is_exit_1(capsys: pytest.CaptureFixture[str]) -> None:
    assert run(capsys, "show", ID.format("99"))[0] == NOT_FOUND
    assert run(capsys, "show", "Mead Recipes")[0] == NOT_FOUND


def test_text_shows_ancestors_then_block_then_references(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, _ = run(capsys, "show", CHAIN)
    assert code == OK
    lines = out.splitlines()
    assert lines[0] == f"{APIARY}:2  [Apiary]"
    assert lines[1] == "- Hive inspections this season"
    assert lines[2].startswith("\t- Inspect the north hive")
    assert lines[4] == "references:"
    assert lines[5].endswith(f"-> {NOTES}:1  [Hive Notes]")


def test_paths_prints_the_file(capsys: pytest.CaptureFixture[str]) -> None:
    assert run(capsys, "show", "--paths", CHAIN)[1] == f"{APIARY}\n"


def backlinks_json(capsys: pytest.CaptureFixture[str], page: str) -> list[dict]:
    code, out, _ = run(capsys, "backlinks", "--json", page)
    assert code == OK
    return json.loads(out)


def test_backlinks_finds_every_link_form_ignoring_case(capsys: pytest.CaptureFixture[str]) -> None:
    found = backlinks_json(capsys, "Wax Foundry")
    # [[Wax Foundry]], #[[Wax Foundry]] and [[wax foundry]]; the #foundry tag is another page.
    assert [(record["path"], record["line"]) for record in found] == [(APIARY, 8), (JOURNAL, 1), (JOURNAL, 3)]


def test_backlinks_carry_ancestors_and_children_on_request(capsys: pytest.CaptureFixture[str]) -> None:
    found = backlinks_json(capsys, "foundry")
    assert [(record["path"], record["line"]) for record in found] == [(JOURNAL, 2)]
    assert [node["line"] for node in found[0]["ancestors"]] == [1]
    code, out, _ = run(capsys, "backlinks", "--json", "--children", "Wax Foundry")
    assert code == OK
    assert [node["line"] for node in json.loads(out)[1]["children"]] == [2]


def test_backlinks_to_a_page_with_no_file_still_answer(capsys: pytest.CaptureFixture[str]) -> None:
    assert [record["line"] for record in backlinks_json(capsys, "Propolis Tincture")] == [8]


def test_backlinks_to_an_unknown_page_is_exit_1(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, err = run(capsys, "backlinks", "Mead Recipes")
    assert (code, out) == (NOT_FOUND, "")
    assert "nothing links to it" in err


def test_backlinks_text_and_paths(capsys: pytest.CaptureFixture[str]) -> None:
    out = run(capsys, "backlinks", "Wax Foundry")[1]
    assert out.startswith(f"{APIARY}:8  [Apiary]\n- Order foundation sheets")
    assert run(capsys, "backlinks", "--paths", "Wax Foundry")[1] == f"{APIARY}\n{JOURNAL}\n"
