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
from logseq_md.cli import HANDLERS, build_parser, main, placeholders
from logseq_md.exits import BAD_ARGUMENTS, OK, Refusal


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


#: Every verb in DESIGN.md section 10.
VERBS = [
    "blocks",
    "show",
    "backlinks",
    "pages",
    "properties",
    "ensure-id",
    "set-property",
    "append-child",
    "set-content",
    "set-marker",
]


def test_every_verb_is_registered_with_a_handler() -> None:
    assert sorted(HANDLERS) == sorted(VERBS)


@pytest.mark.parametrize("verb", VERBS)
def test_every_verb_has_help_with_an_example(verb: str, capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as raised:
        main([verb, "--help"])
    assert raised.value.code == OK
    printed = capsys.readouterr().out
    assert f"logseq-md {verb}" in printed
    assert "example:" in printed


def test_verbs_still_on_a_placeholder() -> None:
    # S10 asserts this is empty. Until then it names what is left, so a stage
    # that implements a verb has to say so here.
    assert placeholders() == sorted(set(VERBS) - {"blocks", "pages", "properties", "show", "backlinks"})


def test_a_placeholder_exits_2(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["set-marker", "x", "DONE"]) == BAD_ARGUMENTS
    assert "not implemented yet" in capsys.readouterr().err


def test_a_refusal_becomes_its_message_and_code(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def refuse(_args: object) -> int:
        raise Refusal(5, "pages/x.md: not valid UTF-8")

    monkeypatch.setitem(HANDLERS, "properties", refuse)
    assert main(["properties"]) == 5
    assert "pages/x.md: not valid UTF-8" in capsys.readouterr().err
