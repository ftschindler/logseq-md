"""A path, made into a graph: where it is, what its config says, and which files are its pages.

DESIGN.md section 8: the graph comes from `--graph`, else `LOGSEQ_MD_GRAPH`, and
nothing is inferred from the filesystem. A directory with neither `pages/` nor
`journals/` is not a graph, and is refused with exit code 5.

Only `pages/` and `journals/` are read (section 4, "What the tool does not
read"), so `logseq/bak`, `assets/`, `draws/` and `whiteboards/` are never
enumerated; neither is a hidden file or directory, which Logseq ignores too.

The config is read once per invocation with the narrow reader in `edn`. When it
cannot be read, the graph falls back to Logseq's current defaults and carries a
note saying so, which `open_graph` prints on stderr.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import TextIO

from logseq_md import edn, names
from logseq_md.exits import BAD_ARGUMENTS, UNREADABLE, Refusal

ENVIRONMENT = "LOGSEQ_MD_GRAPH"
PAGES = "pages"
JOURNALS = "journals"
#: Skipped by construction, since only `pages/` and `journals/` are walked; named for the reader.
NOT_READ = ("logseq/bak", "assets", "draws", "whiteboards")


@dataclass(frozen=True)
class Config:
    """The three settings names depend on, and any note about how they were found."""

    name_format: str = names.TRIPLE_LOWBAR
    journal_file: names.DateFormat = field(default_factory=lambda: names.DateFormat(names.DEFAULT_JOURNAL_FILE_FORMAT))
    journal_title: names.DateFormat = field(
        default_factory=lambda: names.DateFormat(names.DEFAULT_JOURNAL_TITLE_FORMAT)
    )
    notes: tuple[str, ...] = ()


def read_config(root: Path) -> Config:
    """The graph's `logseq/config.edn`, or Logseq's current defaults with a note."""
    path = root / "logseq" / "config.edn"
    try:
        with path.open("rb") as handle:
            data = handle.read()
    except FileNotFoundError:
        return Config(notes=(f"{path}: not found; using Logseq's defaults",))
    try:
        found = edn.read_config(data.decode("utf-8"))
    except (UnicodeDecodeError, edn.Unreadable) as error:
        return Config(notes=(f"{path}: cannot be read ({error}); using Logseq's defaults",))
    notes: list[str] = []
    # A readable config without the key is an old graph: Logseq reads it as legacy.
    name_format = found.get(edn.NAME_FORMAT, names.LEGACY)
    if name_format not in (names.TRIPLE_LOWBAR, names.LEGACY):
        notes.append(f"{path}: unknown {edn.NAME_FORMAT} {name_format}; reading it as {names.LEGACY}")
        name_format = names.LEGACY
    formats: list[names.DateFormat] = []
    for key, default in (
        (edn.JOURNAL_FILE_FORMAT, names.DEFAULT_JOURNAL_FILE_FORMAT),
        (edn.JOURNAL_TITLE_FORMAT, names.DEFAULT_JOURNAL_TITLE_FORMAT),
    ):
        pattern = found.get(key, default)
        try:
            formats.append(names.DateFormat(pattern))
        except ValueError as error:
            notes.append(f"{path}: {error}; using {default!r}")
            formats.append(names.DateFormat(default))
    return Config(name_format, formats[0], formats[1], tuple(notes))


@dataclass(frozen=True)
class Graph:
    root: Path
    config: Config

    def files(self) -> Iterator[Path]:
        """Every markdown file under `pages/` and `journals/`, in a stable order."""
        for directory in (PAGES, JOURNALS):
            base = self.root / directory
            if not base.is_dir():
                continue
            for path in sorted(base.rglob("*.md")):
                if path.is_file() and not any(part.startswith(".") for part in path.relative_to(base).parts):
                    yield path

    def is_journal(self, path: Path) -> bool:
        return path.parent == self.root / JOURNALS

    def journal_date(self, path: Path) -> date | None:
        """The date a journal file is for, or None for a page or an unparseable name."""
        return self.config.journal_file.parse(path.stem) if self.is_journal(path) else None

    def page_name(self, path: Path) -> str:
        """The page name a file holds: a journal's title, or the name its filename encodes."""
        day = self.journal_date(path)
        if day is not None:
            return self.config.journal_title.format(day)
        return names.file_body_to_page(path.stem, self.config.name_format)

    def page_path(self, name: str) -> Path:
        """Where a page called `name` lives, whether or not it exists."""
        return self.root / PAGES / f"{names.page_to_file_body(name, self.config.name_format)}.md"

    def journal_path(self, day: date) -> Path:
        """Where the journal for `day` lives, whether or not it exists."""
        return self.root / JOURNALS / f"{self.config.journal_file.format(day)}.md"


def open_graph(
    flag: str | None,
    environment: Mapping[str, str] | None = None,
    stderr: TextIO | None = None,
) -> Graph:
    """The graph named by `--graph`, else by `LOGSEQ_MD_GRAPH`; the flag wins.

    Refuses with exit 2 when neither names one, and exit 5 when the path is not a
    graph. Notes about the config go to `stderr`.
    """
    environment = os.environ if environment is None else environment
    named = flag or environment.get(ENVIRONMENT)
    if not named:
        raise Refusal(BAD_ARGUMENTS, f"no graph: pass --graph PATH or set {ENVIRONMENT}")
    root = Path(named).expanduser()
    if not ((root / PAGES).is_dir() or (root / JOURNALS).is_dir()):
        raise Refusal(UNREADABLE, f"{root}: not a graph (no {PAGES}/ or {JOURNALS}/)")
    graph = Graph(root, read_config(root))
    for note in graph.config.notes:
        print(f"logseq-md: {note}", file=stderr or sys.stderr)
    return graph
