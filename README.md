# logseq-md

Read and write file-based Logseq markdown graphs from the command line.

A Logseq file graph is a directory of markdown: `pages/` for topics, `journals/` for dates, one
block per bullet, nested by indentation, with `property:: value` lines, `[[page]]` links and
`((uuid))` block references. Ordinary tools read it well enough. Writing back into it is where
they go wrong.

```sh
uvx logseq-md --help
```

That needs no install beyond [uv](https://docs.astral.sh/uv/).

Five reads and five writes ship. `blocks` lists blocks by marker, tag, property, date and page,
each with its ancestors; `show` prints one block or page with its references resolved;
`backlinks` lists what links to a page; `pages` lists every page and journal; `properties`
prints which keys read output drops. The writes, `ensure-id`, `set-property`, `append-child`,
`set-content` and `set-marker`, splice the lines they change into the file, write it atomically,
refuse with exit 3 if the file changed since it was read, and print a unified diff instead with
`--dry-run`. `append-child --record-as <key>` records the new block's id on its parent and
updates that block rather than adding another on the next run. The version stays `0.x` until
the tool has seen a month of real use.

Underneath, a file is held as lines that write back to the identical bytes, which the round-trip
gate checks over every fixture on Linux and Windows, and the mutation gate checks that a write
changes no byte outside its own lines. A graph is opened from `--graph` or `LOGSEQ_MD_GRAPH`, and
its `logseq/config.edn` is read for the filename and journal formats. Ids are minted the way
Logseq mints them, with the creation time in the first eight hex digits.

## The skill

`skills/logseq-md/` teaches a model to reach for this tool and to use it with care: read a
block's ancestors before acting on it, name the file an answer came from, give a block an id
before writing beside it, and leave closing tasks to the graph's owner. Subscribe to it with
[`akit`](https://github.com/ftschindler/federated-agent-kits):

```sh
akit add ftschindler/logseq-md logseq-md
```

## What this is for

Agents and scripts that work against a graph the owner also edits by hand, in the app, on more
than one machine.

The constraint that shapes everything here: **a write changes the bytes it meant to change and
no others.** Every library in this space parses a page into a tree and serialises the tree back
over the file, which is correct in the sense that Logseq still reads it, and wrong in three
ways that matter.

- A one-line status append arrives as a thousand-line diff, so nobody reviews it.
- A graph is usually not a git repository, so a reflow is damage with no way back.
- A graph that syncs between devices gets conflicts, and a conflict between two files that each
  changed one line is a mechanical merge, while a conflict where one side reflowed everything
  cannot be merged by anything, including a person.

So the write path here splices lines into the file it was given. The round-trip test is the
acceptance criterion rather than a nicety: parse every file in a graph, write it back unchanged,
and assert the bytes are identical.

## What it will not do

It knows about blocks, markers, properties, references, pages, journals and ids. It knows
nothing about what you use them for. There is no notion of a task queue, no integration with any
forge, no opinion about which of your graphs is private, and no daemon resolving sync conflicts.

The test of that boundary: every verb and flag is expressible in Logseq's own vocabulary. A flag
that needs a word Logseq does not have belongs in whatever is calling this, not here.

## Development

```sh
make bootstrap   # install the pre-commit hooks into this clone
make test        # run the suite
make check       # run the full guard suite over every file
```

[CONTRIBUTING.md](CONTRIBUTING.md) has the system requirements.

## Licence

[MIT](LICENSE).
