"""Page names, filenames and journal dates, converted the way Logseq converts them.

Two filename formats, chosen by `:file/name-format` in the graph's config
(DESIGN.md section 4, "Pages, journals and namespaces"):

- `:triple-lowbar`, Logseq's current one. A namespace `/` becomes `___`; the
  characters that break a filesystem somewhere (`: * ? " < > | # \\`) are
  percent-encoded, as is a `%` that would otherwise read as an escape, a
  leading `.`, and any `_` next to a `/` or in a run of three, so the
  separator stays unambiguous. Spaces stay spaces.
- the legacy format, which is what Logseq assumes when the key is absent. A
  namespace `/` becomes `%2F`, the same reserved characters are
  percent-encoded, and reading a filename back turns every `.` into `/`.

These mirror `tri-lb-file-name-sanity`, `legacy-url-file-name-sanity` and
`title-parsing` in Logseq 0.10. Page names compare case-insensitively, as
Logseq's do, after the same Unicode normalisation.

Journal filenames and titles use date-fns patterns. Only the tokens Logseq's
own settings offer are understood; a pattern with any other letter is refused,
and the caller falls back to the defaults.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date

TRIPLE_LOWBAR = ":triple-lowbar"
LEGACY = ":legacy"

#: Logseq's defaults for the journal patterns.
DEFAULT_JOURNAL_FILE_FORMAT = "yyyy_MM_dd"
DEFAULT_JOURNAL_TITLE_FORMAT = "MMM do, yyyy"

_RESERVED = re.compile(r'[:*?"<>|#\\]+')
_LEGACY_ANDROID = re.compile(r"[\\#|%]+")
_LEGACY_WINDOWS = re.compile(r'[:*?"<>|\\]+')
_PERCENT_ESCAPE = re.compile(r"%[0-9a-fA-F]{2}")
_WINDOWS_RESERVED_BODIES = frozenset(
    {"CON", "PRN", "AUX", "NUL"} | {f"COM{n}" for n in range(1, 10)} | {f"LPT{n}" for n in range(1, 10)}
)


def _encode(text: str) -> str:
    """JavaScript's `encodeURIComponent`, plus `*`, as Logseq applies it."""
    out: list[str] = []
    for char in text:
        if char.isascii() and (char.isalnum() or char in "-_.!~'()"):
            out.append(char)
        else:
            out.extend(f"%{byte:02X}" for byte in char.encode("utf-8"))
    return "".join(out)


def _sanity(name: str) -> str:
    """Logseq's `page-name-sanity`: no boundary slash, NFC."""
    name = name.removeprefix("/")
    name = name.removesuffix("/")
    return unicodedata.normalize("NFC", name)


def _decode_each(text: str) -> str:
    """Logseq's per-escape decoding: each `%XX` alone, kept when it is not a whole character."""

    def one(match: re.Match[str]) -> str:
        value = int(match.group(0)[1:], 16)
        return chr(value) if value < 0x80 else match.group(0)  # noqa: PLR2004 - ASCII

    return _PERCENT_ESCAPE.sub(one, text)


def _decode_uri_component(text: str) -> str:
    """JavaScript's `decodeURIComponent`, or the text unchanged where that would throw."""
    out = bytearray()
    index = 0
    while index < len(text):
        match = _PERCENT_ESCAPE.match(text, index)
        if match:
            out.append(int(match.group(0)[1:], 16))
            index = match.end()
        elif text[index] == "%":
            return text
        else:
            out += text[index].encode("utf-8")
            index += 1
    try:
        return out.decode("utf-8")
    except UnicodeDecodeError:
        return text


def page_to_file_body(name: str, name_format: str) -> str:
    """The filename, without `.md`, Logseq gives a page called `name`."""
    name = _sanity(name)
    if name_format != TRIPLE_LOWBAR:
        name = _LEGACY_ANDROID.sub(lambda m: _encode(m.group(0)), name)
        name = _LEGACY_WINDOWS.sub(lambda m: _encode(m.group(0)), name)
        return name.replace("/", "%2F").replace("*", "%2A")
    name = _PERCENT_ESCAPE.sub(lambda m: "%25" + m.group(0)[1:], name)
    name = _RESERVED.sub(lambda m: _encode(m.group(0)).replace("*", "%2A"), name)
    if name.startswith("."):
        name = "%2E" + name[1:]
    if name in _WINDOWS_RESERVED_BODIES or name.endswith("."):
        name += "/"
    for ambiguous in ("___", "_/", "/_"):
        name = name.replace(ambiguous, ambiguous.replace("_", "%5F"))
    return name.replace("/", "___")


def file_body_to_page(body: str, name_format: str) -> str:
    """The page name Logseq reads from a filename without `.md`."""
    if name_format != TRIPLE_LOWBAR:
        return _decode_uri_component(body.replace(".", "/"))
    name = _decode_each(body.replace("___", "/"))
    return "/".join(part for part in name.split("/") if part)


