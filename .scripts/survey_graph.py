#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# ///
"""Survey a real Logseq graph and print what it contains, as counts and shapes.

Usage:
  survey_graph.py <graph>

This is how a stage learns which fixtures to write. It reads a graph somebody
keeps private, so three rules bind it (IMPLEMENTATION.md, "Working with the real
graph"):

- It opens graph files with `"rb"` and nothing else, and writes nothing. A test
  reads this source and fails on any write call.
- It prints counts and shapes, never text. A property key the owner invented is
  printed as `custom-N`, because it can name a client or a project. An indent
  prefix is printed as tokens such as `TAB SP SP`, never as the line.
- Its counting is independent of `src/`, so a later stage can check its parser
  against it rather than agree with it. Only the round-trip imports the line
  model, because the round-trip is the question of whether that model holds,
  and the parser comparison imports the block model, so that the two counts of
  the same construct can disagree.
"""

from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from logseq_md import blocks as block_model  # noqa: E402
from logseq_md import lines as line_model  # noqa: E402
from logseq_md.exits import Refusal  # noqa: E402

#: Logseq's own property keys and those of plugins seen in the wild, printed by
#: name. Every other key is somebody's own word and is printed as `custom-N`.
KNOWN_KEYS = frozenset(
    {
        "id",
        "collapsed",
        "title",
        "alias",
        "aliases",
        "tags",
        "type",
        "template",
        "template-including-parent",
        "public",
        "filters",
        "icon",
        "heading",
        "background-color",
        "query-table",
        "query-properties",
        "query-sort-by",
        "query-sort-desc",
        "exclude-from-graph-view",
        "hl-page",
        "hl-color",
        "hl-stamp",
        "hl-type",
        "file",
        "file-path",
        "ls-type",
        "excalidraw-plugin",
        "card-last-interval",
        "card-repeats",
        "card-ease-factor",
        "card-next-schedule",
        "card-last-reviewed",
        "card-last-score",
        "created-at",
        "updated-at",
        "logseq.order-list-type",
        "logseq.table.version",
        "logseq.table.compact",
        "logseq.table.headers",
        "logseq.table.hover",
        "logseq.table.borders",
        "logseq.table.stripes",
        "logseq.table.max-width",
        "logseq.color",
    }
)

MARKERS = ("TODO", "DOING", "DONE", "LATER", "NOW", "WAITING", "CANCELED", "CANCELLED")
SKIPPED_DIRECTORIES = ("logseq/bak", "assets", "draws", "whiteboards")

LINE = re.compile(rb"([^\r\n]*)(\r\n|\n|\r|)")
BULLET = re.compile(rb"-(?:[ \t]|$)")
PROPERTY = re.compile(rb"([A-Za-z0-9_][^\s:]*?)::(?:[ \t]|$)(.*)")
DRAWER_OPEN = re.compile(rb":([A-Za-z][A-Za-z0-9_-]*):[ \t]*$")
FENCE = re.compile(rb"(`{3,}|~{3,})")
UUID = rb"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
BLOCK_REF = re.compile(rb"\(\((" + UUID + rb")\)\)")
EMBED = re.compile(rb"\{\{embed \(\((" + UUID + rb")\)\)\}\}")
MACRO = re.compile(rb"\{\{([A-Za-z][\w-]*)")
PAGE_LINK = re.compile(rb"\[\[([^\[\]]+)\]\]")
MULTI_TAG = re.compile(rb"(?:^|\s)#\[\[([^\[\]]+)\]\]")
TAG = re.compile(rb"(?:^|\s)#([^\s#\[\],;.!?\"'()]+)")
ID_VALUE = re.compile(UUID)
JOURNAL_NAME = re.compile(r"\d{4}_\d{2}_\d{2}")
NAME_FORMAT = re.compile(rb":file/name-format\s+(:[\w-]+)")
JOURNAL_FORMAT = re.compile(rb":journal/file-name-format\s+\"([^\"]*)\"")

TAB = ord("\t")


def tokens(prefix: bytes) -> str:
    """An indent prefix as tokens, so a shape is printed and never a line."""
    return " ".join("TAB" if char == TAB else "SP" for char in prefix) or "(none)"


def indent_of(body: bytes) -> bytes:
    return body[: len(body) - len(body.lstrip(b" \t"))]


def split(data: bytes) -> list[tuple[bytes, bytes]]:
    """Lines as (body, ending), independently of `src/`."""
    out: list[tuple[bytes, bytes]] = []
    position = 0
    while position < len(data):
        match = LINE.match(data, position)
        assert match is not None
        out.append((match.group(1), match.group(2)))
        position = match.end()
    return out


