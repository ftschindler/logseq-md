---
name: logseq-md
description: Read and write a file-based Logseq graph with `uvx logseq-md` rather than by opening its markdown. Use whenever a task touches a Logseq graph or Logseq notes - journals, pages, blocks, a block id or `((uuid))` reference, `property:: value` lines, or a TODO, DOING or DONE task kept in notes - whether to find, answer from, or add to them.
---

# Working in a Logseq graph

A Logseq file graph is a directory of markdown: `pages/` for topics, `journals/` for dates,
one block per bullet, nested by indentation. Read it and write it through `uvx logseq-md`,
never by opening or editing the files yourself. A text edit that Logseq still reads can
still reflow a page, and the owner's graph usually has no git history to undo it with.

The mechanics live in the tool. `uvx logseq-md --help` lists the verbs, and every verb's
`--help` says what it writes, gives an example and documents its `--json` shape. Read the
help of a verb before its first use; this skill does not repeat it.

## Finding the graph

Pass `--graph <dir>` to every call, or set `LOGSEQ_MD_GRAPH` once. The directory is the one
holding `pages/`, `journals/` and `logseq/config.edn`. When the user has not said where the
graph is, ask rather than search their disk for one.

## Reading

```sh
uvx logseq-md blocks --marker TODO --page "Kiln Log"
uvx logseq-md show 7a20b1c3-0000-4d5e-8f60-000000000021
uvx logseq-md backlinks "Kiln Log"
uvx logseq-md pages --json
```

- **Read the ancestor chain before acting on a block.** A block's meaning is mostly in its
  parents: "ply the singles" is a step of whatever it sits under. `blocks` and `show` print
  the ancestors; use them.
- **Journals are chronological, pages are topical.** What happened on a day is in that
  day's journal; what is known about a thing is on its page, and in the journal blocks that
  link to it, which `backlinks` finds. Look in both before saying something is not there.
- **There is no search by text.** To find a block by its words, list the page with
  `blocks --page`, or when the page is unknown, `grep -rn` the graph for the page and line
  and pass `page:line` to `show`. Grep locates; the tool reads.
- **An answer names its file.** Say which page or journal a block came from, so the owner
  can open it and check. `--json` and `--paths` give the path.

## Writing

```sh
uvx logseq-md ensure-id "Kiln Log:33"
uvx logseq-md append-child 7a20b1c3-0000-4d5e-8f60-000000000002 --text "tile 3 crazed" --dry-run
uvx logseq-md append-child 7a20b1c3-0000-4d5e-8f60-000000000002 --text "tile 3 crazed" --record-as review-note
uvx logseq-md set-property 7a20b1c3-0000-4d5e-8f60-000000000006 shelf top
```

- **Ids before writes.** Every write except `ensure-id` takes a block's uuid. A block found
  by `page:line` gets one from `ensure-id` first, and the write uses what it prints. Line
  numbers move when the owner edits; ids do not.
- **`--dry-run` before a write nobody will review.** It prints the diff and writes nothing.
  When the user is not watching the change land, look at the diff first.
- **Update your own note instead of adding another.** `append-child --record-as <key>`
  remembers the note's id on its parent and replaces that note on the next run. Pick a key
  that names what the note is for.
- **The owner closes their own tasks.** Do not change a block's marker, mark a task DONE or
  CANCELED, or reword a task, unless the user asked for exactly that. Report what you found,
  or add a child note beside the task, and leave the decision to them.

## When it refuses

A refusal is the tool protecting the file, and its message says why. Exit 1 is nothing
found, 2 is a request it will not carry out as asked, 3 is a file that changed since it was
read, 4 is a `--record-as` note that is gone, and 5 is a graph it cannot read. Re-read and
retry after a 3; narrow an ambiguous name; report a page that is not an outline to the user
rather than working around it by editing the file.
