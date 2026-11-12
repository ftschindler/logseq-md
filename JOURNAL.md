# JOURNAL - logseq-md

One dated entry per surprise met while building a stage: the command, the output, what was
expected and what was done instead. Entries about a real graph carry counts and invented
examples, never its text.

## 2026-11-10 - S1: the survey on the maintainer's graph

`uv run --script .scripts/survey_graph.py <graph>` over 961 files in `pages/` and `journals/`.

- **Round-trip: 961 of 961 byte-identical.** No line-model failure to fix.
- 820 files have no final newline, 39 have one, 102 are empty. Only `\n` endings; no CRLF, no
  lone `\r`, no BOM, no invalid UTF-8, no YAML front matter. All of those still have fixtures
  under `tests/fixtures/lines/`, per [DESIGN.md §9](DESIGN.md#what-the-fixtures-must-cover).
- 3,801 lines carry a prefix mixing tabs and spaces. Shapes seen at a bullet: `TAB TAB SP SP`
  (60), `TAB TAB SP SP SP SP` (4), `TAB SP SP` (3), `TAB TAB TAB SP SP` (1). `mixed-prefix.md`
  carries each.
- 465 whitespace-only lines and 317 lines with trailing whitespace: `whitespace-lines.md`.
- For later stages: 2 property lines at a deviant indent against 2,596 conventional; 17
  continuation orders, including `DEADLINE > id > :LOGBOOK:` (2) and `SCHEDULED > DEADLINE` (6);
  29 fenced lines that look like bullets, all in backtick fences, no tilde fence; 37 pages with
  only page properties; 15 dangling `((uuid))` targets of 623; maximum depth 9; 10 custom
  property keys.

**Surprise.** The first leak check failed on `front-matter.md`: its `---` delimiter lines occur
in the graph as horizontal rules. A run of dashes is structure, so `---` joined the leak
check's structure list rather than the fixture being changed.

## 2026-11-11 - S2: the parser comparison on the maintainer's graph

`uv run --script .scripts/survey_graph.py <graph>` over 963 files, now with a section comparing
the survey's own counts with `blocks.py`'s, construct by construct: 22,276 bullets, 2,608 block
property lines, 232 page-level ones, 191 fences, 373 scheduling lines, 28 drawers, 11,806
references, every marker and a maximum depth of 9. All agree.

**Surprise: the survey and the design meant different things by "after properties".** The first
comparison put 1,374 wrapped lines inside the content span where the parser put 1,373, and 0
outside it where the parser put 76. The survey only closed the span on a property, while
[DESIGN.md §7](DESIGN.md#the-five-writes) closes it on a property, a drawer or a scheduling
line; and it reopened the span after a `DEADLINE:`. The survey was wrong and now follows the
design. `wrapped.md` carries a line after a property and one after a `DEADLINE:`.

**Surprise: the survey's depth was an indent level, not a depth.** It agreed on the real graph,
but the synthetic graph in the tests has a bullet indented two tabs under a one-tab parent, which
the survey called depth 4 and the parser depth 3. The parser nests a bullet under the nearest
earlier bullet indented less, so a jump of two levels is one level of nesting; the survey now
counts the same way, independently. `indent-jump.md` is the fixture.

**Surprise: the leak check flagged structure.** `:LOGBOOK:` and a bulleted fence marker such as
`- ```python` occur in any graph that has tasks or code. Both joined the leak check's structure
list, a structure line with a bullet in front now counts as structure, and the `lines` evidence
was re-recorded for the changed script. A fixture line using Logseq's own
`logseq.order-list-type:: number` matched too and was replaced by an invented dotted key rather
than widening the list to property lines.

## 2026-11-12 - S3: the name check on the maintainer's graph

`uv run --script .scripts/survey_graph.py <graph>` over 963 files, now with a name check that
maps every filename to a page name or a date and back through `graph.py`: 256 of 256 page
filenames and 707 of 707 journal filenames map back, with no config note. The config is
`:triple-lowbar` with a custom `:journal/page-title-format`. Of the page filenames, 65 carry a
`___` namespace, 124 a single `_`, 9 a dot, 2 a space and 3 non-ASCII letters; none carries a
`%` escape. `tests/fixtures/graphs/triple-lowbar/` still has a filename for every escaping rule
Logseq 0.10 applies, since a graph with a colon in a page title would have them.

**Surprise: the design said spaces become underscores.** They do not, in either format; Logseq
keeps a space in the filename, and the real graph has two such files. [DESIGN.md
§4](DESIGN.md#pages-journals-and-namespaces) now says so.

**Surprise: a config without `:file/name-format` is not the current default.** Logseq reads a
missing key as the legacy format, so only a config that cannot be read at all falls back to
`:triple-lowbar`, and says so on stderr.

**Surprise: the leak check flagged a lone `}`.** The closing brace of a fixture `config.edn`
on its own line occurs in the graph's markdown. The brace moved onto the previous line rather
than widening the structure list.