VALUE_SHAPES = (
    ("uuid", ID_VALUE),
    ("bool", re.compile(rb"(?i)true|false")),
    ("number", re.compile(rb"-?\d+(\.\d+)?")),
    ("page-links", re.compile(rb"\[\[[^\]]+\]\](\s*,\s*\[\[[^\]]+\]\])*")),
    ("tags", re.compile(rb"#\S+(\s+#\S+)*")),
    ("url", re.compile(rb"[a-z]+://.*")),
    ("path", re.compile(rb"(\.{0,2}/|[A-Za-z]:\\).*")),
    ("comma-list", re.compile(rb".*,.*")),
)


def value_shape(value: bytes) -> str:
    """A property value as a shape such as `uuid` or `url`, never as its text."""
    value = value.strip()
    if not value:
        return "empty"
    return next((name for name, pattern in VALUE_SHAPES if pattern.fullmatch(value)), "text")


class Survey:
    def __init__(self) -> None:
        self.counts: Counter[str] = Counter()
        self.prefixes: Counter[str] = Counter()
        self.keys: dict[str, Counter[str]] = {}
        self.custom_names: dict[bytes, str] = {}
        self.orders: Counter[str] = Counter()
        self.drawers: Counter[str] = Counter()
        self.macros: Counter[str] = Counter()
        self.clock_per_logbook: Counter[int] = Counter()
        self.round_trip_failures: Counter[str] = Counter()
        self.parser: Counter[str] = Counter()
        self.unclassified: Counter[str] = Counter()
        self.top_level: Counter[str] = Counter()
        self.block_ids: set[bytes] = set()
        self.block_refs: dict[bytes, set[bytes]] = {}
        self.max_depth = 0
        self.name_format = "(not set)"
        self.journal_format = "(not set)"

    def key_label(self, key: bytes) -> str:
        text = key.decode("utf-8", "replace")
        if text.lower() in KNOWN_KEYS:
            return text.lower()
        if key not in self.custom_names:
            self.custom_names[key] = f"custom-{len(self.custom_names) + 1}"
        return self.custom_names[key]

    def file(self, path: Path, graph: Path) -> None:  # noqa: PLR0912 - one counter per branch
        with path.open("rb") as handle:
            data = handle.read()
        relative = path.relative_to(graph)
        count = self.counts
        count["files"] += 1
        count[f"files in {relative.parts[0]}/"] += 1

        if path.parent.name == "pages" and "___" in path.stem:
            count["namespaced filenames (___)"] += 1
        if path.parent.name == "pages" and "%2F" in path.stem.upper():
            count["namespaced filenames (%2F)"] += 1
        if path.parent.name == "pages" and "." in path.stem:
            count["page filenames with a dot"] += 1
        if path.parent.name == "journals":
            key = "journal filenames YYYY_MM_DD" if JOURNAL_NAME.fullmatch(path.stem) else "journal filenames other"
            count[key] += 1

        self.round_trip(data, relative)
        self.parse(data, relative)

        try:
            data.decode("utf-8")
        except UnicodeDecodeError:
            count["files not valid UTF-8"] += 1
        if data.startswith(b"\xef\xbb\xbf"):
            count["files with a UTF-8 BOM"] += 1
            data = data[3:]
        if not data:
            count["files empty"] += 1
            return
        if not data.strip():
            count["files blank-only"] += 1
            return
        if data.endswith((b"\n", b"\r")):
            count["files with a final newline"] += 1
        else:
            count["files without a final newline"] += 1
        if data.startswith(b"---\n") or data.startswith(b"---\r\n"):
            count["files with YAML front matter"] += 1

        lines = split(data)
        endings = {ending for _, ending in lines if ending}
        for ending in endings:
            count[f"files with {ending!r} endings"] += 1
        if len(endings) > 1:
            count["files with mixed line endings"] += 1

        self.structure(lines)

    def round_trip(self, data: bytes, relative: Path) -> None:
        try:
            document = line_model.parse(data, name=str(relative))
        except Refusal:
            self.counts["round-trip refused (not UTF-8)"] += 1
            return
        result = document.to_bytes()
        if result == data:
            self.counts["round-trip byte-identical"] += 1
            return
        self.counts["round-trip differs"] += 1
        original, written = split(data), split(result)
        for index, (before, after) in enumerate(zip(original, written, strict=False)):
            if before != after:
                self.round_trip_failures[
                    f"line {index + 1}: indent {tokens(indent_of(before[0]))}, ending {before[1]!r} -> {after[1]!r}"
                ] += 1
                return
        self.round_trip_failures[f"line count {len(original)} -> {len(written)}"] += 1

    def parse(self, data: bytes, relative: Path) -> None:  # noqa: PLR0912 - one counter per construct
        """Count with the block model what `structure` counts on its own, for `compare`."""
        try:
            page = block_model.parse(line_model.parse(data, name=str(relative)))
        except Refusal:
            return
        count = self.parser
        lines = page.document.lines
        fenced = page.fenced
        count["bullets"] += len(page.blocks)
        count["page-level property lines"] += len(page.page_properties)
        count["code fences"] += len(page.fences)
        count["lines inside code fences"] += len(fenced) - len(page.fences)
        for fence in page.fences:
            for number in list(fence)[1:]:
                rest = lines[number].content
                if BULLET.match(rest.encode()):
                    count["fenced lines that look like bullets"] += 1
        if not page.outline and any(line.content for line in lines):
            if page.page_properties and all(
                kind is block_model.Kind.PAGE_PROPERTY or not lines[n].content
                for n, kind in enumerate(page.preamble_kinds)
            ):
                count["pages with no bullets: page properties only"] += 1
            elif not page.page_properties:
                count["pages with no bullets: prose only"] += 1
            else:
                count["pages with no bullets: properties and prose"] += 1
        references = [*page.references]
        for block in page.blocks:
            references += block.references
            count["maximum nesting depth"] = max(count["maximum nesting depth"], block.depth)
            if block.marker:
                count[f"marker {block.marker}"] += 1
            for prop in block.properties:
                conventional = lines[prop.line].indent == block.prefix + "  "
                count[f"property lines at {'the conventional' if conventional else 'a deviant'} indent"] += 1
            for offset, kind in enumerate(block.kinds):
                number = block.start + offset
                content = lines[number].content
                if kind is block_model.Kind.SCHEDULING:
                    count[content.split(":", 1)[0] + ":"] += 1
                elif kind is block_model.Kind.DRAWER and DRAWER_OPEN.match(content.encode()) and content != ":END:":
                    count["drawers"] += 1
                elif kind is block_model.Kind.CONTENT and content and number not in fenced:
                    inside = number < block.content_end
                    count["wrapped content lines" if inside else "wrapped content lines (after the content span)"] += 1
        for reference in references:
            count[f"references {reference.kind.value}"] += 1

    def compare(self) -> list[tuple[str, object]]:
        """Each construct as the survey counted it and as the block model did."""
        mine = self.counts
        derived = {
            "bullets": mine["bullets"],
            "page-level property lines": mine["page-level property lines"],
            "code fences": sum(n for key, n in mine.items() if key.startswith("code fences ")),
            "lines inside code fences": mine["lines inside code fences"],
            "fenced lines that look like bullets": mine["fenced lines that look like bullets"],
            "maximum nesting depth": self.max_depth,
            "DEADLINE:": mine["DEADLINE:"],
            "SCHEDULED:": mine["SCHEDULED:"],
            "drawers": sum(self.drawers.values()),
            "wrapped content lines": mine["wrapped content lines"],
            "wrapped content lines (after the content span)": mine["wrapped content lines (after the content span)"],
            "references page": mine["[[links]]"] - mine["#[[multi word tags]]"],
            "references tag": mine["#tags"] + mine["#[[multi word tags]]"],
            "references block": mine["((uuid)) references"],
            "references embed": mine["{{embed ((uuid))}}"],
        }
        for key in (
            "property lines at the conventional indent",
            "property lines at a deviant indent",
            "pages with no bullets: prose only",
            "pages with no bullets: page properties only",
            "pages with no bullets: properties and prose",
            *(f"marker {marker}" for marker in block_model.MARKERS),
        ):
            derived[key] = mine[key]
        rows: list[tuple[str, object]] = []
        for key, survey in derived.items():
            parser = self.parser[key]
            rows.append((key, f"{survey} {'==' if survey == parser else '!='} {parser}"))
        return rows

    def structure(self, lines: list[tuple[bytes, bytes]]) -> None:  # noqa: PLR0912, PLR0915
        # One pass over a file as a state machine (fence, drawer, current block).
        # Split up, the state would travel between functions and read worse.
        count = self.counts
        fence: bytes | None = None
        drawer: str | None = None
        clocks = 0
        bullet_prefix: bytes | None = None
        bullets = 0
        page_properties = 0
        prose = 0
        file_kinds: set[str] = set()
        order: list[str] = []
        content_after_property = False
        span_closed = False

        # The open ancestors' indent widths, a tab counting as two spaces. A bullet
        # is a child of the nearest earlier bullet indented less than it, so an
        # indent that jumps two levels nests one.
        widths: list[int] = []

        def nest(indent: bytes) -> None:
            width = 2 * indent.count(b"\t") + indent.count(b" ")
            while widths and widths[-1] >= width:
                widths.pop()
            widths.append(width)
            self.max_depth = max(self.max_depth, len(widths))

        def close_block() -> None:
            nonlocal order
            if len(order) > 1:
                self.orders[" > ".join(order)] += 1
            order = []

        for body, _ending in lines:
            indent = indent_of(body)
            rest = body[len(indent) :]
            if indent:
                file_kinds.add(
                    "tab" if b"\t" in indent and b" " not in indent else "space" if b"\t" not in indent else "mixed"
                )
                if b"\t" in indent and b" " in indent:
                    count["lines with a mixed tab/space prefix"] += 1
            if body and not rest:
                count["whitespace-only lines"] += 1
            if body.endswith((b" ", b"\t")) and rest:
                count["lines with trailing whitespace"] += 1

            if fence is not None:
                count["lines inside code fences"] += 1
                if FENCE.match(rest) and rest.startswith(fence[:1] * len(fence)):
                    fence = None
                    continue
                if BULLET.match(rest):
                    count["fenced lines that look like bullets"] += 1
                elif PROPERTY.match(rest):
                    count["fenced lines that look like properties"] += 1
                elif DRAWER_OPEN.match(rest) or rest.strip() == b":END:":
                    count["fenced lines that look like drawers"] += 1
                continue

            fence_open = FENCE.match(rest.removeprefix(b"- "))
            if fence_open:
                fence = fence_open.group(1)
                count[f"code fences {fence[:1].decode()}"] += 1
                if BULLET.match(rest):
                    bullets += 1
                    count["bullets"] += 1
                    nest(indent)
                continue

            if drawer is not None:
                if rest.strip() == b":END:":
                    if drawer == "LOGBOOK":
                        self.clock_per_logbook[clocks] += 1
                    drawer = None
                elif rest.startswith(b"CLOCK:"):
                    clocks += 1
                continue

            if BULLET.match(rest):
                close_block()
                bullets += 1
                count["bullets"] += 1
                bullet_prefix = indent
                self.prefixes[tokens(indent)] += 1
                nest(indent)
                text = rest[1:].lstrip(b" \t")
                for marker in MARKERS:
                    if text == marker.encode() or text.startswith(marker.encode() + b" "):
                        count[f"marker {marker}"] += 1
                        break
                self.references(text)
                content_after_property = False
                span_closed = False
                continue

            if not rest:
                continue

            prop = PROPERTY.match(rest)
            if prop:
                key = prop.group(1)
                label = self.key_label(key)
                self.keys.setdefault(label, Counter())[value_shape(prop.group(2))] += 1
                if bullet_prefix is None:
                    page_properties += 1
                    count["page-level property lines"] += 1
                else:
                    expected = bullet_prefix + b"  "
                    count[
                        "property lines at the conventional indent"
                        if indent == expected
                        else "property lines at a deviant indent"
                    ] += 1
                    if label in ("id", "collapsed"):
                        order.append(label)
                    if label == "id":
                        self.block_ids.add(prop.group(2).strip().lower())
                    if content_after_property:
                        count["property lines after wrapped content that followed a property"] += 1
                    span_closed = True
                continue

            drawer_open = DRAWER_OPEN.match(rest)
            if drawer_open:
                drawer = drawer_open.group(1).decode()
                self.drawers[drawer] += 1
                clocks = 0
                if drawer == "LOGBOOK" and bullet_prefix is not None:
                    order.append(":LOGBOOK:")
                span_closed = bullet_prefix is not None
                continue

            for keyword in (b"DEADLINE:", b"SCHEDULED:"):
                if rest.startswith(keyword):
                    count[keyword.decode()] += 1
                    if bullet_prefix is not None:
                        order.append(keyword.decode().rstrip(":"))
                    break
            else:
                if bullet_prefix is None:
                    prose += 1
                    self.references(rest)
                    continue
                count["wrapped content lines (after the content span)" if span_closed else "wrapped content lines"] += 1
                if span_closed:
                    content_after_property = True
                self.references(rest)
                continue
            # A scheduling line closes the content span, like a property or a drawer.
            span_closed = bullet_prefix is not None

        close_block()
        if fence is not None:
            count["files ending inside an open fence"] += 1
        if drawer is not None:
            count["files ending inside an open drawer"] += 1
        if bullets == 0:
            if prose and not page_properties:
                count["pages with no bullets: prose only"] += 1
            elif page_properties and not prose:
                count["pages with no bullets: page properties only"] += 1
            else:
                count["pages with no bullets: properties and prose"] += 1
        if file_kinds:
            count[f"files indented with {'+'.join(sorted(file_kinds))}"] += 1

    def references(self, text: bytes) -> None:
        count = self.counts
        count["[[links]]"] += len(PAGE_LINK.findall(text))
        count["#[[multi word tags]]"] += len(MULTI_TAG.findall(text))
        count["#tags"] += len(TAG.findall(text))
        embeds = EMBED.findall(text)
        count["{{embed ((uuid))}}"] += len(embeds)
        refs = BLOCK_REF.findall(text)
        count["((uuid)) references"] += len(refs) - len(embeds)
        for name in MACRO.findall(text):
            if name != b"embed":
                self.macros[name.decode("utf-8", "replace")] += 1
        for ref in refs:
            self.block_refs.setdefault(ref.lower(), set())

    def config(self, graph: Path) -> None:
        config = graph / "logseq" / "config.edn"
        if not config.is_file():
            return
        with config.open("rb") as handle:
            data = handle.read()
        match = NAME_FORMAT.search(data)
        self.name_format = match.group(1).decode() if match else "(not set)"
        match = JOURNAL_FORMAT.search(data)
        self.journal_format = match.group(1).decode() if match else "(not set)"


