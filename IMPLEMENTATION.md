# IMPLEMENTATION - logseq-md

**Status:** the plan of record. [DESIGN.md](DESIGN.md) remains the sole source of truth for
*what* gets built. This document says *in which order*, *what each stage has to prove*, and
*which* of the design's open questions each stage answers.

**Section references.** A `§N` link points at the matching section of [DESIGN.md](DESIGN.md).

**This plan assumes nothing from this repository except [DESIGN.md](DESIGN.md) and this
file.** A fresh session should be able to start at any unticked stage whose prerequisites have
merged, and know what it owns, what it must not touch and what it hands on.

**The end state is a published package and a skill.** `logseq-md` on PyPI, so that
`uvx logseq-md --help` works on a machine with nothing installed beyond uv
([§11](DESIGN.md#11-windows-linux-python)), carrying the read and write verbs of
[§10](DESIGN.md#10-commands), plus a skill subscribable with `akit`
([§12](DESIGN.md#12-the-skill)).

## Status

- [ ] **[S0](#s0---the-release-pipeline)** - The release pipeline
- [ ] **[S1](#s1---the-fixture-graph)** - The fixture graph, *on the maintainer's machine*
- [ ] **[S2](#s2---lines-the-round-trip-gate-and-the-cli-frame)** - Lines, the round-trip gate, and the CLI frame
- [ ] **[S3](#s3---blocks)** - Blocks
- [ ] **[S4](#s4---graphs-config-and-names)** - Graphs, config and names
- [ ] **[S5](#s5---identity-and-targets)** - Identity and targets
- [ ] **[S6](#s6---enumeration-blocks-pages-properties)** - Enumeration: `blocks`, `pages`, `properties`
- [ ] **[S7](#s7---resolution-show-backlinks)** - Resolution: `show`, `backlinks`
- [ ] **[S8](#s8---the-splice-and-the-in-block-writes)** - The splice, and the in-block writes
- [ ] **[S9](#s9---append-child-and---record-as)** - `append-child` and `--record-as`
- [ ] **[S10](#s10---the-skill)** - The skill
- [ ] **[S11](#s11---the-release-gate)** - The release gate

## How to use it

**One stage is one session and one pull request.** A stage names what it owns, what it must
not touch and the interfaces it leaves for the next. A session that finds itself editing
another stage's files has either found a design bug, which goes into [DESIGN.md](DESIGN.md) in
the same diff, or has drifted.

**Order is a dependency graph, not a queue.** Each stage lists what it needs, and only a
merged stage counts.

```text
S0 ──────────────────────────────────────────────┐
S1 ── S2 ─┬─ S3 ─┬─ S5 ─┬─ S6 ─┐                 │
          └─ S4 ─┘      ├─ S7 ─┼─ S10 ── S11 ────┘
                        └─ S8 ── S9 ─┘
```

Read as: S0 and S1 need nothing and can start at once. S3 and S4 run in parallel after S2. S6,
S7 and S8 run in parallel after S5. S11 needs everything, S0 included.

**The repository stays releasable after every stage.** A stage ends with a green suite on both
operating systems. One that cannot merge on its own is too large, and splitting it is part of
doing it.

**Answer an open question only when a stage forces it.** Each stage names which of
[§13](DESIGN.md#13-still-open) it settles. Most settle none.

**Keep a journal.** `JOURNAL.md` beside this file, created by the first stage that has
something to record: one dated entry per surprise, with the actual command and output, what was
expected and what was done instead. It is how a later stage learns what an earlier one found
without inheriting its session. **It is bound by rule 8 like everything else**: an entry about
the real graph carries counts and invented examples, never its text.

## Before starting

| What | Where | Why |
| --- | --- | --- |
| The design | [DESIGN.md](DESIGN.md) | every format rule, verb, flag and exit code is specified there |
| The guard suite | this repository | `make bootstrap` once, then `make check` and `make test` |
| The sibling project | [ftschindler/federated-agent-kits](https://github.com/ftschindler/federated-agent-kits) | its `release.yml`, `rehearsal.yml`, `.scripts/version.py` and `skills/` are what [S0](#s0---the-release-pipeline) and [S10](#s10---the-skill) port rather than reinvent |
| A real graph | the maintainer's machine, `LOGSEQ_MD_TEST_GRAPH` | [S1](#s1---the-fixture-graph) only; no other stage needs or gets one |

Two constraints bind every stage and are easy to breach without noticing: **Python with an
empty runtime dependency list**, and **Windows and Linux equally**
([§11](DESIGN.md#11-windows-linux-python), [§3](DESIGN.md#3-rules-of-the-build) rule 6). The
second is kept by the CI matrix that already exists, which every stage keeps green.

## What every stage delivers

These are not repeated under each stage. A stage is not done without them.

**Tests that could fail.** Every behaviour the stage adds has a test that fails when the
behaviour is removed. Byte-level behaviour is asserted on bytes, read with `open(..., "rb")`,
never on decoded text that might have had its line endings translated.

**The fixture graph stays the acceptance corpus.** From [S2](#s2---lines-the-round-trip-gate-and-the-cli-frame)
on, `tests/fixtures/graph/` round-trips byte-identically on every CI run. A stage that adds a
parser or writer feature adds the fixture case that exercises it, either into that graph or as
a small file under `tests/fixtures/<stage-topic>/`.

**Nothing from a personal graph enters the repository** ([§3](DESIGN.md#3-rules-of-the-build)
rule 8). Not in a fixture, a test name, a docstring, a journal entry or a commit message.

**The opacity check holds.** No property key other than `id` and `collapsed` appears as a
literal in `src/`, and no code branches on a caller-supplied key
([§5](DESIGN.md#why-opacity-is-the-half-that-matters)). The test enforcing it lands in
[S2](#s2---lines-the-round-trip-gate-and-the-cli-frame); the drop list printed by
`logseq-md properties` ([§6](DESIGN.md#properties-in-output)) is the one named exception and
lives in one module the test allows by path.

**Exit codes from one place.** The table in [§10](DESIGN.md#exit-codes) is defined once, in
`src/logseq_md/exits.py`, and every refusal uses a name from it rather than a literal number.

**Help that carries the verb.** Every command's `--help` says what it does in one sentence,
what it writes and never writes, one worked example with invented arguments, and every flag in
one line. The skill in [S10](#s10---the-skill) leans on this rather than repeating it.

**`--json` from the first verb that has output.** Text is for people and may be reworded; JSON
is what a script parses ([§6](DESIGN.md#what-a-read-returns)). Every command that prints a
result offers both.

**Windows-safe by construction.** `pathlib.Path` throughout, files opened in binary mode on the
read and write paths, no shell, no symlink, no assumption that `make` exists.

**Documentation in the same diff.** `README.md` and the command's own help change with the
behaviour, never in a follow-up. The README's "Pre-alpha" paragraph says what works so far.

**One bump label on the pull request**, per [CONTRIBUTING.md](CONTRIBUTING.md). Stages that add
a verb are `minor`; S1 and S10 are `minor` too since they ship; S0 is `minor` so that its own
merge is the first release.

## S0 - The release pipeline

**Goal.** A merged pull request labelled `major`, `minor` or `patch` publishes to PyPI without
anybody touching a version number. [CONTRIBUTING.md](CONTRIBUTING.md) already promises this and
nothing implements it yet.

**Needs.** Nothing. Independent of every other stage.

**Build.** Port from federated-agent-kits, retargeted to `logseq-md`:

- `.scripts/version.py` with `current`, `next <level>`, `write <version>` and
  `check-untouched <base-ref>`. It edits the one `version =` line in `pyproject.toml` and no
  other byte of the file.
- `.github/workflows/release.yml`. On a pull request, a job `🏷 (the pull request says how big
  it is)` refusing anything other than exactly one of `major`, `minor`, `patch`, `no-release`,
  and refusing a diff that edits the version line. On a push to `main`, a job that reads the
  merged pull request's label, writes the version, builds, runs `twine check --strict`,
  commits and tags in one atomic push, and publishes to PyPI with trusted publishing. Publishing
  is the last step because it is the only one that cannot be undone.
- `.github/workflows/rehearsal.yml`, a job `🧪 (publish a rehearsal and install it)`: on every
  pull request, publish `<next>.dev<run id>` to TestPyPI, install it back with `uvx`, and run
  `logseq-md --version`. A separate workflow file because a trusted publisher is matched on the
  filename.
- The four labels created in the repository.
- Tests for `version.py` under `tests/`, since it is code this repository runs.

**By hand, once, by the maintainer.** These are part of the stage, not a follow-up. A release
job that cannot push is not a release job.

1. PyPI trusted publisher for `release.yml` in environment `pypi`, and TestPyPI for
   `rehearsal.yml` in environment `testpypi`. Both environments created in the repository.
2. A GitHub App holding `contents: write`, installed on this repository, with its client id and
   private key as `RELEASE_APP_CLIENT_ID` and `RELEASE_APP_PRIVATE_KEY`. The sibling's app may
   be reused by installing it here.
3. The app added to the bypass list of the `main-requires-checks-and-prs` ruleset.
4. `🏷 (the pull request says how big it is)` and `🧪 (publish a rehearsal and install it)`
   added to that ruleset's required checks, **after** each has reported once, since a required
   check that never reports blocks every merge.

**Done when.** This stage's own merge publishes `0.1.0`, `uvx logseq-md --version` prints it
on both operating systems, and the tag `v0.1.0` points at the release commit.

**Settles.** Nothing in [§13](DESIGN.md#13-still-open).

**Leave alone.** `src/`. A release pipeline that ships the existing frame is the test of the
pipeline.

## S1 - The fixture graph

**Goal.** A synthetic graph in `tests/fixtures/graph/` that contains every structure the
maintainer's real graph contains, at least once, with every word invented. This is the corpus
CI runs the round-trip gate against ([§9](DESIGN.md#9-tests)), and the reason most
contributors never need a real graph.

**Needs.** Nothing. **Runs on the maintainer's machine**, with `LOGSEQ_MD_TEST_GRAPH` pointing
at a real graph. An agent without that variable stops and says so.

**The rule this stage exists to keep.** The agent never reads a file of the real graph into
its context. It reads the output of a survey script that reports **shapes and counts, never
text**. Everything in the fixture is written from those shapes and from
[§4](DESIGN.md#4-the-file-format), with invented words.

**Build.**

- `.scripts/survey_graph.py <graph>`: stdlib only, read-only, deliberately independent of
  `src/` so it can later check the parser rather than agree with it. It prints a table of
  constructs and counts, covering at least every measurement quoted in
  [§4](DESIGN.md#4-the-file-format) and [§9](DESIGN.md#what-the-fixtures-must-cover):
  - files with and without a final newline; empty and blank-only files; line-ending kinds;
    files that are not valid UTF-8; YAML front matter;
  - indentation per file (tabs, spaces, mixed) and per prefix (mixed inside one prefix),
    with the prefix rendered as tokens such as `TAB SP SP`, never as the line;
  - maximum nesting depth;
  - property lines at the conventional indent and at a deviant one; the set of property
    **keys** with counts, since keys are format vocabulary rather than content; observed
    orders of `id::`, `collapsed::`, `DEADLINE:`, `SCHEDULED:` and `:LOGBOOK:`;
  - wrapped content lines, before and after properties;
  - each marker word; `DEADLINE:`, `SCHEDULED:`; drawers by name; `CLOCK:` lines per logbook;
  - code fences by fence character, and lines inside them that look like bullets, properties
    or drawers;
  - pages with no bullets, split into prose-only and page-property-only;
  - `[[links]]`, `#tags`, `#[[multi word tags]]`, `((uuid))`, `{{embed ((uuid))}}`, and any
    other `{{...}}` macro names; dangling references; reference cycles;
  - namespaced filenames, the `:file/name-format` value, and the journal filename format;
  - which top-level directories exist, so the skip list in
    [§4](DESIGN.md#what-the-tool-does-not-read) is confirmed;
  - anything the script meets that it cannot classify, by count and shape.
- `tests/fixtures/graph/`: a small graph with `pages/`, `journals/`, `logseq/config.edn`, and
  a `logseq/bak/` file the reader must skip. Every construct the survey counted at least once
  appears at least once. Constructs in [§9](DESIGN.md#what-the-fixtures-must-cover) that the
  real graph lacks (CRLF, mixed endings, non-UTF-8, front matter) go in too.
- `tests/fixture_coverage.toml`, mapping each survey construct to the fixture files that carry
  it. It lives outside the fixture graph because anything inside it gets parsed. A test runs
  the survey on the fixture graph and asserts a non-zero count for every row.
- A `graph`-marked test, run by `make test_graph`, asserting:
  - every construct the survey finds in the real graph is present in the fixture graph, so a
    construct that turns up later in real use fails locally until a fixture lands, which is the
    rule in [§9](DESIGN.md#the-corpus-problem) made mechanical;
  - **no line of the fixture graph occurs verbatim in the real graph**, other than lines made
    only of structure: bullets, whitespace, property keys with an id-shaped or boolean value,
    fence markers, `:END:`. This is the leak check, and it runs every time the maintainer runs
    `make test_graph`.
- The `.gitattributes` rule `tests/fixtures/** -text` and the hook exclusions already exist;
  confirm a Windows checkout leaves the CRLF fixture's bytes alone.

**Before the pull request.** The maintainer reads the full fixture diff for anything
recognisable, because the leak check catches copied lines and not paraphrase.

**Done when.** `make test_graph` passes against the real graph, the survey's output on the
fixture graph covers every row in `tests/fixture_coverage.toml`, and the survey output that
informed the fixture is summarised in `JOURNAL.md` as counts only.

**Settles.** Nothing in [§13](DESIGN.md#13-still-open). It may correct a count in
[§4](DESIGN.md#4-the-file-format), in the same diff, if the survey disagrees with it.

**Leave alone.** `src/`. The survey is a test tool and stays in `.scripts/`.

## S2 - Lines, the round-trip gate, and the CLI frame

**Goal.** Any file in a graph is held as lines that write back to the identical bytes, the
gate in [§9](DESIGN.md#the-gate) runs on every CI run, and the CLI has a slot for every verb so
parallel stages do not collide in `cli.py`.

**Needs.** [S1](#s1---the-fixture-graph).

**Build.**

- `src/logseq_md/lines.py`: read a file as bytes, decode strictly as UTF-8, and split into
  lines that each keep their indent prefix, their content and their exact ending (`\n`,
  `\r\n`, `\r` or none). Serialising the unmodified lines returns the original bytes. A file
  that is not valid UTF-8 is a refusal with exit code 5, naming the file. A leading UTF-8 BOM
  is retained.
- `src/logseq_md/exits.py`: the [§10](DESIGN.md#exit-codes) table as named constants, and one
  exception type carrying a code and a message that `main` turns into stderr plus that code.
  `cli.py`'s existing `OK`/`FAILED` move here.
- The CLI frame in `cli.py`: every verb in [§10](DESIGN.md#10-commands) registered as an
  argparse subcommand with its arguments and flags, a shared `--graph` option, and a handler
  table mapping verb name to function. Every handler is a stub that prints "not implemented
  yet" and exits 2. Later stages replace one handler and touch nothing else in the frame.
- `tests/test_round_trip.py`: every file in `tests/fixtures/graph/` read and written back to a
  temporary path, byte-identical. A `graph`-marked twin runs the same over
  `LOGSEQ_MD_TEST_GRAPH`, skipping the directories in
  [§4](DESIGN.md#what-the-tool-does-not-read).
- `tests/test_opacity.py`: the grep from [§5](DESIGN.md#why-opacity-is-the-half-that-matters)
  over `src/`, failing on any quoted property key other than `id` and `collapsed`, with the
  drop-list module named in [S6](#s6---enumeration-blocks-pages-properties) allowed by path.
- `tests/test_cli.py` gains: every verb in [§10](DESIGN.md#10-commands) is registered; a test
  listing the verbs still stubbed, which [S11](#s11---the-release-gate) asserts is empty.

**Done when.** The gate is green over the fixture graph on Linux and Windows, `make test_graph`
is green on the maintainer's machine, and `logseq-md <verb> --help` works for every verb.

**Settles.** Nothing in [§13](DESIGN.md#13-still-open).

**Leave alone.** Block structure. A line is not yet a bullet, a property or a drawer.

## S3 - Blocks

**Goal.** A page's lines become blocks with structure alongside them, never in place of them
([§9](DESIGN.md#the-gate): "structure can be added alongside the source representation").

**Needs.** [S2](#s2---lines-the-round-trip-gate-and-the-cli-frame).

**Build.** `src/logseq_md/blocks.py`, implementing [§4](DESIGN.md#4-the-file-format):

- A block is a line range in its file: the bullet line, its depth, its indent prefix, and for
  each continuation line a classification of exactly one of wrapped content, property,
  `DEADLINE:`/`SCHEDULED:`, drawer line (`:LOGBOOK:` through `:END:`, and any other
  `:NAME:` drawer), or child. Parent and children are links by index, not copies.
- The content span: the bullet line plus wrapped lines, up to the first property, drawer,
  scheduling line or child ([§7](DESIGN.md#the-five-writes)).
- Properties recognised by shape and position, never by a computed indent
  ([§4](DESIGN.md#properties)). Each keeps its key and its raw value; order is preserved and
  never interpreted.
- Code fence state, backtick and tilde, so a fenced line is content however it looks.
- The marker, when the content starts with one of the seven in
  [§7](DESIGN.md#the-five-writes).
- References found in the content: `[[page]]`, `#tag`, `#[[tag]]`, `((uuid))`,
  `{{embed ((uuid))}}`, with their positions. Not resolved here.
- Page-level properties before the first bullet, and pages with no bullets, which parse to a
  page with no blocks and a flag saying so ([§6](DESIGN.md#pages-that-are-not-outlines)).
- A `graph`-marked test comparing the parser's counts with `.scripts/survey_graph.py`'s on the
  real graph, construct by construct. A disagreement is a parser bug or a survey bug, and the
  fixture that settles it lands with the fix.

**Done when.** Every fixture file parses, every block's line range tiles its file with no gaps
or overlaps, the round-trip gate still holds, and the survey comparison is green locally.

**Settles.** Nothing.

**Leave alone.** Files across a graph, names, ids. This stage sees one file at a time.

## S4 - Graphs, config and names

**Goal.** A path becomes a graph, and a page name, a filename and a journal date convert into
one another the way the graph's own config says.

**Needs.** [S2](#s2---lines-the-round-trip-gate-and-the-cli-frame). Runs in parallel with
[S3](#s3---blocks).

**Build.**

- `src/logseq_md/graph.py`: the graph from `--graph` or `LOGSEQ_MD_GRAPH`, flag winning
  ([§8](DESIGN.md#8-graphs)). A path without `pages/` or `journals/` is not a graph: exit 5.
  File enumeration over `pages/` and `journals/` only, skipping `logseq/bak`, `assets/`,
  `draws/` and `whiteboards/` ([§4](DESIGN.md#what-the-tool-does-not-read)).
- `src/logseq_md/edn.py`: the narrow reader [§4](DESIGN.md#pages-journals-and-namespaces)
  describes, reading `:file/name-format` and the journal file and title formats from
  `logseq/config.edn`. Its docstring says it is not a general EDN parser and must not become
  one. Comments, nested maps and strings containing `:` are handled; anything else it does not
  understand falls back to Logseq's current defaults and says so on stderr.
- `src/logseq_md/names.py`: page name to filename and back for `:triple-lowbar` and the legacy
  format, including namespaces, spaces and the characters Logseq escapes; journal date to
  filename and back. Case handling matches Logseq: page names compare case-insensitively.
- Fixtures: a `config.edn` per format, one with comments and awkward strings, one the narrow
  reader cannot read.

**Done when.** Every file in the fixture graph maps to a page name or a date and back to the
same filename, and `logseq-md pages` has what it needs except output.

**Settles.** Nothing.

**Leave alone.** Block parsing.

## S5 - Identity and targets

**Goal.** Every `<target>` form in [§10](DESIGN.md#targets) resolves to a block or a page, and
the tool can mint an id the way Logseq does.

**Needs.** [S3](#s3---blocks) and [S4](#s4---graphs-config-and-names).

**Build.**

- `src/logseq_md/identity.py`: squuid minting per [§5](DESIGN.md#logseqs-uuids-are-not-random),
  with the clock injectable so a test pins it. A test mints at a fixed timestamp and asserts the
  first eight hex digits and the version nibble.
- A graph-wide scan that maps every `id::` to its file and block. Built per invocation, never
  stored ([§3](DESIGN.md#3-rules-of-the-build) rule 5). Two blocks sharing an id is reported,
  not resolved silently.
- `src/logseq_md/targets.py`: one resolver for a uuid, a page name, a journal date and
  `page:line`. A miss is exit 1. A `page:line` handed to a write verb is exit 2 naming
  `ensure-id` ([§10](DESIGN.md#targets)); the resolver offers a flag for that so the write
  stages do not re-implement it.
- Fixtures for each target form, an ambiguous page name, and a duplicated id.

**Done when.** Every target form resolves against the fixture graph, and the scan of a
3,000-file graph takes under two seconds on the maintainer's machine, recorded in the journal.

**Settles.** Nothing.

**Leave alone.** Output formatting, and anything that writes.

## S6 - Enumeration: `blocks`, `pages`, `properties`

**Goal.** A caller can list what is in a graph and filter it, with ancestors on every block.

**Needs.** [S5](#s5---identity-and-targets). Runs in parallel with [S7](#s7---resolution-show-backlinks)
and [S8](#s8---the-splice-and-the-in-block-writes).

**Build.**

- `blocks`, with the filters in [§6](DESIGN.md#searching): `--marker`, `--tag`,
  `--has-property <key>`, `--since`/`--until`, `--page`, composing as a conjunction. Every
  result carries its ancestor chain ([§6](DESIGN.md#what-a-read-returns)); `--children` adds
  the subtree. `--since`/`--until` filter journals by their date, and say in `--help` that a
  page has no date.
- `pages`: every page and journal, including the ones with no outline.
- `properties`: prints the drop list. `src/logseq_md/policy.py` holds that list and nothing
  else, and is the one module the opacity test allows by path.
- `src/logseq_md/output.py`: the three shapes in [§6](DESIGN.md#what-a-read-returns). Text
  for people, `--json` with a documented shape, `--paths` one path per line. The JSON shape is
  written down in `--help` and in a test that pins it. Property stripping with `--raw` and
  `--keep <key>` lives here, so [S7](#s7---resolution-show-backlinks) uses the same code.

**Done when.** Each filter, alone and combined, returns the expected blocks from the fixture
graph in all three shapes, and `--has-property` takes any key without the tool knowing it.

**Settles.** Nothing.

**Leave alone.** Reference resolution beyond reporting that a reference exists.

## S7 - Resolution: `show`, `backlinks`

**Goal.** One block or page, with its references resolved and its ancestors present, and the
reverse question of what points at a page.

**Needs.** [S5](#s5---identity-and-targets). Uses `output.py` from
[S6](#s6---enumeration-blocks-pages-properties) if it has merged; if not, it builds the
minimum it needs in that module and the second of the two to merge reconciles.

**Build.**

- `show <target>`: the block or page, its ancestors, references resolved per
  [§6](DESIGN.md#resolution). One level by default, `--depth N` further. A cycle is reported
  where it is met. A dangling reference is reported as dangling. `--children` as in S6.
- `backlinks <page>`: every block that links to the page by `[[...]]`, `#tag` or `#[[...]]`,
  with ancestors.
- Fixtures: a reference chain three deep, a two-block cycle, a dangling reference, an embed.

**Done when.** Each case above produces the reported, not substituted, result in text and
JSON, and no input makes `show` fail to terminate.

**Settles.** Nothing.

**Leave alone.** Writing.

## S8 - The splice, and the in-block writes

**Goal.** A write changes only the bytes it meant to, atomically, and refuses when the file
moved. Four of the five write verbs ship on top of it.

**Needs.** [S5](#s5---identity-and-targets).

**Build.**

- `src/logseq_md/splice.py` ([§7](DESIGN.md#the-splice), [§7](DESIGN.md#concurrency)): take a
  file as read, a list of line-range replacements, and produce the new bytes. Write to a
  temporary file in the same directory, then rename over the original; on Windows use the
  replace call that overwrites. Before renaming, compare the file on disk with what was read
  and refuse with exit 3 if it differs. `--dry-run` prints a unified diff and writes nothing.
- The mutation half of the gate ([§9](DESIGN.md#the-gate)): for every block in the fixture
  graph, apply one write and assert every byte outside the spliced range is unchanged.
- New lines copy the file's line ending: the ending of the line they follow, or of the file's
  first line when there is none. A file without a final newline keeps not having one, unless
  the insertion is at the end, in which case the inserted line takes the ending and the last
  line does not gain one.
- `ensure-id <target>` ([§5](DESIGN.md#giving-a-block-an-id)): print the existing id, or insert
  a minted one as the first continuation line, indented like the block's existing property
  lines, or by the conventional rule in [§4](DESIGN.md#properties) when it has none.
- `set-property <uuid> <key> <value>`: replace the value of an existing line with that key, or
  insert one after the last existing property. Re-running converges.
- `set-content <uuid> --text ...`: replace the content span, leaving properties, drawers and
  children. Multi-line text keeps the span's continuation indent.
- `set-marker <uuid> <MARKER>`: validate against the seven markers, replace, add or (with
  `none`) remove the marker word on the content line. Never touches `:LOGBOOK:`.
- Every write refuses on a page with no outline, naming the file
  ([§6](DESIGN.md#pages-that-are-not-outlines)), and on `page:line` targets.
- At least one test drives a sequence rather than a state: `ensure-id`, edit the file as a
  person would, `ensure-id` again, assert the same id and an unchanged file.

**Done when.** The mutation gate is green on both operating systems, each verb converges on a
second run, and a write against a file modified between read and rename exits 3 with the file
untouched.

**Settles.** The first question in [§13](DESIGN.md#13-still-open), provisionally: `set-content`
ships as designed, taking a uuid and asking no questions. What settles it for good is
[§13](DESIGN.md#13-still-open)'s first real caller, not this stage.

**Leave alone.** Inserting new blocks.

## S9 - `append-child` and `--record-as`

**Goal.** A caller can write a note beneath a block, record where it put it, and update rather
than duplicate it on the next run ([§7](DESIGN.md#how-a-caller-updates-its-own-note-instead-of-adding-another)).

**Needs.** [S8](#s8---the-splice-and-the-in-block-writes).

**Build.**

- `append-child <uuid> --text ...`: insert as the last child, after the target's properties,
  drawers and existing children and before its next sibling ([§7](DESIGN.md#position)), with
  indentation copied from the file per [§7](DESIGN.md#indentation-on-insert). Multi-line
  `--text` becomes one block with wrapped content.
- `--record-as <key>`: in one splice, append the child with a minted id and write
  `<key>:: <child-id>` on the parent. On a later run, when the parent already carries the key,
  resolve the recorded block and replace its content instead. When the recorded block is gone,
  exit 4 naming the id ([§7](DESIGN.md#when-the-recorded-block-is-gone)). No default for the
  key.
- `--create` for a journal date that has no file ([§7](DESIGN.md#files-that-do-not-exist)).
  Without it, exit 1. With it, only a journal date is accepted; a page name is exit 2.
- Fixtures from [§9](DESIGN.md#what-the-fixtures-must-cover): insertion with and without a final
  newline, beside properties, a logbook, existing children and a following sibling, into
  tab-, space- and mixed-indented files.
- A sequence test: `append-child --record-as k`, run again, assert one child with updated
  content; delete the child by hand, run again, assert exit 4 and an untouched file.

**Done when.** The sequence above holds on both operating systems, and every new child's
indentation matches its siblings byte for byte in every fixture.

**Settles.** Nothing.

**Leave alone.** The other write verbs, except to share code with them.

## S10 - The skill

**Goal.** A model given a Logseq task reaches for `logseq-md` and uses it the way
[§12](DESIGN.md#12-the-skill) describes.

**Needs.** [S6](#s6---enumeration-blocks-pages-properties), [S7](#s7---resolution-show-backlinks),
[S9](#s9---append-child-and---record-as), and [S0](#s0---the-release-pipeline) for the version
file.

**Build.**

- `skills/logseq-md/SKILL.md` in the shape federated-agent-kits uses, subscribable with
  `akit`. Its description is what decides whether it is ever reached for, so it names the
  situations: a Logseq graph, journals, a block id, a task in notes.
- The practice from [§12](DESIGN.md#12-the-skill): read the ancestor chain before acting,
  journals are chronological and pages topical, the owner closes their own tasks, an answer
  names its file, ids before writes, `--dry-run` before a write a person will not review. The
  mechanics stay in `--help`; the skill points at it.
- `skills/logseq-md/VERSION`, written by `.scripts/version.py write` alongside
  `pyproject.toml`, with a test that the two agree.
- Every command example in the skill runs against the fixture graph in a test.

**Done when.** `akit` renders the skill from this repository into a harness, and a fresh
session with only the skill installed answers a question about the fixture graph by calling
`uvx logseq-md` rather than reading files.

**Settles.** The third question in [§13](DESIGN.md#13-still-open), for now: a skill and no
rule. The journal records whether it gets reached for.

**Leave alone.** `src/`, except help text the skill exposed as unclear.

## S11 - The release gate

**Goal.** What [§11](DESIGN.md#11-windows-linux-python) promises, as a stranger meets it.

**Needs.** Every stage above.

**Build.**

- A smoke job in `tests.yml`, on both operating systems, that builds this branch's wheel,
  runs it through `uvx` against a copy of the fixture graph, and exercises one read and one
  write per verb family, asserting output and exit codes. It installs this branch's wheel
  rather than the index's, because on a pull request the index holds the last release.
- The stub list from [S2](#s2---lines-the-round-trip-gate-and-the-cli-frame) is empty,
  asserted by the test written then.
- `README.md` and `CONTRIBUTING.md` describe what ships. "Pre-alpha" goes; the version stays
  `0.x`.

**Done when.** The smoke job is green on both operating systems and is added to the ruleset's
required checks, by hand, after it has reported once.

**Settles.** Nothing. `1.0` is not a step any stage performs: it waits for the month of real
use [§2](DESIGN.md#that-premise-is-a-bet) asks for, and for the first real caller to answer
[§13](DESIGN.md#13-still-open)'s first question.

**Leave alone.** Behaviour. A defect the smoke finds is fixed in the stage it belongs to, with
a fixture.
