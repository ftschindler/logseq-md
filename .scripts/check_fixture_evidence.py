#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# ///
"""Check that every fixture directory carries evidence its leak check still describes.

Usage:
  check_fixture_evidence.py [path ...]

The leak check (`.scripts/check_fixture_leaks.py`) needs a real graph, so it
runs on a maintainer's machine and records `tests/evidence/fixtures-<topic>.json`.
This is the offline half, run in CI and as a pre-commit hook. It cannot tell
that the check ran; it can tell that the recording still describes the fixtures
that are committed. It fails when:

- a fixture directory has no evidence file;
- a recorded hash no longer matches a fixture, or the leak script itself;
- the recorded file set differs from the directory's;
- the recorded outcome is not `pass`.

Paths are accepted and ignored, because a directory is checked as a whole.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES = "tests/fixtures"
EVIDENCE = "tests/evidence"
LEAK_SCRIPT = ".scripts/check_fixture_leaks.py"
SCHEMA_VERSION = 1


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_topic(topic: str, directory: Path, root: Path) -> list[str]:
    evidence_path = root / EVIDENCE / f"fixtures-{topic}.json"
    relative = evidence_path.relative_to(root).as_posix()
    record = f"run `uv run --script {LEAK_SCRIPT} <graph> --record`"
    if not evidence_path.is_file():
        return [f"{topic}: no evidence at {relative}; {record}"]
    try:
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        return [f"{relative}: not valid JSON ({error})"]
    if not isinstance(evidence, dict):
        return [f"{relative}: not a JSON object"]

    problems: list[str] = []
    if evidence.get("schema_version") != SCHEMA_VERSION:
        problems.append(f"{relative}: schema_version is {evidence.get('schema_version')!r}, expected {SCHEMA_VERSION}")
    if evidence.get("script_sha256") != sha256_of(root / LEAK_SCRIPT):
        problems.append(f"{relative}: {LEAK_SCRIPT} changed since the evidence was recorded; {record}")

    current = {path.relative_to(root).as_posix() for path in directory.rglob("*") if path.is_file()}
    entries = evidence.get("files")
    if not isinstance(entries, list) or not all(isinstance(e, dict) and "path" in e and "sha256" in e for e in entries):
        return [*problems, f"{relative}: `files` must be a list of {{path, sha256}}"]
    recorded = {entry["path"]: entry["sha256"] for entry in entries}
    problems += [
        f"{relative}: {path} is not covered by the evidence; {record}" for path in sorted(current - recorded.keys())
    ]
    problems += [
        f"{relative}: covers {path}, which no longer exists; {record}" for path in sorted(recorded.keys() - current)
    ]
    problems += [
        f"{relative}: {path} changed since the evidence was recorded; {record}"
        for path in sorted(current & recorded.keys())
        if sha256_of(root / path) != recorded[path]
    ]

    if evidence.get("outcome") != "pass":
        problems.append(f"{relative}: recorded outcome is {evidence.get('outcome')!r}, not 'pass'")
    return problems


def check_all(root: Path = REPO_ROOT) -> list[str]:
    fixtures = root / FIXTURES
    if not fixtures.is_dir():
        return []
    problems: list[str] = []
    for directory in sorted(fixtures.iterdir()):
        if directory.is_dir():
            problems += check_topic(directory.name, directory, root)
    return problems


def main(argv: list[str]) -> int:
    problems = check_all()
    for problem in problems:
        print(f"error: {problem}", file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
