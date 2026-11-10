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
