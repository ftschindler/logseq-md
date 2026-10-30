#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# ///
"""Fail if any tracked file reaches this command through uvx the long way round.

uvx reads its first argument as a distribution to resolve and infers the command
from it. Here the distribution and the command are both `logseq-md`, which is
why that name was chosen, so the short spelling is the whole invocation:

    uvx logseq-md --help

Naming the distribution separately is not wrong, and that is the problem: it
runs, it reads as more careful, and it is what somebody copies from a sibling
repository where the two names genuinely differ and the longer form is required.
One spelling in the documentation means one thing for a reader to learn and one
thing to change if the name ever moves.

This is the inverse of the guard in `federated-agent-kits`, which forbids the
short form because the command's name there belongs to an unrelated project on
PyPI. The lesson is the same in both: whichever spelling is correct, only one
of them should appear, because a reader cannot tell a working line from a
plausible one by looking at it.

Asks git rather than walking the tree, so it reports what would be committed,
which is what a reader copies out of a rendered README.
"""

from __future__ import annotations

import re
import subprocess
import sys

#: uvx, then any run of flags, with `--from` naming this distribution somewhere
#: in that run. The flags are captured as a group because `--from` is separated
#: from the command by its value and possibly by further flags, so the run has to
#: be judged as a whole.
REDUNDANT_FROM = re.compile(r"uvx(?P<flags>(?:\s+-{1,2}[^\s]+(?:[=\s]+[^\s]+)?)*)\s+logseq-md\b")

#: The files that have to contain the discouraged form in order to do their job:
#: this guard and its test. Named outright rather than matched by a pattern, so
#: the list cannot quietly grow, and no document that instructs anybody is on it.
EXEMPT = (
    ".scripts/check_uvx_invocation.py",
    "tests/test_support_scripts.py",
)

SUGGESTION = "uvx logseq-md"


def offences(text: str) -> list[int]:
    """The line numbers that name the distribution redundantly."""
    found = []
    for number, line in enumerate(text.splitlines(), start=1):
        match = REDUNDANT_FROM.search(line)
        if match is not None and "--from" in match.group("flags"):
            found.append(number)
    return found


def tracked_files() -> list[str]:
    listed = subprocess.run(["git", "ls-files", "-z"], capture_output=True, text=True, check=False)
    if listed.returncode != 0:
        print(f"check_uvx_invocation: `git ls-files` failed\n{listed.stderr}", file=sys.stderr)
        raise SystemExit(1)
    return [path for path in listed.stdout.split("\0") if path]


def committed_text(path: str) -> str | None:
    """The indexed content of one file, or `None` if it is not text.

    The index rather than the working tree: this runs as a pre-commit hook, and
    what a reader eventually copies is what was committed.
    """
    shown = subprocess.run(["git", "show", f":{path}"], capture_output=True, check=False)
    try:
        return shown.stdout.decode("utf-8")
    except UnicodeDecodeError:  # a binary file carries no instruction for a reader
        return None


def main() -> int:
    offenders: list[tuple[str, int]] = []
    for path in tracked_files():
        if path in EXEMPT:
            continue
        text = committed_text(path)
        if text is not None:
            offenders.extend((path, number) for number in offences(text))

    if not offenders:
        return 0

    print("The distribution and the command share a name here, so naming it twice says nothing.")
    for path, number in offenders:
        print(f"  {path}:{number}")
    print(f"\nWrite `{SUGGESTION}` instead.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
