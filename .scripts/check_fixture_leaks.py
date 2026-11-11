#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# ///
"""Check that no fixture line was copied out of a real graph, and record that it was checked.

Usage:
  check_fixture_leaks.py <graph> [--record]

A fixture is written by somebody who has just read a private graph, which is how
a real line ends up in one. This compares every line of every file under
`tests/fixtures/<topic>/` with every line of every markdown file in the graph,
and fails on any match that is more than structure: a bullet on its own, a `---` rule,
whitespace, an `id::` or `collapsed::` line, a fence marker or `:END:`.

Lines are compared as bytes with surrounding whitespace removed, and once more
with a leading bullet removed, so a line copied at a different depth or lifted
out of a block still matches. That catches a copied line and not a paraphrase;
reading the fixture diff stays a reviewer's job.

With `--record`, it writes `tests/evidence/fixtures-<topic>.json` per fixture
directory: the hash of every fixture file in it, the hash of this script, the
outcome and how many graph files were scanned. **No path, name or line from the
graph is written**, and the graph is opened with `"rb"` and nothing else. A test
reads this source and fails if graph-reading code gains a write call; the only
writing is in `write_evidence`, which touches the repository.

`.scripts/check_fixture_evidence.py` is the offline half that runs in CI.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES = "tests/fixtures"
EVIDENCE = "tests/evidence"
SCHEMA_VERSION = 1

LINE_BREAK = re.compile(rb"\r\n|\n|\r")
BULLET = re.compile(rb"^-[ \t]+")
STRUCTURE = re.compile(rb"^(-|-{3,}|:END:|(`{3,}|~{3,})[\w+-]*|(id|collapsed)::.*)?$", re.IGNORECASE)


def normalised(line: bytes) -> list[bytes]:
    """The forms of a line worth comparing: stripped, and stripped of its bullet."""
    stripped = line.strip(b" \t\xef\xbb\xbf")
    forms = [stripped]
    unbulleted = BULLET.sub(b"", stripped)
    if unbulleted != stripped:
        forms.append(unbulleted)
    return [form for form in forms if not STRUCTURE.match(form)]


def graph_lines(graph: Path) -> tuple[set[bytes], int]:
    """Every comparable line form in the graph's markdown, and how many files held them."""
    seen: set[bytes] = set()
    scanned = 0
    for path in sorted(graph.rglob("*.md")):
        if not path.is_file():
            continue
        with path.open("rb") as handle:
            data = handle.read()
        scanned += 1
        for line in LINE_BREAK.split(data):
            seen.update(normalised(line))
    return seen, scanned


def fixture_topics(root: Path) -> dict[str, list[Path]]:
    """Each fixture directory, mapped to every file in it."""
    fixtures = root / FIXTURES
    if not fixtures.is_dir():
        return {}
    return {
        directory.name: sorted(path for path in directory.rglob("*") if path.is_file())
        for directory in sorted(fixtures.iterdir())
        if directory.is_dir()
    }


def leaks(files: list[Path], seen: set[bytes], root: Path) -> list[str]:
    """Each fixture line found in the graph, named by fixture path and line number only."""
    found: list[str] = []
    for path in files:
        for number, line in enumerate(LINE_BREAK.split(path.read_bytes()), start=1):
            if any(form in seen for form in normalised(line)):
                found.append(f"{path.relative_to(root).as_posix()}:{number}")
    return found


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def evidence_for(topic: str, files: list[Path], outcome: str, scanned: int, root: Path) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "topic": topic,
        "files": [{"path": path.relative_to(root).as_posix(), "sha256": sha256_of(path)} for path in files],
        "script_sha256": sha256_of(Path(__file__).resolve()),
        "outcome": outcome,
        "graph_files_scanned": scanned,
        "recorded_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def write_evidence(evidence: dict, root: Path) -> Path:
    """The one place this script writes, and it writes into the repository."""
    target = root / EVIDENCE / f"fixtures-{evidence['topic']}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes((json.dumps(evidence, indent=2, sort_keys=True) + "\n").encode("utf-8"))
    return target


def check(graph: Path, root: Path = REPO_ROOT, *, record: bool = False) -> int:
    seen, scanned = graph_lines(graph)
    if scanned == 0:
        print(f"error: no markdown under {graph}; is it a graph?", file=sys.stderr)
        return 2
    failed = False
    for topic, files in fixture_topics(root).items():
        found = leaks(files, seen, root)
        outcome = "fail" if found else "pass"
        failed |= bool(found)
        for location in found:
            print(f"leak: {location} occurs verbatim in the graph", file=sys.stderr)
        print(f"{topic}: {outcome} ({len(files)} fixture files, {scanned} graph files)")
        if record:
            print(
                f"  recorded {write_evidence(evidence_for(topic, files, outcome, scanned, root), root).relative_to(root).as_posix()}"
            )
    return 1 if failed else 0


def main(argv: list[str]) -> int:
    record = "--record" in argv
    paths = [arg for arg in argv if arg != "--record"]
    if len(paths) != 1:
        print(__doc__, file=sys.stderr)
        return 2
    return check(Path(paths[0]), record=record)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
