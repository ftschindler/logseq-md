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
  the same construct can disagree. The name check imports the graph model,
  because whether a filename survives the trip to a page name and back is a
  question about that model and nothing else. The id scan imports the identity
  model, and only to time it and count what it finds. The write check imports
  the splice and the write planners, and applies them in memory only: for every
  block, it plans each in-block write, applies it to the parsed document, and
  counts whether every byte outside the planned lines is unchanged. Nothing is
  written. The append check does the same for `append-child`, with and without
  `--record-as`, and also counts whether the new child's prefix equals its
  siblings'. The indentation report is the survey's own: for every block with
  children, whether the children's prefixes extend the parent's, and by what.
"""

from __future__ import annotations

import re
import sys
import time
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from logseq_md import blocks as block_model  # noqa: E402
from logseq_md import graph as graph_model  # noqa: E402
from logseq_md import identity as identity_model  # noqa: E402
from logseq_md import lines as line_model  # noqa: E402
from logseq_md import splice as splice_model  # noqa: E402
from logseq_md import writes as write_model  # noqa: E402
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


def depth_of(prefix: bytes) -> int:
    """An indent's depth to compare, a tab counting as two spaces, as Logseq nests them."""
    return 2 * prefix.count(b"\t") + prefix.count(b" ")


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
        self.names: Counter[str] = Counter()
        self.name_failures: Counter[str] = Counter()
        self.id_scan: dict[str, object] = {}
        self.write_check: Counter[str] = Counter()
        self.indentation: Counter[str] = Counter()
        self.append_check: Counter[str] = Counter()
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


def shape(stem: str) -> str:
    """A filename as a shape: letters `a`, digits `9`, other text `u`, runs collapsed, punctuation kept."""
    out: list[str] = []
    for char in stem:
        token = "9" if char.isdigit() else "a" if char.isascii() and char.isalpha() else char if char.isascii() else "u"
        if not out or out[-1] != token or token not in "a9u":
            out.append(token)
    return "".join(out)


def name_check(result: Survey, graph: Path) -> None:
    """Every filename to a page name or a date and back, in memory, through the graph model."""
    model = graph_model.Graph(graph, graph_model.read_config(graph))
    result.names["config notes"] = len(model.config.notes)
    for path in model.files():
        if model.is_journal(path):
            day = model.journal_date(path)
            back = None if day is None else model.journal_path(day)
            kind = "journal"
        else:
            back = model.page_path(model.page_name(path))
            kind = "page"
            stem = path.stem
            for label, present in (
                ("a ___ namespace separator", "___" in stem),
                ("a single _", re.search(r"(?<!_)_(?!_)", stem) is not None),
                ("a space", " " in stem),
                ("a dot", "." in stem),
                ("non-ASCII", not stem.isascii()),
                ("an uppercase letter", any(c.isupper() for c in stem)),
            ):
                if present:
                    result.names[f"page filenames with {label}"] += 1
            for escape in re.findall(r"%[0-9A-Fa-f]{2}", stem):
                result.names[f"page filenames escaping {escape.upper()}"] += 1
        if back == path:
            result.names[f"{kind} filenames that map back"] += 1
        else:
            result.names[f"{kind} filenames that do not"] += 1
            result.name_failures[f"{kind}: {shape(path.stem)}"] += 1


def id_scan(result: Survey, graph: Path) -> None:
    """Time the graph-wide id scan the resolver runs per invocation, and count what it finds."""
    model = graph_model.Graph(graph, graph_model.read_config(graph))
    started = time.perf_counter()
    try:
        ids = identity_model.scan(model)
    except Refusal as refusal:
        result.id_scan["refused with exit"] = refusal.code
        return
    result.id_scan["seconds"] = f"{time.perf_counter() - started:.3f}"
    result.id_scan["distinct ids"] = len(ids.found)
    result.id_scan["ids on more than one block"] = len(ids.duplicates())
    result.id_scan["page-level ids"] = sum(1 for where in ids.found.values() for w in where if w.block is None)


WRITE_PLANS = {
    "ensure-id": lambda page, block: write_model.plan_ensure_id(
        page, block, lambda: "00000000-0000-4000-8000-000000000000"
    )[1],
    "set-property": lambda page, block: write_model.plan_set_property(page, block, "survey-key", "value"),
    "set-content": lambda page, block: write_model.plan_set_content(page, block, "text\nwrapped"),
    "set-marker": lambda page, block: write_model.plan_set_marker(page, block, None if block.marker else "TODO"),
}


