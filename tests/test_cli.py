"""The command answers at all.

These are deliberately shallow. They exist so the packaging is checked from the
first commit: an entry point that does not resolve, a version that does not
render and a `--help` that raises are all failures this catches before there is
any graph code to blame.
"""

from __future__ import annotations

import subprocess
import sys

import pytest

from logseq_md import __version__
from logseq_md.cli import OK, build_parser, main


def test_version_is_not_empty() -> None:
    assert __version__


def test_help_exits_zero_in_process() -> None:
    assert main([]) == OK


def test_version_flag_exits_zero() -> None:
    # argparse raises SystemExit for --version rather than returning.
    with pytest.raises(SystemExit) as raised:
        main(["--version"])
    assert raised.value.code == OK


def test_unknown_argument_is_a_usage_error() -> None:
    with pytest.raises(SystemExit) as raised:
        main(["--no-such-flag"])
    assert raised.value.code == 2


def test_parser_is_named_after_the_command() -> None:
    # The console script, the module and the distribution all carry this name,
    # and `uvx logseq-md` only works while they agree.
    assert build_parser().prog == "logseq-md"


def test_module_runs_as_a_subprocess() -> None:
    # The in-process tests never exercise `__main__`, which is the path a person
    # takes with `python -m`.
    completed = subprocess.run(
        [sys.executable, "-m", "logseq_md", "--version"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == OK
    assert __version__ in completed.stdout
