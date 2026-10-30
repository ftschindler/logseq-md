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

**Pre-alpha.** The packaging, the entry point and the guard suite are in place. Nothing reads a
graph yet.

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