def survey(graph: Path) -> Survey:
    """Walk `pages/` and `journals/` and count what they hold."""
    result = Survey()
    for child in sorted(graph.iterdir()):
        if child.is_dir():
            result.top_level[child.name + "/"] = sum(1 for p in child.rglob("*.md") if p.is_file())
    for directory in ("pages", "journals"):
        root = graph / directory
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*.md")):
            if path.is_file():
                result.file(path, graph)
    result.config(graph)
    dangling = [ref for ref in result.block_refs if ref not in result.block_ids]
    result.counts["distinct ((uuid)) targets"] = len(result.block_refs)
    result.counts["dangling ((uuid)) targets"] = len(dangling)
    return result


def report(result: Survey) -> str:
    out: list[str] = []

    def section(title: str, rows: list[tuple[str, object]]) -> None:
        out.append(f"\n## {title}\n")
        width = max((len(name) for name, _ in rows), default=0)
        out.extend(f"  {name:<{width}}  {value}" for name, value in rows)

    section("counts", sorted(result.counts.items()))
    section("top-level directories (markdown files)", sorted(result.top_level.items()))
    section("skipped by design", [(name, "skipped") for name in SKIPPED_DIRECTORIES])
    section("config", [(":file/name-format", result.name_format), (":journal/file-name-format", result.journal_format)])
    section("bullet prefixes", result.prefixes.most_common())
    section("maximum nesting depth", [("depth", result.max_depth)])
    section("continuation order (id, collapsed, DEADLINE, SCHEDULED, :LOGBOOK:)", result.orders.most_common())
    section(
        "property keys (custom keys anonymised)",
        [
            (key, f"{sum(shapes.values())}  {dict(shapes.most_common())}")
            for key, shapes in sorted(result.keys.items(), key=lambda kv: -sum(kv[1].values()))
        ],
    )
    section("drawers", result.drawers.most_common())
    section("CLOCK lines per logbook", [(f"{n} CLOCK", c) for n, c in sorted(result.clock_per_logbook.items())])
    section("macros other than embed", result.macros.most_common())
    section("parser comparison (survey == blocks.py)", result.compare())
    section("round-trip failures (first differing line)", result.round_trip_failures.most_common())
    section("unclassified", result.unclassified.most_common())
    return "\n".join(out).lstrip("\n") + "\n"


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print(__doc__, file=sys.stderr)
        return 2
    graph = Path(argv[0])
    if not (graph / "pages").is_dir() and not (graph / "journals").is_dir():
        print(f"error: {graph} has neither pages/ nor journals/", file=sys.stderr)
        return 5
    sys.stdout.write(report(survey(graph)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
