# DESIGN - logseq-md

**Status:** first draft. Nothing is implemented beyond the package frame. This document is the
sole source of truth for the design, so change it here first.
[IMPLEMENTATION.md](IMPLEMENTATION.md) says in which order it gets built.

**Date:** 2026-10-30

## 1. What this is

A command-line tool for reading and writing a **file-based Logseq graph**: the markdown
directories Logseq 0.x keeps on disk, as opposed to the database graphs its successor uses.

It exists for one job that the dozen tools already in this space do not do. A write changes the
bytes it meant to change and no others.

### What a graph is

A directory holding `pages/`, `journals/` and some supporting folders. Every file is markdown.
Every line beginning with a bullet is a **block**, and blocks nest by indentation. A block may
carry **properties**, may reference another block by its **id**, and may link to a page by name.

That is the whole data model, and [§4](#4-the-file-format) is its definitional home.

### Who calls it

Scripts and agents working against a graph that its owner also edits by hand, in the Logseq
application, often on more than one machine. The tool is a subprocess with text output. It is
not a library first, not a server and not a plugin.

### Who it is generic for

Nobody yet. Every requirement here traces to one graph and one workflow, and the first consumer
is the author's own.

**The genericity is a discipline rather than a response to demand.** Rule 7 of
[§3](#3-rules-of-the-build), rule 8, and [§8](#8-graphs)'s refusal to search two graphs at once
all cost something, and what they buy is a tool that stays small enough to reason about whilst
the workflow around it changes. A second user would be welcome and is not what any of this was
written for. Saying so here is cheaper than letting a reader infer an audience that does not
exist.

## 2. What this does

You have a graph. Something that is not you wants to read a block, and sometimes write beside
one, whilst the application is open, or closed, or syncing to a phone.

**Everything else in this space parses a page into a tree and writes the tree back over the
file.** The result is valid: Logseq reads it. It is also wrong, in three ways that compound.

- **A one-line append arrives as a thousand-line diff.** Nobody reviews the second one, which
  means nobody reviews any of them.
- **A graph is usually not a git repository.** There is no `git checkout` for a reflowed
  journal from 2023, and the only copy of what it used to say is whatever Logseq happened to
  put in `logseq/bak`.
- **A reflow poisons every merge that comes after it.** Two devices that each changed one line
  is a mechanical three-way merge. One side that reflowed the file cannot be merged by
  anything, including a person reading both.

So the write path splices lines into the file it was handed, and the round-trip test in
[§9](#9-tests) is the acceptance criterion rather than a nicety.

### That premise is a bet

**Every harm above is predicted, not observed.** No reserialising write has yet cost anything
here, because none has been run. The argument is reasoning from how the format and the tooling
behave, and reasoning is how a project talks itself into a constraint it keeps paying for after
the reason has gone.

What would count as evidence against it: a month of real use in which no reviewed diff is made
unreadable by a reflow, no graph edit is lost in a way byte preservation would have prevented,
and no conflict arrives that a three-way merge could not resolve. Should that month pass, the
honest response is to reopen this section rather than to defend it.

Three things follow.

**The tool never normalises.** Not indentation, not property order, not blank lines, not
trailing whitespace. Where a graph is inconsistent, it stays inconsistent.

**Reading is the common case and writing is the guarded one.** Read verbs need no flags.
Write verbs name what they will touch and print a diff when asked.

**It knows Logseq and nothing else.** No task queue, no forge, no notion that one graph matters
more than another. [§3](#3-rules-of-the-build) rule 7 is how that is kept true.

## 3. Rules of the build

1. **A write changes the bytes it meant to change and no others.** Every untouched line comes
   back identical, including its line ending.
2. **Read-only by default.** A write happens because a write verb was named.
3. **A refusal is a refusal.** When the file moved underneath us, or the block is not there,
   the command fails and says which. It never writes half of what it was asked for.
4. **Re-running a write converges.** Asking twice for the same end state produces it once.
   This is what makes the tool safe to call from something that retries.
5. **The graph is the only state.** No index on disk, no cache to invalidate, no daemon.
6. **Python, on Windows and Linux equally.**
7. **The tool's vocabulary is Logseq's, and caller-supplied names are opaque.** Two halves.
   The tool's own verbs and flags use Logseq's words: blocks, markers, properties, references,
   pages, journals, ids. And a property key handed in by a caller is copied, never read: the
   tool ships no default key, branches on no key's name, and documents no key that means
   something. [§5](#why-opacity-is-the-half-that-matters) says why the second half carries the
   weight, and [§15](#15-not-doing) is what the rule has already excluded.
8. **Nothing a personal graph contains enters this repository.** Not as a fixture, not as an
   example, not in a test name. [§9](#9-tests) says what is used instead.

## 4. The file format

This section is the definitional home for everything the tool parses. Later sections name a
construct and refer back here rather than restating it.

Every claim below was read off two real graphs totalling about 3,300 files, and the counts are
from those. Where the evidence is thin, it says so.

### A block

A block is a line whose first non-whitespace is `-`, plus every line after it that is not
itself a block. Nesting is by leading tabs.

```text
- weekly review
 - decide whether the migration ships this month #planning
   id:: 69676218-6ca0-4d45-8d0f-d229c8721922
   collapsed:: true
  - the blocker is the index rebuild
```

Every example in this document is invented. Rule 8 of [§3](#3-rules-of-the-build) is why, and
the structures they show are the ones the real graphs taught us.

Observed depth runs to eight levels.

**The indent character is not reliably a tab.** Measured across 1,533 files: 997 use tabs, 555
use spaces, 628 mix the two within one file, and **492 mix both characters inside a single
indent prefix**. There is no canonical indentation to normalise towards, which is why rule 1 of
[§3](#3-rules-of-the-build) talks about bytes, and why
[§7](#indentation-on-insert) copies a file's own convention rather than applying a rule.

### What else sits under a bullet

Three constructs share the continuation position and are not the same thing. Getting them apart
is most of the parser.

**Wrapped content.** A block's text may run onto further lines. 301 files carry 2,848 such
lines. They belong to the block's content, which is why
[§7](#the-five-writes) replaces a content *span* rather than a line.

**Properties**, covered below.

**Drawers**, meaning `:LOGBOOK:` and friends, covered under task markers.

Two further hazards are not continuation lines at all. **Code fences** can contain lines that
look like bullets, properties or drawers: 51 files do. A parser that does not track fence state
reads a snippet as structure. And **74 non-empty files have no bullets whatsoever**, being
prose pages or page-property files. [§6](#pages-that-are-not-outlines) says what happens to
those.

**A block's text is frequently meaningless without its ancestors.** Two shapes seen repeatedly
in real graphs, reproduced here in invented form: `TODO I'll review and accept whichever we
pick`, and `TODO investigate the second one`. The subject lives two levels up. Any read that returns a block without the option
of its ancestors returns something a caller cannot act on, which is why
[§6](#6-reading) makes the ancestor chain a first-class output rather than a flag nobody sets.

### Properties

A property is a continuation line of the form `key:: value`. It belongs to the block above it.

**Its indentation is usually the block's own prefix followed by two spaces**, which aligns the
key under the text after the bullet. Usually rather than always: 58 property lines across 16
files deviate from it. The tool therefore recognises a property by its shape and its position,
never by a computed indent, and writes a new one by copying the prefix convention it found.

Keys seen in the wild, with counts from one graph, because the useful distinction is not
alphabetical:

| Key | Count | What it is |
| --- | --- | --- |
| `id::` | 102 | the block's identity ([§5](#5-identity)) |
| `collapsed::` | many | fold state in the application |
| `hl-page::`, `hl-color::`, `hl-stamp::` | 69, 69, 7 | a PDF highlight's location |
| `file::`, `file-path::` | 50, 50 | the asset a block was extracted from |
| `ls-type::` | 63 | what kind of extracted thing it is |
| `excalidraw-plugin::` | 22 | a drawing |

**That table is the reason property stripping is a policy rather than a switch.** `collapsed::`
is noise in every output. `hl-page::` and `file-path::` are the trail back to page 12 of the
PDF a note came from, which is the most valuable thing on the block.

### Task markers and scheduling

A block whose text starts with a marker word is a task. Observed across two graphs: `TODO`
(497), `DONE` (1025), `WAITING` (103), `DOING` (23), `LATER` (2). `NOW` and `CANCELED` exist in
Logseq and do not appear here.

Three further constructs attach to tasks and are **not** properties, despite sitting in the same
continuation position:

```text
- DONE write up the decision
  DEADLINE: <2023-09-04 Mon>
  :LOGBOOK:
  CLOCK: [2023-10-17 Tue 13:12:37]--[2023-10-17 Tue 14:16:03] =>  00:52:45
  :END:
```

`:LOGBOOK:` is a multi-line block holding clock records. The tool reads it and
[§7](#7-writing) says why it never writes one.

### Order of the continuation lines

Logseq writes `id::` first, immediately after the content: `id::` then `collapsed::`, `id::`
then `DEADLINE:`, `DEADLINE:` then `:LOGBOOK:`. There is at least one file where `DEADLINE:`
precedes `id::`, so the order is a convention rather than a rule.

**That question is closed by not answering it.** The tool inserts `id::` immediately after the
content, which is where Logseq puts it, and never moves a line it did not write. A canonical
order is not needed, because nothing is ever reordered.

### References and links

| Written | Means | Resolution |
| --- | --- | --- |
| `[[Page Name]]` | a link to a page | a filename, see below |
| `#tag` | the same thing, shorter | the same |
| `((uuid))` | a reference to one block | the block carrying that `id::` |
| `{{embed ((uuid))}}` | the same block, rendered inline | the same |

Block references resolve from the markdown alone, and completely. Of 228 distinct `((uuid))`
references in one graph, 228 resolve to an `id::` in the same graph and none dangles. There is
no index, no hash and no application involved: the `id::` is simply written into the target
file at the moment the reference is first made.

### Pages, journals and namespaces

A page's filename is its title with `/` replaced, per `logseq/config.edn`:

```text
:file/name-format :triple-lowbar
```

So `[[Cooking/Bread Starter]]` is `pages/Cooking___Bread Starter.md`. Spaces stay spaces;
the characters some filesystem refuses (`: * ? " < > | # \`) are percent-encoded, and so is an
underscore that would make the separator ambiguous. A config without the key is an older
graph, whose filenames use the legacy format: `%2F` for the slash, and a `.` read back as one.
**The tool reads the graph's own `config.edn` for this** rather than assuming the current
default, because the setting has changed across Logseq versions and a graph carries the one it
was written under.

EDN is Clojure's data format and Python has no reader for it in the standard library. Rather
than take a dependency, the tool reads the two or three keys it needs with a narrow reader,
documented in the source as not a general EDN parser and not to be extended into one. A graph
whose config cannot be read that way falls back to the current default and says so.

That is a deliberate trade. The alternative puts a parsing library into a project whose central
claim is that no library gets to reformat a file, and
[§11](#11-windows-linux-python) is why the dependency list stays empty.

Journals are `journals/YYYY_MM_DD.md`, titled like `Feb 28th, 2025`, with both formats in the
same file as `:journal/file-name-format` and `:journal/page-title-format`.

### What the tool does not read

`logseq/bak` holds 608 files in one graph, which are previous versions of pages the application
replaced. `assets/`, `draws/` and `whiteboards/` are not outline markdown. All four are skipped
by default, and `bak` in particular would otherwise double every search result.

## 5. Identity

A block's identity is a UUID in an `id::` property. This section owns how one is made.

### Logseq's UUIDs are not random

They are DataScript **squuids**: the first eight hex characters are the creation time in Unix
seconds, the version nibble is forced to 4, the rest is random. The effect is a UUID that sorts
by age.

Logseq 0.10.15 reaches one through `get-custom-id-or-new-id`, which returns an explicit `id` or
`custom-id` property when the block has one and otherwise calls `d/squuid`:

- [`deps/graph-parser/src/logseq/graph_parser/block.cljs#L581-L589`](https://github.com/logseq/logseq/blob/0.10.15/deps/graph-parser/src/logseq/graph_parser/block.cljs#L581-L589)
- [DataScript's implementation](https://github.com/tonsky/datascript/blob/8c01d1b7e401ab1765f2933164267922f550d753/src/datascript/util.cljc#L128-L161)

Checked across 970 sampled ids from both graphs: **every one decodes to a plausible Unix-seconds
prefix with a version nibble of 4**, which is the squuid shape and not a coincidence available
to `uuid4`.

**The prefix is the id's creation time, not the block's date.** Of 564 ids living in journals,
365 decode to their journal's own date and 199 do not, an exact match rate of 64.7%. That is
expected rather than a discrepancy: a block gets its id the first time something references it,
which is often months after it was written. Seven ids decode more than five years away from
their journal and came from Excalidraw or other embedded material rather than from Logseq.

Nothing in the tool relies on the prefix meaning anything. It is reproduced because that is what
Logseq writes, and a `uuid4` in its place would be accepted everywhere, pass every test, and
quietly destroy the only ordering signal the format carries.

### Giving a block an id

`logseq-md ensure-id` takes a block that may or may not have one and guarantees it does:

- A block that already has an `id::` keeps it, and the command prints it. This is rule 4 of
  [§3](#3-rules-of-the-build), and it is the difference between a safe retry and two
  identities for one block.
- A block without one gets a freshly minted squuid, written as the first continuation line.

That is the whole of minting. `ensure-id` is the only verb that creates a UUID, which is why it
stays a named verb rather than folding into
[`set-property`](#the-five-writes): every other write takes an id it was given.

### Why a caller needs this

Anything that writes beside a block and then wants to find its own writing again needs a
durable address. A file and a line number is not one: the file is edited by a person between
runs. The id is the address Logseq itself uses, it is already how the application tracks a
block across edits, and putting one on a block is a thing Logseq does routinely.

### Why opacity is the half that matters

Rule 7 of [§3](#3-rules-of-the-build) has two halves, and the second is the one that does the
work. This is its definitional home.

A caller records where it put something by writing a property whose key it chooses:

```sh
logseq-md append-child 69676218-6ca0-4d45-8d0f-d229c8721922 \
    --text "checked, pin updated" --record-as review-note
```

The tool writes `review-note:: <new-id>` on the parent. It never read the words. It copied a
string it was handed, and the workflow stayed in the caller.

**The failure this guards against arrives in three steps, each of which looks reasonable.**
First `--record-as` gains a default, because typing it every time is tedious. Then
`blocks --unclaimed` appears, meaning "has no such property". Then `blocks --stale --since 7d`
appears, reading the recorded block's age.

Each step is defensible on its own and the three together are somebody's workflow compiled into
a generic tool. At step one, two unrelated callers share a key and silently overwrite each
other's pointers. At step two, "unclaimed" is not a Logseq word and the tool now holds that a
property means ownership. At step three the next person's workflow no longer fits.

**The test is mechanical.** Grep the source for a hardcoded property name. Only `id` and
`collapsed` may appear, those being Logseq's own. Anything else is the rule being broken, and it
is checkable by somebody who has not read this section.

## 6. Reading

### What a read returns

The matched block, its ancestors, and its references resolved. **Ancestors are not optional**,
for the reason in [§4](#a-block): without them the text frequently has no subject.

Children arrive on request rather than by default. They are often the real content and often
large, and an enumeration that returned every subtree would return most of the graph.

Three output shapes, because the callers differ:

| Shape | For | Flag |
| --- | --- | --- |
| text | a person, and an agent reading a terminal | default |
| JSON | a script | `--json` |
| paths | piping into something else | `--paths` |

**Whilst the version begins with a zero, none of them is a promise.** From 1.0, `--json` is the
contract and the text output is not: a caller parsing prose has no grounds to complain when a
message is reworded, and a JSON field that is renamed is a major version under the release
rules.

### Resolution

Reading resolves what it can from the graph alone:

- `((uuid))` becomes the referenced block's text, inline, marked as a reference.
- `{{embed ((uuid))}}` resolves the same way.
- `[[Page]]` becomes a path, through the graph's own `:file/name-format`.
- A journal filename becomes a date, and a date becomes a filename.

**One level deep by default.** A referenced block may itself hold references, and nothing in the
format prevents a cycle: A referencing B whilst B references A. `--depth` goes further and a
cycle is reported where it is met rather than followed, so no read can fail to terminate.

Resolution is reported, never silently substituted. A reference that does not resolve is said
to be dangling rather than dropped, because a dangling reference in a synced graph usually means
the other device has the block.

A `[[Page]]` whose path holds no file is dangling too, and its path is still given: Logseq
creates a page on its first link, so a caller may want to write there. An id two blocks carry
is reported as ambiguous with both, as a target would be ([§10](#targets)).

Showing a page shows its top-level blocks, and its whole outline with `--children`, the same
rule as for a block. Backlinks answer for a page that only exists as a link, and refuse with
exit 1 a name that no file holds and nothing links to, so a typo is not read as a page nobody
links to.

### Properties in output

`collapsed::` and the Excalidraw keys are dropped. `hl-page::`, `file-path::` and the rest of
the extraction trail are kept. `id::` is kept.

Two flags, because one was too coarse. `--raw` keeps everything, for a caller that wants the
literal block. `--keep <key>` rescues one key from the drop list, for a caller that wants the
fold state and nothing else it implies.

The list of what is dropped lives in one place in the code and is printed by
`logseq-md properties`, so that a person can see the policy rather than infer it.

### Pages that are not outlines

74 non-empty files in the measured corpus have no bullets at all: prose pages, and files holding
only page-level properties.

**They are read and they are not written.** Enumeration returns them as a page with no blocks,
so a caller searching the graph still finds their text. Every block-level write refuses, naming
the file and saying it has no outline.

Treating such a file as one implicit block would make it writable, and would put a bullet into a
page somebody deliberately kept as prose. Skipping them entirely would make 74 real pages
invisible to every caller. Reading without writing is the only option that neither hides them
nor rewrites them.

### Searching

Searching is enumeration with filters, not a query language. Filters compose: a marker, a tag,
a property's presence by `--has-property <key>`, a date range, a page. **Every one of them is a
Logseq concept**, which is
rule 7 of [§3](#3-rules-of-the-build) doing its job: the filter set is sufficient for a caller
that wants "every unfinished task I tagged this way that I have not already annotated", and the
tool never learns what that caller means by it.

`--has-property` is what makes a caller resumable across runs, and the caller names the key
every time. There is no default and no way to ask for a key by any other means, which keeps the
tool opaque to what the key signifies
([§5](#why-opacity-is-the-half-that-matters)).

## 7. Writing

### The splice

A write locates the lines it will change, builds the replacement lines, and writes the file with
every other byte as it found it. It does not build a document and serialise it.

The consequence worth stating plainly: **the tool cannot fix a malformed file, and will not
try.** A graph with inconsistent indentation keeps it. This is a feature of rule 1 in
[§3](#3-rules-of-the-build) rather than a limitation of the parser.

### The five writes

| Verb | Changes |
| --- | --- |
| `ensure-id` | adds one `id::` line, or nothing ([§5](#giving-a-block-an-id)) |
| `set-property` | sets one `key:: value` line on a block, key chosen by the caller |
| `append-child` | inserts one or more lines as the last child of a block |
| `set-content` | replaces one block's content span, leaving its properties and children |
| `set-marker` | replaces the marker word on one block's content line |

A block's content is a **span**, not a line: 301 files in the measured corpus carry wrapped
text. `set-content` replaces from the bullet line to the last line before the first property,
drawer or child, which is the only reading under which the verb means the same thing on every
block.

`set-marker` is the one verb that validates its argument, against Logseq's seven markers: TODO,
DOING, DONE, LATER, NOW, WAITING, CANCELED. That is not the tool holding an opinion. Markers are
a closed set in Logseq, unlike property keys, and an unrecognised one produces a block the
application renders as ordinary prose rather than as a task.

### How a caller updates its own note instead of adding another

A caller that writes a progress note, runs again an hour later and writes a second one has
produced a block with two notes and no way to tell which is current. **Every existing tool in
this space has this failure, because all of them append.**

Avoiding it needs the caller to find its own earlier note, which needs somewhere to keep the
id. That place is the graph, because rule 5 of [§3](#3-rules-of-the-build) says so and because
a state file beside the caller is one more thing to lose:

```sh
logseq-md append-child <task-id> --text "..." --record-as review-note
```

`--record-as` does two things in **one atomic file write**: it appends the child, and it writes
that child's id as `review-note:: <child-id>` on the parent. Both land or neither does, so an
interrupted run cannot leave an orphan.

On the next run the same command finds the property, resolves the recorded block and replaces
its content rather than appending. **The verb converges**, which is rule 4 holding rather than
being weakened, and the caller needs no memory of its own.

The key is the caller's word. The tool copies it and never reads it, which is the opacity half
of rule 7 ([§5](#why-opacity-is-the-half-that-matters)).

Finding which blocks already carry such a note is `blocks --has-property review-note`
([§6](#searching)). The caller names the key every time.

### When the recorded block is gone

The graph's owner deletes the note in Logseq, or the file arrives from a phone without it. The
property now names a block that is not there.

**The command refuses, with an exit code naming the missing id.** It does not re-create the
block, which would resurrect something somebody deliberately deleted, and it does not append a
fresh one, which is the duplicate-accumulation failure arriving slowly enough that nobody
connects the two.

Clearing the property is how an owner tells a caller to start again. That makes a deletion a
signal rather than an accident, and it costs the caller one case to handle.

### Position

`append-child` inserts after the target's existing children and before the next sibling. Where
the target has properties and a `:LOGBOOK:`, the insertion goes after all of them, because those
belong to the target rather than to its children. Blank lines belong to the block above them,
so the insertion goes after those too.

The target can also be a page or a journal date, and the new block is then the page's last
top-level block. A page holding only blank lines takes its first block; a page with prose and
no outline is refused, like every write. `--record-as` needs a block to record on, so with a
page target it is exit 2.

### Indentation on insert

**The new line copies the file's own convention rather than applying a rule.** The tool reads
the target's prefix, reads an existing child's prefix where there is one, and extends using the
characters that file already uses at that depth.

A rule would be simpler and wrong. 492 files mix tabs and spaces inside a single indent prefix,
so "the target's indent plus one tab" writes a child whose indentation does not match its
siblings in roughly a third of a real graph. Logseq may still read it; a person reading the diff
will not.

Where the target has no children, the evidence at that depth is the child prefix most common
under the file's other blocks with the target's own prefix. Where the file gives none, the tool
extends with whatever the target's own prefix ends in: a tab, or its trailing run of spaces. A
top-level target with no evidence takes a tab, as Logseq does. A new top-level block copies the
page's last one.

### Files that do not exist

Every write edits a file that is already there, with one exception. Logseq creates today's
journal when the application is opened, so on a day it has not been opened the file is absent.

`--create` is how a caller says to make it. Without the flag the command refuses, so a mistyped
date cannot quietly add a page to somebody's graph. With the flag, only a date is accepted; a page
name is exit 2. The new file is written atomically and refused with exit 3 if one appeared in the
meantime, and like most of a real graph it has no final newline.

### What a write never does

- **It never writes a `:LOGBOOK:` or a `CLOCK:` line.** Those are the application's record of
  time actually spent. Synthesising one puts a false entry in somebody's time tracking, and the
  format gives no way to mark an entry as invented.
- **It never decides to close a task.** `set-marker DONE` does what it says, because a person
  running it means it. The advice that a caller should leave that judgement to the graph's
  owner lives in the skill ([§12](#12-the-skill)), which is where policy belongs.
- **It never reorders or reformats.** See [§4](#order-of-the-continuation-lines).

### Concurrency

Two writers are assumed: the person, through the Logseq application, which watches the
filesystem and re-reads a file it sees change.

- **The file is written atomically**, to a temporary file in the same directory and then
  renamed. The application's watcher never observes a half-written file.
- **A write refuses if the file changed since it was read.** Just before the rename, the file
  is read again and compared byte for byte with what the write started from. Graph files are
  small, so this costs little, and unlike a size and modification time it cannot be fooled by a
  coarse clock or a sync tool restoring a timestamp. The remedy is to read again, which the
  caller can do without help.

That is the whole concurrency story, and it is deliberately small. A graph that syncs between
devices has a third writer this tool cannot see, and [§15](#15-not-doing) is why that stays
somebody else's problem.

### The diff

`--dry-run` prints what would change, as a unified diff, and writes nothing. Because the write
is a splice, that diff is as short as the change, which is the property that makes a human
review of an automated write possible at all.

## 8. Graphs

A graph is a path. It arrives as `--graph PATH`, or from `LOGSEQ_MD_GRAPH`, and nothing is
inferred from the shape of the filesystem.

**One graph per invocation, and no flag changes that.** A person with a personal graph and a
work graph has a boundary between them that this tool cannot see and must not cross. A command
that searched both would eventually surface the wrong one into the wrong context, and the cost
of that is not symmetrical with the convenience of not typing the flag twice.

Named graphs, a registry, a config file: [§15](#15-not-doing).

## 9. Tests

### The gate

**Parse every fixture file, write it back with no modification, and assert the bytes are
identical.** Then do it again with one real mutation, and assert that every byte outside the
spliced region is unchanged.

That is the acceptance criterion for this project. It is also, as far as the survey in
[§14](#14-what-else-exists) found, the criterion no existing tool meets.

**It is achievable.** A model retaining each source line's indentation, content and line-ending
bytes round-tripped **1,533 of 1,533 files** across two real graphs, with no exemptions. The
gate is therefore a bar this design can clear rather than an aspiration, which matters because
the usual way a project loses its differentiator is a late gate failure met by weakening the
gate.

What that result does not show is that an abstract syntax tree can be serialised back to the
same bytes. It shows the opposite is unnecessary: structure can be added alongside the source
representation rather than in place of it.

### The corpus problem

The best corpus is a real graph: thousands of files, Excalidraw pages, PDF highlight blocks,
eight-level nesting, a decade of inconsistency. It is also somebody's private notes, full of
colleagues' names, client references and internal URLs, and rule 8 of
[§3](#3-rules-of-the-build) keeps all of it out of this repository.

**No test ever runs against a real graph.** A test that writes, run against somebody's notes,
is one bug away from damaging them, and a test that only reads is one refactor away from
writing. Tests see fixtures and nothing else, on every machine.

A real graph is read by scripts instead, and only to decide which fixtures to write:

| | Fixtures in the repository | A real graph |
| --- | --- | --- |
| Content | synthetic, small, one directory per topic | whatever is actually there |
| Read by | the test suite, on every CI run | scripts in `.scripts/`, on a maintainer's machine |
| Opened | for reading and writing, in a temporary copy | for reading only |
| Finds | regressions, on every platform | the constructs nobody thought of |

The survey script reports what a graph contains as counts and shapes, never as text, and
round-trips each file through the line model in memory. A construct it finds is handled once a
fixture reproducing it lands, and not before.

The fixtures are not a lesser version of the real thing. They are the record of what a real
graph taught us, written down so that it keeps being checked on every platform and after the
graph is no longer reachable.

### Proving a fixture leaked nothing

A fixture is written by somebody who has just read a private graph, which is how a real line
ends up in one. A read-only leak check compares every fixture line with the graph and fails on
any match that is more than structure.

It cannot run in CI, which has no graph. So it records evidence instead: one file per fixture
directory, holding the hashes of that directory's fixtures and of the check itself, the outcome
and a count of graph files scanned. It holds no path and no name from the graph. CI verifies
offline that the evidence still describes the committed fixtures, so a fixture changed after
its check is a red build rather than an oversight.

That catches a copied line and not a paraphrase. Reading the fixture diff stays a reviewer's
job.

### What the fixtures must cover

Established by running the gate against copies of two real graphs. The list is the experiment's
output rather than a guess, and the first two entries are the ones that would otherwise have
been missed:

- **A file with no trailing newline.** 1,328 of 1,533 files have none. A writer that helpfully
  adds one fails byte equality on 87% of a real graph.
- **An indent prefix mixing tabs and spaces.** 492 files have one.
- Empty files, and files holding only blank lines.
- Eight levels of nesting.
- Tab-only, space-only and mixed indentation across whole files.
- Property lines at the conventional indent and at the deviant one.
- Properties in non-canonical order, since the order is convention rather than rule.
- Wrapped block content, before and after properties.
- `DEADLINE:`, `SCHEDULED:`, and a `:LOGBOOK:` with several `CLOCK:` entries.
- Code fences, both backtick and tilde, containing lines that look like bullets, properties and
  drawers.
- Prose-only, metadata-only and page-property-only files.
- A namespaced filename with triple underscores.
- `((uuid))` and `{{embed ((uuid))}}`, including one that dangles and one pair that cycles.
- Child insertion into files with and without a final newline, and beside properties, drawers,
  existing children and a following sibling.
- An existing `id::` and a newly inserted one.
- A squuid minted at a fixed timestamp, asserting both the prefix and the version nibble.

Neither graph contains CRLF line endings, mixed line endings, non-UTF-8 bytes or YAML front
matter. All four still get fixtures, because a graph edited on Windows or by another tool will
have them and no real corpus here would catch it.

`.gitattributes` marks `tests/fixtures/**` as `-text`, so a Windows checkout does not rewrite
the line endings of files whose line endings are the thing under test. The repository's own
`end-of-file-fixer` hook excludes the same path, for the same reason.

### Platforms

Linux and Windows, both in CI, at both ends of the supported Python range. A tool whose entire
job is byte-exact file handling is one where a platform difference is a correctness bug rather
than an inconvenience.

## 10. Commands

Read verbs first, because they are the common case.

```sh
logseq-md blocks    --graph PATH [filters]   # enumerate, with ancestors
logseq-md show      --graph PATH <target>    # one block or page, resolved
logseq-md backlinks --graph PATH <page>      # what points here
logseq-md pages     --graph PATH             # what exists
logseq-md properties                         # the strip policy, printed
```

Read filters: `--marker`, `--tag`, `--has-property <key>`, `--since` / `--until`, `--page`.
Read options: `--children`, `--depth N`, `--raw`, `--keep <key>`, `--json`, `--paths`.

Write verbs, each taking `--dry-run`:

```sh
logseq-md ensure-id     --graph PATH <target>
logseq-md set-property  --graph PATH <uuid> <key> <value>
logseq-md append-child  --graph PATH <target> --text ... [--record-as <key>] [--create]
logseq-md set-content   --graph PATH <uuid> --text ...
logseq-md set-marker    --graph PATH <uuid> <MARKER>
```

### Targets

A `<target>` is a uuid, a page, a date for a journal, or a `page:line`. One resolver handles all
four.

**`page:line` is accepted for reads only.** A line number is invalidated by the owner editing
the page between two runs, which is the race ids exist to remove. It is convenient for a first
look at an unfamiliar graph and that is the whole of its value. Every write verb refuses it and
names `ensure-id` as the way to get a handle that lasts. `ensure-id` itself is the one exception:
a block with no id has no other address, and the verb prints the id that every later write uses.

**How each form is written.** A uuid is compared without regard to case. A date is
`YYYY-MM-DD`, and a journal's title as the config renders it, such as `Feb 28th, 2025`, is a
page name like any other. In `page:line` the line counts from 1. A line inside a block's bullet,
properties or drawer names that block, and a line before the first bullet names the page. A
colon is legal in a page title, so the text is only read as `page:line` when the part before
the last colon is an existing page.

**An ambiguous target is refused, never guessed.** Two files can decode to one page name, and
a block copied by hand outside Logseq carries its id twice. Either is exit 2, listing every
file or `file:line` that matched, because answering from one of them would answer from a page
the caller may not mean.

### Exit codes

A code per refusal, so a caller branches on what happened rather than on English that is free to
be reworded.

| Code | Means | What a caller does |
| --- | --- | --- |
| 0 | did it | carry on |
| 1 | the block or page is not there | report, or create it |
| 2 | the arguments were wrong | fix the call |
| 3 | the file changed since it was read | read again and retry |
| 4 | a recorded block is gone ([§7](#when-the-recorded-block-is-gone)) | decide, do not assume |
| 5 | the file is not valid UTF-8, or the graph is not one | stop |

## 11. Windows, Linux, Python

Python, because the machine this is written on runs it everywhere, because the one library
worth evaluating is Python ([§14](#14-what-else-exists)), and because 3,300 files is not enough
work to justify anything faster.

It ships on PyPI as `logseq-md`, and the command inside is also `logseq-md`, so:

```sh
uvx logseq-md --help
```

needs no install beyond uv and no `--from`. The names match deliberately, and a guard in
`.scripts/check_uvx_invocation.py` keeps the longer spelling out of the documentation, so that
a reader meets one form rather than two.

The runtime dependency list is empty and the bar for adding to it is high. The write path's
whole value is that it does not hand a file to a serialiser, and a markdown library is the most
likely way for one to arrive.

## 12. The skill

The tool is a command. A model reaching for it correctly is a separate artefact: a **skill**,
shipped from this repository and subscribed to with
[`akit`](https://github.com/ftschindler/federated-agent-kits).

The split follows what the two things actually carry. The tool knows the format. The skill
knows the practice: that journals are chronological and pages are topical, that an ancestor
chain is worth reading before acting on a block, that a graph's owner closes their own tasks,
and that an answer naming no file cannot be checked.

Whether the kit is one skill or a skill and a rule is [§13](#13-still-open). A skill nothing
reaches for is one that quietly never runs, which is the lesson `fkb` already paid for.

## 13. Still open

None of these blocks the first piece of work.

**Does `set-content` belong in the tool at all?** It is the verb a caller uses to update a note
it wrote earlier, and recognising "a block I wrote" is the first place a caller's workflow
could leak into the tool. The current answer keeps the leak out by making the verb take a uuid
and ask no questions: the caller remembers its own id. Whether that is enough in practice is a
thing to learn from the first real caller. It ships that way for now, replacing the bullet line and
its wrapped lines, marker included, and refusing text that would read as structure.

**How long does the file format have?** Logseq's own CLI targets database graphs, and the
official tooling has moved. This changes nothing about a graph already on disk, and it does
mean the format this parses is one nobody upstream is adding to. That is arguably the case for
building this rather than against it, and it is worth knowing rather than discovering.

**One skill, or a skill and a rule?** Nothing makes a model reach for a skill except its
description, and a lookup tool has the same discovery problem `fkb` has. A rule costs tokens on
every single turn. Write the skill, see whether it gets reached for, and add the rule only if it
does not.

**Does anything want more than one graph at once?** [§8](#8-graphs) refuses on purpose. If a
real caller turns out to want both, the answer is two invocations and the caller merging them,
which keeps the refusal and costs a loop.

## 14. What else exists

Around thirty tools, surveyed in October 2026. They divide cleanly, and the division is the
argument for this one.

**Through the application's HTTP API**: [`ergut/mcp-logseq`](https://github.com/ergut/mcp-logseq),
[`joelhooks/logseq-mcp-tools`](https://github.com/joelhooks/logseq-mcp-tools),
[`dailydaniel/logseq-mcp`](https://github.com/dailydaniel/logseq-mcp),
[`muellerei/logseq-cli`](https://github.com/muellerei/logseq-cli). Good block operations,
including nested insertion. All of them require Logseq to be running with its API server
enabled, which is not a state an unattended caller can assume.

**Against the files, by reserialising**: [`varunity/mcp-logseq`](https://github.com/varunity/mcp-logseq),
[`dearcloud09/logseq-mcp`](https://github.com/dearcloud09/logseq-mcp), and every parsing library
found, including [`LogseqMarkdownParser`](https://github.com/thiswillbeyourgithub/LogseqMarkdownParser),
which documents that it converts leading spaces to tabs. `varunity` is the instructive one: it
mints UUIDs and appends a child under a specific block, then writes by serialising the page's
whole tree. Three requirements met and the one that makes them safe missed.

**Measured against the gate**: [`logseq-matryca-parser`](https://github.com/MarcoPorcellato/logseq-matryca-parser)
was the one candidate worth depending on, and it was tested rather than argued about.

It parsed all 1,533 files without error, so it is a capable reader. Against the gate it is not
close. Re-serialising a 200-file sample came back byte-identical 20 times, a **10% pass rate**,
because its serializer canonicalises nesting, properties and line endings and always appends a
final newline. Its `append_child_to_node` preserved unrelated bytes in **18 of 40 trials**, for
the same reason. It cannot write an `id::` at all. It is Apache-2.0 and brings pydantic, rich
and typer, against a dependency list that is empty by design
([§11](#11-windows-linux-python)).

**So the parser and the writer are built here.** The measurements are recorded rather than the
conclusion alone, because a future reason to revisit this should start from them.

**Not applicable**: [`@logseq/cli`](https://github.com/logseq/logseq/tree/master/cli) is the
official tool for database graphs, and [`cldwalker/logseq-query`](https://github.com/cldwalker/logseq-query)
reads the local transit data and has not been touched since 2023.

Nothing found models a durable, updatable annotation beside a block, which is
[§7](#the-five-writes).

## 15. Not doing

**An MCP server.** It buys structured tool schemas and costs a process. The tool is a
subprocess with text output, which every harness can already call, and a caller that wants MCP
can wrap a command more easily than this repository can carry a server.

**Anything through Logseq's HTTP API.** It requires the application to be running, which the
callers this is for cannot assume, and it has no fallback when it is not. See
[§14](#14-what-else-exists) for who went that way.

**Resolving sync conflicts.** A graph that syncs between devices gets conflicts, and a daemon
that merges them is a different shape of program: continuous and reactive, where this is
invoked and transactional. Keeping them apart is also why rule 1 of
[§3](#3-rules-of-the-build) matters more rather than less. A byte-preserving writer leaves
conflicts that a three-way merge can resolve; a reserialising one leaves conflicts nothing can.

**A task queue's policy.** The verbs in [§10](#10-commands) are deliberately sufficient for one:
a caller can enumerate tasks by marker and tag, give one an id, write a note underneath it,
record where it put that note, and update it on the next run. Denying that would be a dodge,
because the verb set was shaped by exactly that use.

What the tool does not do is decide anything. Four judgements stay with the caller, and none of
them has a flag:

- **Which blocks are eligible.** The tool filters on Logseq's own attributes and has no notion
  of a task being ready, claimed or relevant.
- **What an annotation means.** It writes text it was handed.
- **When something is finished.** `set-marker` does what it is told and proposes nothing.
- **What a property key signifies.** Keys are copied, never read
  ([§5](#why-opacity-is-the-half-that-matters)).

The boundary is checkable: a feature request fails it when the tool would have to know what the
caller is doing in order to implement it.

**Any integration with a forge.** The work a caller does between reading a block and writing
beside it is that caller's business. A tool that knew about pull requests would be a workflow
with a parser attached.

**A registry of named graphs.** `--graph PATH` and an environment variable cover it. A registry
is a second place for the truth about where a graph is, and the first thing it would need is a
rule about which graph is the default, which is the refusal in [§8](#8-graphs) undone.

**Knowing that one graph is more private than another.** It is true, it matters, and it is not
expressible in Logseq's vocabulary. It belongs to the caller.

**A general markdown parser.** Nothing here needs to understand emphasis, tables or links as
syntax. It needs bullets, indentation, continuation lines and four bracket forms. A markdown
AST would be more code, more dependency and a standing invitation to serialise.

**Supporting database graphs.** A different storage model with official tooling that already
addresses it. The name says which one this is.

**Writing into `logseq/bak`.** It is the application's own record of what a file used to say,
which makes it the closest thing a graph has to an undo. Nothing here touches it.

## 16. The name

`logseq-md` says the two things that need saying: it is for Logseq, and it is for the markdown
graphs rather than the database ones. That distinction did not need making before the format
split, and now it is the first question a reader has.

The distribution and the command share a name, which is what makes `uvx logseq-md` the whole
invocation. The sibling repository `federated-agent-kits` splits them, and that was forced
rather than chosen: the command there is `akit`, and `akit` on PyPI is somebody else's project,
so naming only the command reaches a stranger's code. Here no such project exists, so the
names match and the guard that enforces it runs the other way round.
