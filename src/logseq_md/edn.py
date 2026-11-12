"""The narrow reader for the three keys this tool needs from `logseq/config.edn`.

**This is not a general EDN parser and must not become one** (DESIGN.md section
4, "Pages, journals and namespaces"). It tokenises just enough of EDN to find
the top-level map's keys and skip whatever values it does not care about:
comments, strings (with `:` and escapes inside), keywords, symbols, numbers,
character literals, the `#_` discard, sets and nested maps, vectors and lists.
It returns the value of a wanted key only when that value is a keyword or a
string. Anything else it meets is a reason to give up on the whole file, and the
caller falls back to Logseq's defaults and says so.

A key nested inside another map is never mistaken for a top-level one, which is
the reason this tokenises instead of searching the text.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

#: The three keys read, and the defaults Logseq applies when the file cannot be read.
NAME_FORMAT = ":file/name-format"
JOURNAL_FILE_FORMAT = ":journal/file-name-format"
JOURNAL_TITLE_FORMAT = ":journal/page-title-format"
WANTED = (NAME_FORMAT, JOURNAL_FILE_FORMAT, JOURNAL_TITLE_FORMAT)

_OPEN = {"{": "}", "#{": "}", "[": "]", "(": ")"}
_CLOSE = frozenset("}])")
_ATOM = re.compile(r"[^\s,;()\[\]{}\"]+")
_CHAR = re.compile(r"\\(newline|space|tab|return|backspace|formfeed|u[0-9a-fA-F]{4}|o[0-7]{1,3}|.)", re.DOTALL)
_STRING = re.compile(r'"((?:[^"\\]|\\.)*)"', re.DOTALL)
_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", '"': '"', "\\": "\\", "b": "\b", "f": "\f"}


class Unreadable(ValueError):  # noqa: N818 - an outcome the caller falls back from, not a bug
    """The file holds something this reader does not understand."""


@dataclass(frozen=True)
class _Token:
    kind: str  # "open", "close", "string", "atom", "discard"
    text: str


def _unescape(body: str) -> str:
    out: list[str] = []
    index = 0
    while index < len(body):
        char = body[index]
        if char != "\\":
            out.append(char)
            index += 1
            continue
        following = body[index + 1]
        if following in _ESCAPES:
            out.append(_ESCAPES[following])
            index += 2
        elif following == "u" and re.fullmatch(r"[0-9a-fA-F]{4}", body[index + 2 : index + 6]):
            out.append(chr(int(body[index + 2 : index + 6], 16)))
            index += 6
        else:
            raise Unreadable(f"unknown string escape \\{following}")
    return "".join(out)


def _tokens(text: str) -> list[_Token]:  # noqa: PLR0912 - one branch per token kind
    tokens: list[_Token] = []
    index = 0
    while index < len(text):
        char = text[index]
        if char.isspace() or char == ",":
            index += 1
        elif char == ";":
            newline = text.find("\n", index)
            index = len(text) if newline < 0 else newline + 1
        elif char == '"':
            match = _STRING.match(text, index)
            if match is None:
                raise Unreadable("unterminated string")
            tokens.append(_Token("string", _unescape(match.group(1))))
            index = match.end()
        elif char in "{[(":
            tokens.append(_Token("open", char))
            index += 1
        elif char in _CLOSE:
            tokens.append(_Token("close", char))
            index += 1
        elif text.startswith("#{", index):
            tokens.append(_Token("open", "#{"))
            index += 2
        elif text.startswith("#_", index):
            tokens.append(_Token("discard", "#_"))
            index += 2
        elif char == "#":
            raise Unreadable("a tagged literal or reader macro")
        elif char == "\\":
            match = _CHAR.match(text, index)
            if match is None:
                raise Unreadable("a character literal at the end of the file")
            tokens.append(_Token("atom", match.group(0)))
            index = match.end()
        else:
            match = _ATOM.match(text, index)
            assert match is not None  # every other character starts an atom
            tokens.append(_Token("atom", match.group(0)))
            index = match.end()
    return tokens


class _Reader:
    def __init__(self, tokens: list[_Token]) -> None:
        self.tokens = tokens
        self.position = 0

    def next(self) -> _Token:
        if self.position >= len(self.tokens):
            raise Unreadable("the file ends inside a form")
        token = self.tokens[self.position]
        self.position += 1
        return token

    def form(self) -> _Token | None:
        """Read one form; return its token when it is a scalar, None when a collection."""
        token = self.next()
        if token.kind == "discard":
            self.form()
            return self.form()
        if token.kind == "close":
            raise Unreadable(f"an unexpected {token.text}")
        if token.kind == "open":
            self.rest_of(_OPEN[token.text])
            return None
        return token

    def rest_of(self, closer: str) -> None:
        while True:
            token = self.tokens[self.position] if self.position < len(self.tokens) else None
            if token is None:
                raise Unreadable("the file ends inside a collection")
            if token.kind == "close":
                if token.text != closer:
                    raise Unreadable(f"{token.text} closes a collection opened differently")
                self.position += 1
                return
            self.form()

    def at_close(self) -> bool:
        while self.position < len(self.tokens) and self.tokens[self.position].kind == "discard":
            self.position += 1
            self.form()
        return self.position < len(self.tokens) and self.tokens[self.position].kind == "close"


def read_config(text: str) -> dict[str, str]:
    """The wanted keys found at the top level of `text`, each as written.

    A keyword value keeps its colon (`:triple-lowbar`); a string value is
    unescaped. A wanted key whose value is anything else, or a file this reader
    does not understand, raises `Unreadable`.
    """
    reader = _Reader(_tokens(text))
    opening = reader.next()
    while opening.kind == "discard":
        reader.form()
        opening = reader.next()
    if opening.kind != "open" or opening.text != "{":
        raise Unreadable("the file is not a map")
    found: dict[str, str] = {}
    while not reader.at_close():
        key = reader.form()
        if reader.at_close():
            raise Unreadable("a map with an odd number of forms")
        value = reader.form()
        if key is None or key.kind != "atom" or key.text not in WANTED:
            continue
        if value is None or (value.kind == "atom" and not value.text.startswith(":")):
            raise Unreadable(f"{key.text} has a value that is neither a keyword nor a string")
        found[key.text] = value.text
    reader.next()
    if reader.position != len(reader.tokens):
        raise Unreadable("something follows the map")
    return found