def page_key(name: str) -> str:
    """What two page names are compared by: Logseq lower-cases them after normalising."""
    return _sanity(name).lower()


def same_page(first: str, second: str) -> bool:
    return page_key(first) == page_key(second)


_MONTHS = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)
_DAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")

#: Longest first, so `MMMM` is never read as `MM` twice.
_TOKENS = ("yyyy", "yy", "MMMM", "MMM", "MM", "M", "do", "dd", "d", "EEEE", "EEE", "EE", "E")
_TOKEN = re.compile("|".join(_TOKENS) + r"|'(?:[^']|'')*'|[A-Za-z]|.", re.DOTALL)


def _ordinal(day: int) -> str:
    suffix = "th" if 11 <= day % 100 <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")  # noqa: PLR2004
    return f"{day}{suffix}"


def _render(token: str, day: date) -> str:  # noqa: PLR0911 - one return per token
    if token == "yyyy":
        return f"{day.year:04d}"
    if token == "yy":
        return f"{day.year % 100:02d}"
    if token == "MMMM":
        return _MONTHS[day.month - 1]
    if token == "MMM":
        return _MONTHS[day.month - 1][:3]
    if token in ("MM", "dd"):
        return f"{day.month if token == 'MM' else day.day:02d}"
    if token in ("M", "d"):
        return str(day.month if token == "M" else day.day)
    if token == "do":
        return _ordinal(day.day)
    if token == "EEEE":
        return _DAYS[day.weekday()]
    return _DAYS[day.weekday()][:3]


_PATTERNS = {
    "yyyy": r"(?P<year>\d{4})",
    "yy": r"(?P<year2>\d{2})",
    "MMMM": "(?P<monthname>" + "|".join(_MONTHS) + ")",
    "MMM": "(?P<monthabbr>" + "|".join(m[:3] for m in _MONTHS) + ")",
    "MM": r"(?P<month>\d{2})",
    "M": r"(?P<month>\d{1,2})",
    "do": r"(?P<day>\d{1,2})(?:st|nd|rd|th)",
    "dd": r"(?P<day>\d{2})",
    "d": r"(?P<day>\d{1,2})",
    "EEEE": "(?:" + "|".join(_DAYS) + ")",
    "EEE": "(?:" + "|".join(d[:3] for d in _DAYS) + ")",
    "EE": "(?:" + "|".join(d[:3] for d in _DAYS) + ")",
    "E": "(?:" + "|".join(d[:3] for d in _DAYS) + ")",
}


@dataclass(frozen=True)
class DateFormat:
    """A date-fns pattern such as `yyyy_MM_dd`, both ways."""

    pattern: str

    def __post_init__(self) -> None:
        self._parts()  # refuse an unknown token at construction

    def _parts(self) -> list[tuple[bool, str]]:
        """The pattern as (is_token, text) pairs; quoted text is literal."""
        parts: list[tuple[bool, str]] = []
        for match in _TOKEN.finditer(self.pattern):
            text = match.group(0)
            if text in _TOKENS:
                parts.append((True, text))
            elif text.startswith("'") and len(text) > 1:
                parts.append((False, text[1:-1].replace("''", "'") or "'"))
            elif text.isascii() and text.isalpha():
                raise ValueError(f"the date pattern {self.pattern!r} uses {text!r}, which this tool does not know")
            else:
                parts.append((False, text))
        return parts

    def format(self, day: date) -> str:
        return "".join(_render(text, day) if token else text for token, text in self._parts())

    def parse(self, text: str) -> date | None:
        """The date `text` names under this pattern, or None."""
        seen: set[str] = set()
        regex = ""
        for token, part in self._parts():
            if not token:
                regex += re.escape(part)
                continue
            piece = _PATTERNS[part]
            group = re.search(r"\?P<(\w+)>", piece)
            if group and group.group(1) in seen:
                piece = re.sub(r"\?P<\w+>", "", piece)  # a repeated field must not redefine its group
            elif group:
                seen.add(group.group(1))
            regex += piece
        match = re.fullmatch(regex, text)
        if match is None:
            return None
        fields = match.groupdict()
        year = (
            int(fields["year"]) if fields.get("year") else 2000 + int(fields["year2"]) if fields.get("year2") else None
        )
        month = int(fields["month"]) if fields.get("month") else None
        for key, names in (("monthname", _MONTHS), ("monthabbr", [m[:3] for m in _MONTHS])):
            if fields.get(key):
                month = names.index(fields[key]) + 1
        day = int(fields["day"]) if fields.get("day") else None
        if year is None or month is None or day is None:
            return None
        try:
            parsed = date(year, month, day)
        except ValueError:
            return None
        return parsed if self.format(parsed) == text else None
