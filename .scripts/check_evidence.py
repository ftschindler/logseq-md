#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# ///
"""Check that every skill carries evidence it was tried on a real assistant.

Ported from ftschindler/agent-kits. Nothing else here can tell you a skill is one
a model will not follow: a skill that is discovered, opened and then ignored
passes every other check in this repository.

The run happens on a maintainer's machine, against the assistant they already
pay for, and is recorded into `tests/evidence/<skill>.json` by
`.scripts/record_evidence.py`. This script is the offline half, run in CI and as
a pre-commit hook: it cannot tell you the run happened, but it can tell you the
recording still describes the skill that is committed, and the probes it asked.

What it enforces:

- **Every kit has an evidence file.** A kit with none has never been tried.
- **Every file hash matches the bytes on disk.** Editing a skill after recording
  is then a red check rather than an oversight.
- **The file set matches the kit's current set.** A hash-only check would miss a
  reference added after the recording, which is exactly the content a skill
  loads when it matters.
- **The recorded outcome is `pass`.** A failing run is committable on purpose,
  so a kit that does not work can be described rather than hidden; the check
  then names it.

Usage:
  check_evidence.py [path ...]

Paths are accepted and ignored beyond deciding whether to run at all, because a
kit is checked as a whole.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
EVIDENCE_DIR_NAME = "tests/evidence"
PROBES_DIR_NAME = "tests/probes"

SCHEMA_VERSION = 1

# Build artifacts and caches are not part of a kit, so they are not part of what
# the evidence covers either.
NOT_PART_OF_A_KIT = ("__pycache__", ".ruff_cache", ".pytest_cache")
# The release job rewrites VERSION on every merge, and a recording made stale by
# every release would be a check nobody could keep green. It says nothing to a model.
NOT_COVERED = ("VERSION",)


def kit_files(root: Path) -> dict[str, list[str]]:
    """Every skill in the repository, mapped to the files its evidence covers.

    A skill is its directory, keyed by the directory name a subscription uses,
    plus its probes in `tests/probes/<skill>.json`: a recording describes the
    questions it asked as much as the skill it asked them with.
    """
    kits: dict[str, list[str]] = {}
    skills = root / "skills"
    if skills.is_dir():
        for marker in sorted(skills.rglob("SKILL.md")):
            if not marker.is_file():
                continue
            directory = marker.parent
            files = [
                path.relative_to(root).as_posix()
                for path in sorted(directory.rglob("*"))
                if path.is_file()
                and path.name not in NOT_COVERED
                and not any(part in NOT_PART_OF_A_KIT for part in path.parts)
            ]
            probes = root / PROBES_DIR_NAME / f"{directory.name}.json"
            if probes.is_file():
                files.append(probes.relative_to(root).as_posix())
            kits[directory.name] = sorted(files)
    return kits


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_coverage(recorded: list, files: list[str], *, relative: str, root: Path) -> list[str]:
    """The recorded file set against the kit's current one, and every hash in it."""
    problems: list[str] = []
    recorded_paths = {entry.get("path") for entry in recorded if isinstance(entry, dict)}
    problems += [
        f"{relative}: {missing} is part of the kit and is not covered by the evidence"
        for missing in sorted(set(files) - recorded_paths)
    ]
    problems += [
        f"{relative}: covers {extra}, which is no longer part of the kit"
        for extra in sorted(recorded_paths - set(files))
    ]

    for entry in recorded:
        if not isinstance(entry, dict) or "path" not in entry or "sha256" not in entry:
            problems.append(f"{relative}: every entry in `files` needs a `path` and a `sha256`")
            continue
        path = root / entry["path"]
        if not path.is_file():
            continue  # already reported above as no longer part of the kit
        if sha256_of(path) != entry["sha256"]:
            problems.append(
                f"{relative}: {entry['path']} has changed since the evidence was recorded. "
                "Re-record it, because the recording describes bytes that are no longer there."
            )
    return problems


def check_kit(name: str, files: list[str], root: Path) -> list[str]:
    """Check one kit's evidence file against the bytes currently committed."""
    evidence_path = root / EVIDENCE_DIR_NAME / f"{name}.json"
    relative = evidence_path.relative_to(root).as_posix()
    if not evidence_path.is_file():
        return [
            f"{name}: no evidence at {relative}. Record one with `uv run --script .scripts/record_evidence.py {name}`."
        ]

    try:
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [f"{relative}: is not valid JSON ({exc})"]
    if not isinstance(evidence, dict):
        return [f"{relative}: is not a JSON object"]

    problems: list[str] = []
    if evidence.get("schema_version") != SCHEMA_VERSION:
        problems.append(
            f"{relative}: `schema_version` is {evidence.get('schema_version')!r}, expected {SCHEMA_VERSION}"
        )
    if evidence.get("kit") != name:
        problems.append(f"{relative}: `kit` is {evidence.get('kit')!r}, expected {name!r}")

    recorded = evidence.get("files")
    if isinstance(recorded, list):
        problems += check_coverage(recorded, files, relative=relative, root=root)
    else:
        problems.append(f"{relative}: `files` is missing or is not a list")

    runs = evidence.get("runs")
    if not isinstance(runs, list) or not runs:
        problems.append(f"{relative}: `runs` is missing or empty, so nothing was actually asked")

    if evidence.get("outcome") != "pass":
        problems.append(
            f"{relative}: recorded outcome is {evidence.get('outcome')!r}. "
            "A failing run is committable so the failure is visible; it is still a failure."
        )

    return problems


def check_all(root: Path = REPO_ROOT) -> list[str]:
    """Every check this script knows, over one repository tree."""
    problems: list[str] = []
    for name, files in sorted(kit_files(root).items()):
        problems += check_kit(name, files, root)
    return problems


def main(argv: list[str]) -> int:
    problems = check_all()
    for problem in problems:
        print(f"error: {problem}", file=sys.stderr)
    if problems:
        print(
            f"\n{len(problems)} problem(s). See CONTRIBUTING.md > Skill evidence for how to record it.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
