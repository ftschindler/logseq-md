"""Caller-supplied property keys are opaque (DESIGN.md section 5).

The test is the mechanical one the design names: no property key other than
Logseq's own `id` and `collapsed` appears as a literal in `src/`. A key written
as `key::`, or any key this test knows from Logseq and its plugins, fails it.

The drop list printed by `logseq-md properties` is the one exception, and lives
alone in `src/logseq_md/policy.py`, which is allowed by path.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src" / "logseq_md"
ALLOWED_BY_PATH = {SRC / "policy.py"}
LOGSEQ_OWN = {"id", "collapsed"}

#: Keys a reader of real graphs meets, other than Logseq's own two. Finding one
#: of these as a whole string literal means the code is about to branch on it.
KNOWN_KEYS = {
    "title",
    "alias",
    "tags",
    "template",
    "template-including-parent",
    "public",
    "filters",
    "icon",
    "heading",
    "background-color",
    "query-table",
    "hl-page",
    "hl-color",
    "hl-stamp",
    "hl-type",
    "file",
    "file-path",
    "ls-type",
    "excalidraw-plugin",
    "logseq.order-list-type",
}

PROPERTY_SPELLING = re.compile(r"(?<![\w.-])([A-Za-z][\w.-]*)::")


def offences(source: str) -> list[str]:
    found: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
            continue
        value = node.value
        found += [
            f"line {node.lineno}: {key}::" for key in PROPERTY_SPELLING.findall(value) if key.lower() not in LOGSEQ_OWN
        ]
        if value.lower() in KNOWN_KEYS:
            found.append(f"line {node.lineno}: {value!r}")
    return found


def test_no_property_key_other_than_logseqs_own_is_a_literal_in_src() -> None:
    problems = {
        path.relative_to(SRC).as_posix(): found
        for path in sorted(SRC.rglob("*.py"))
        if path not in ALLOWED_BY_PATH and (found := offences(path.read_text(encoding="utf-8")))
    }
    assert problems == {}


def test_the_check_catches_a_hardcoded_key() -> None:
    assert offences('KEY = "review-note::"\n') == ["line 1: review-note::"]
    assert offences('if key == "hl-page": pass\n') == ["line 1: 'hl-page'"]


def test_the_check_lets_logseqs_own_keys_through() -> None:
    assert offences('LINE = "id:: " + "collapsed:: true"\n') == []
