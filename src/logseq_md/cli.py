"""The command line entry point.

Nothing reads a graph yet. What is here is the parser, the version flag and the
exit convention, which is what the packaging, the entry point and the smoke test
in CI need in order to be checked before there is anything to check them on.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from logseq_md import __version__

#: Exit codes. `2` is argparse's own code for a usage error and is not reused
#: here for anything else, so a caller can tell "you asked wrongly" from "the
#: graph said no".
OK = 0
FAILED = 1


def build_parser() -> argparse.ArgumentParser:
    """The argument parser, built separately so a test can inspect it."""
    parser = argparse.ArgumentParser(
        prog="logseq-md",
        description="Read and write file-based Logseq markdown graphs.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command and return its exit code.

    Returning rather than exiting keeps the whole command testable in-process;
    `run` is the thin wrapper the console script points at.
    """
    parser = build_parser()
    parser.parse_args(argv)
    parser.print_help()
    return OK


def run() -> None:
    """Console script entry point."""
    sys.exit(main())
