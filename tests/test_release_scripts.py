"""The two scripts the release pipeline runs: the version arithmetic, and the check
that a rehearsal upload installs.

Neither is in `src/`, and both are the kind of code whose first failure happens
in a release. Loaded by path because their file names are commands, not modules:
`uv run .scripts/version.py next minor` answers the question on a laptop.
"""

from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path
from types import ModuleType

import pytest

from logseq_md.cli import build_parser

SCRIPTS = Path(__file__).resolve().parent.parent / ".scripts"


def load(name: str) -> ModuleType:
    path = SCRIPTS / name
    spec = importlib.util.spec_from_file_location(path.stem.replace("-", "_"), path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


version = load("version.py")
verify_published = load("verify-published.py")


class TestNextVersion:
    @pytest.mark.parametrize(
        ("current", "level", "expected"),
        [
            ("0.0.0", "minor", "0.1.0"),
            ("0.1.0", "patch", "0.1.1"),
            ("0.1.0", "minor", "0.2.0"),
            # Zeroed, always: 0.4.2 major is 1.0.0, never 1.4.2.
            ("0.4.2", "major", "1.0.0"),
            ("1.9.9", "major", "2.0.0"),
        ],
    )
    def test_each_level(self, current: str, level: str, expected: str) -> None:
        assert version.next_version(current, level) == expected

    def test_something_that_is_not_a_version_is_refused(self) -> None:
        with pytest.raises(SystemExit):
            version.next_version("v1.2", "patch")


class TestDevVersion:
    """A rehearsal is the next release with a numeric dev segment.

    Numeric because PEP 440 says so, and because warehouse refuses the local
    spelling, `0.1.1+g6ec3cb1`, that a commit sha would need.
    """

    def test_it_is_the_version_this_change_would_release(self) -> None:
        assert version.dev_version("0.1.0", "patch", "37611306651") == "0.1.1.dev37611306651"
        assert version.dev_version("0.1.0", "minor", "7") == "0.2.0.dev7"

    def test_a_serial_that_is_not_a_number_is_refused(self) -> None:
        with pytest.raises(SystemExit):
            version.dev_version("0.1.0", "patch", "6ec3cb1")

    def test_a_dev_version_may_be_written(self) -> None:
        assert 'version = "0.1.1.dev9"' in version.replace_version('[project]\nversion = "0.1.0"\n', "0.1.1.dev9")

    def test_a_local_version_may_not_be(self) -> None:
        with pytest.raises(SystemExit):
            version.replace_version('[project]\nversion = "0.1.0"\n', "0.1.1+g6ec3cb1")


class TestTheVersionLine:
    SAMPLE = '[project]\nname = "x"\nversion = "0.1.0"\nrequires-python = ">=3.11"\n'

    def test_it_reads_the_project_version(self) -> None:
        assert version.read_version(self.SAMPLE) == "0.1.0"

    def test_it_writes_it_back_and_changes_nothing_else(self) -> None:
        assert version.replace_version(self.SAMPLE, "0.2.0") == self.SAMPLE.replace("0.1.0", "0.2.0")

    def test_it_refuses_a_version_that_is_not_one(self) -> None:
        with pytest.raises(SystemExit):
            version.replace_version(self.SAMPLE, "0.2")

    def test_a_file_with_no_version_line_is_an_error(self) -> None:
        with pytest.raises(SystemExit):
            version.read_version('[project]\nname = "x"\n')

    def test_this_repository_declares_one(self) -> None:
        assert version.read_version(version.PYPROJECT.read_text(encoding="utf-8"))

    def test_write_edits_only_that_line_and_the_skill_version(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Bytes, not text: a Windows checkout with CRLF endings has to come back
        # with CRLF endings and nothing else moved.
        pyproject = tmp_path / "pyproject.toml"
        before = b'[project]\r\nname = "x"\r\nversion = "0.1.0"\r\n# version = "9.9.9"\r\n'
        pyproject.write_bytes(before)
        skill_version = tmp_path / "VERSION"
        monkeypatch.setattr(version, "PYPROJECT", pyproject)
        monkeypatch.setattr(version, "SKILL_VERSION", skill_version)

        assert version.main(["write", "0.2.0"]) == 0

        assert pyproject.read_bytes() == before.replace(b'"0.1.0"', b'"0.2.0"')
        assert skill_version.read_bytes() == b"0.2.0\n"


def git(*arguments: str) -> None:
    subprocess.run(["git", *arguments], check=True, capture_output=True)


AUTHOR = ("-c", "user.name=Test", "-c", "user.email=test@example.invalid", "-c", "commit.gpgsign=false")


class TestTheVersionGuard:
    """A rewrite is refused; the line arriving for the first time is not.

    Against a real repository, because the thing being tested is a `git diff`.
    """

    def diff_of(self, tmp_path: Path, base: str | None, head: str, monkeypatch: pytest.MonkeyPatch) -> bool:
        repository = tmp_path / "repo"
        repository.mkdir()
        pyproject = repository / "pyproject.toml"
        git("init", "-q", "-b", "main", str(repository))
        (repository / "README.md").write_text("seed\n", encoding="utf-8")
        if base is not None:
            pyproject.write_text(base, encoding="utf-8")
        git("-C", str(repository), "add", "-A")
        git("-C", str(repository), *AUTHOR, "commit", "-qm", "base")
        git("-C", str(repository), "checkout", "-q", "-b", "change")
        pyproject.write_text(head, encoding="utf-8")
        git("-C", str(repository), "add", "-A")
        git("-C", str(repository), *AUTHOR, "commit", "-qm", "change")
        monkeypatch.setattr(version, "PYPROJECT", pyproject)
        monkeypatch.setattr(version, "REPO_ROOT", repository)
        return version.version_changed("main", "change")

    def test_a_rewritten_version_is_caught(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        before = '[project]\nname = "x"\nversion = "0.1.0"\n'
        assert self.diff_of(tmp_path, before, before.replace("0.1.0", "0.2.0"), monkeypatch) is True

    def test_the_line_arriving_for_the_first_time_is_not(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        assert self.diff_of(tmp_path, None, '[project]\nname = "x"\nversion = "0.1.0"\n', monkeypatch) is False

    def test_an_unrelated_edit_to_the_same_file_is_allowed(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        before = '[project]\nname = "x"\nversion = "0.1.0"\n'
        assert self.diff_of(tmp_path, before, before + 'description = "y"\n', monkeypatch) is False


class Result:
    def __init__(self, code: int = 0, stdout: str = "") -> None:
        self.returncode = code
        self.stdout = stdout
        self.stderr = ""


class TestVerifyPublished:
    def captured(self, monkeypatch: pytest.MonkeyPatch) -> list[str]:
        """The command `run` would have executed, without executing it."""
        seen: list[str] = []

        def record(command: list[str], **_options: object) -> Result:
            seen.extend(command)
            return Result()

        monkeypatch.setattr(verify_published.subprocess, "run", record)
        verify_published.run("0.1.1.dev9", "https://test.pypi.org/simple/", "--version")
        return seen

    def test_it_pins_the_exact_version_in_the_short_spelling(self, monkeypatch: pytest.MonkeyPatch) -> None:
        command = self.captured(monkeypatch)
        assert "logseq-md==0.1.1.dev9" in command
        assert "--from" not in command

    def test_it_asks_the_rehearsal_index_first(self, monkeypatch: pytest.MonkeyPatch) -> None:
        command = self.captured(monkeypatch)
        indexes = [command[position + 1] for position, item in enumerate(command) if item == "--index"]
        assert indexes == ["https://test.pypi.org/simple/", verify_published.PYPI]

    def test_it_runs_the_entry_point(self, monkeypatch: pytest.MonkeyPatch) -> None:
        assert self.captured(monkeypatch)[-2:] == ["logseq-md==0.1.1.dev9", "--version"]

    def test_it_retries_while_the_index_catches_up(self, monkeypatch: pytest.MonkeyPatch) -> None:
        attempts: list[int] = []

        def flaky(*_arguments: str) -> Result:
            attempts.append(1)
            return Result(1 if len(attempts) < 3 else 0)

        monkeypatch.setattr(verify_published, "run", flaky)
        monkeypatch.setattr(verify_published.time, "sleep", lambda _seconds: None)
        assert verify_published.wait_for("0.1.1.dev9", "x").returncode == 0
        assert len(attempts) == 3

    def test_it_gives_up_rather_than_waiting_forever(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(verify_published, "run", lambda *_arguments: Result(1))
        monkeypatch.setattr(verify_published.time, "sleep", lambda _seconds: None)
        assert verify_published.wait_for("0.1.1.dev9", "x").returncode == 1

    def test_a_package_that_misreports_its_own_version_fails(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(verify_published, "wait_for", lambda *_arguments: Result(0, "logseq-md 0.1.0\n"))
        assert verify_published.main(["0.1.1.dev9", "https://test.pypi.org/simple/"]) == 1

    def test_the_real_entry_point_passes_the_help_check(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # The string the script looks for in `--help` has to be one the command
        # actually prints, or every rehearsal fails after a successful upload.
        help_text = build_parser().format_help()
        responses = iter([Result(0, help_text)])
        monkeypatch.setattr(verify_published, "wait_for", lambda *_arguments: Result(0, "logseq-md 0.1.1.dev9\n"))
        monkeypatch.setattr(verify_published, "run", lambda *_arguments: next(responses))
        assert verify_published.main(["0.1.1.dev9", "x"]) == 0