def write_check(result: Survey, graph: Path) -> None:
    """Plan every in-block write on every block, apply it in memory, and count what stayed put."""
    model = graph_model.Graph(graph, graph_model.read_config(graph))
    for path in model.files():
        try:
            page = block_model.parse(line_model.read(path))
        except Refusal:
            continue
        before = page.document.to_bytes()
        sizes = [len(line.text().encode()) for line in page.document.lines]
        head = len(before) - sum(sizes)
        for block in page.blocks:
            for verb, plan in WRITE_PLANS.items():
                try:
                    edit = plan(page, block)
                except Refusal:
                    result.write_check[f"{verb}: refused"] += 1
                    continue
                if edit is None:
                    result.write_check[f"{verb}: already so"] += 1
                    continue
                after = splice_model.apply(page.document, [edit]).to_bytes()
                start = head + sum(sizes[: edit.start])
                end = head + sum(sizes[: edit.end])
                kept = after.startswith(before[:start]) and after.endswith(before[end:])
                result.write_check[f"{verb}: {'only its own lines' if kept else 'OTHER BYTES CHANGED'}"] += 1


def children_prefixes(data: bytes) -> list[tuple[bytes, list[bytes]]]:
    """Every bullet's prefix with its children's prefixes, read by the survey's own rules, fences skipped."""
    stack: list[tuple[bytes, list[bytes]]] = []
    done: list[tuple[bytes, list[bytes]]] = []
    fence: bytes | None = None
    for body, _ in split(data):
        content = body.lstrip(b" \t")
        if fence is not None:
            if content.startswith(fence):
                fence = None
            continue
        if not BULLET.match(content):
            opening = FENCE.match(content)
            fence = opening.group(1) if opening else None
            continue
        prefix = indent_of(body)
        while stack and depth_of(stack[-1][0]) >= depth_of(prefix):
            done.append(stack.pop())
        if stack:
            stack[-1][1].append(prefix)
        stack.append((prefix, []))
        opening = FENCE.match(content[1:].lstrip(b" \t"))
        fence = opening.group(1) if opening else None
    return done + stack


def indentation(result: Survey, graph: Path) -> None:
    """For every block with children, whether its children's prefixes extend its own, and by what shape."""
    for directory in ("pages", "journals"):
        root = graph / directory
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*.md")):
            if not path.is_file():
                continue
            with path.open("rb") as handle:
                data = handle.read()
            for parent, children in children_prefixes(data):
                if not children:
                    continue
                if len(set(children)) > 1:
                    result.indentation["children with differing prefixes"] += 1
                if all(child.startswith(parent) for child in children):
                    for step in {tokens(child[len(parent) :]) for child in children}:
                        result.indentation[f"extended by {step}"] += 1
                else:
                    result.indentation["a child prefix that does not extend the parent's"] += 1


def append_check(result: Survey, graph: Path) -> None:
    """Plan append-child on every block and page, with and without --record-as, apply in memory and count."""
    model = graph_model.Graph(graph, graph_model.read_config(graph))
    minted = "00000000-0000-4000-8000-000000000000"
    for path in model.files():
        try:
            page = block_model.parse(line_model.read(path))
        except Refusal:
            continue
        before = b"".join(line.text().encode() for line in page.document.lines)
        targets = [*page.blocks, None] if page.outline else []
        for parent in targets:
            for verb, kwargs in (
                ("append-child", {}),
                ("--record-as", {"child_id": minted, "record_as": "survey-key"}),
            ):
                if parent is None and kwargs:
                    continue
                try:
                    edits = write_model.plan_append_child(page, parent, "text\nwrapped", **kwargs)
                except Refusal:
                    result.append_check[f"{verb}: refused"] += 1
                    continue
                after = block_model.parse(splice_model.apply(page.document, edits))
                rest = b"".join(
                    line.text().encode() for i, line in enumerate(after.document.lines) if not _inserted(i, edits)
                )
                if rest == before:
                    outcome = "only inserted lines"
                elif rest.rstrip(b"\r\n") == before and not before.endswith((b"\n", b"\r")):
                    outcome = "only inserted lines, and the old last line's ending"
                else:
                    outcome = "OTHER BYTES CHANGED"
                result.append_check[f"{verb}: {outcome}"] += 1
                if parent is not None and parent.children:
                    new = next(b for b in after.blocks if b.parent == parent.index and b.index > parent.children[-1])
                    old = page.blocks[parent.children[-1]].prefix
                    same = new.prefix == old
                    result.append_check[f"{verb}: prefix {'matches' if same else 'DIFFERS FROM'} the siblings'"] += 1


def _inserted(index: int, edits: list) -> bool:
    shift = 0
    for edit in sorted(edits, key=lambda edit: edit.start):
        start = edit.start + shift
        if start <= index < start + len(edit.texts):
            return True
        shift += len(edit.texts) - (edit.end - edit.start)
    return False


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
    name_check(result, graph)
    id_scan(result, graph)
    write_check(result, graph)
    indentation(result, graph)
    append_check(result, graph)
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
    section("name check (filename -> page name or date -> filename)", sorted(result.names.items()))
    section("name check failures, by shape", result.name_failures.most_common())
    section("id scan (identity.scan, in memory)", list(result.id_scan.items()))
    section("write check (planned and applied in memory)", sorted(result.write_check.items()))
    section("indentation of children under their parent (by shape)", sorted(result.indentation.items()))
    section("append check (planned and applied in memory)", sorted(result.append_check.items()))
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
