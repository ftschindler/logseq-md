#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# ///
"""Run a built wheel the way a stranger would, against a copy of a fixture graph.

Usage: smoke.py <path-to-wheel>

Every verb runs once through uvx, from the wheel given rather than the index, the reads first and
then the writes, each asserting its exit code and something in its output, and
the writes asserting the file on disk afterwards. The graph is a copy of
`tests/fixtures/writes/graph/` in a temporary directory, so the fixture itself
is never written.

It is not a second test suite. The suite proves the behaviour; this proves the
wheel carries it: the entry point resolves, the package imports from an install
rather than a checkout, and a write lands on a real file on this operating
system.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

FIXTURE = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "writes" / "graph"
PARENT = "7a20b1c3-0000-4d5e-8f60-000000000051"  # "kiln day", in the journal
TASK = "7a20b1c3-0000-4d5e-8f60-000000000021"  # "TODO ply the singles", on Spindle
NOTE = "7a20b1c3-0000-4d5e-8f60-000000000022"  # "the drop spindle", on Spindle


class SmokeError(Exception):
    pass


def run(wheel: Path, graph: Path, *args: str, code: int = 0, out: str = "") -> str:
    """Run one command, and fail unless it exits with `code` and prints `out`."""
    cmd = ["uvx", "--quiet", "--from", str(wheel), "logseq-md", *args]
    env = {**os.environ, "LOGSEQ_MD_GRAPH": str(graph), "PYTHONIOENCODING": "utf-8"}
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", env=env, check=False)
    shown = " ".join(args)
    if proc.returncode != code:
        raise SmokeError(f"{shown}: exit {proc.returncode}, wanted {code}\n{proc.stdout}{proc.stderr}")
    if out not in proc.stdout:
        raise SmokeError(f"{shown}: output lacks {out!r}\n{proc.stdout}{proc.stderr}")
    print(f"ok  {shown}")
    return proc.stdout


def read_bytes(path: Path) -> bytes:
    return path.read_bytes()


def smoke(wheel: Path, graph: Path) -> None:
    spindle = graph / "pages" / "Spindle.md"
    journal = graph / "journals" / "2031_03_04.md"
    kiln = graph / "pages" / "Kiln Log.md"

    run(wheel, graph, "--version", out="logseq-md")

    # Reads.
    run(wheel, graph, "blocks", "--marker", "TODO", out="TODO ply the singles")
    run(wheel, graph, "show", "Spindle", out="spinning practice")
    run(wheel, graph, "show", "no such page at all", code=1)
    run(wheel, graph, "backlinks", "Spindle")
    run(wheel, graph, "pages", out="Kiln Log")
    run(wheel, graph, "properties", out="collapsed")
    run(wheel, graph, "frobnicate", code=2)

    # Writes. A dry run first, which must leave the file alone.
    before = read_bytes(spindle)
    run(wheel, graph, "set-marker", "--dry-run", TASK, "DONE", out="+")
    if read_bytes(spindle) != before:
        raise SmokeError("set-marker --dry-run changed the file")

    run(wheel, graph, "set-marker", TASK, "DONE")
    if b"DONE ply the singles" not in read_bytes(spindle):
        raise SmokeError("set-marker did not write the marker")

    run(wheel, graph, "set-property", NOTE, "fibre", "wool")
    if b"fibre:: wool" not in read_bytes(spindle):
        raise SmokeError("set-property did not write the property")

    run(wheel, graph, "set-content", NOTE, "--text", "the supported spindle")
    if b"the supported spindle" not in read_bytes(spindle):
        raise SmokeError("set-content did not write the content")

    minted = run(wheel, graph, "ensure-id", "Kiln Log:30").strip()
    if f"id:: {minted}".encode() not in read_bytes(kiln):
        raise SmokeError(f"ensure-id printed {minted!r} but did not write it")

    run(wheel, graph, "append-child", PARENT, "--text", "smoke child", "--record-as", "smoke")
    run(wheel, graph, "append-child", PARENT, "--text", "smoke child again", "--record-as", "smoke")
    after = read_bytes(journal)
    if b"smoke child again" not in after or b"- smoke child\n" in after or b"smoke:: " not in after:
        raise SmokeError(f"append-child --record-as did not update in place:\n{after!r}")


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print(__doc__.split("\n\n")[1], file=sys.stderr)
        return 2
    wheel = Path(argv[0]).resolve()
    with tempfile.TemporaryDirectory() as tmp:
        graph = Path(tmp) / "graph"
        shutil.copytree(FIXTURE, graph)
        try:
            smoke(wheel, graph)
        except SmokeError as e:
            print(f"FAIL {e}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
