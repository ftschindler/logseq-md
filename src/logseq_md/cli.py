"""The command line entry point.

Every verb in DESIGN.md section 10 is registered here with its arguments, and
dispatched through `HANDLERS`. A stage that implements a verb replaces its entry
in that table and touches nothing else in the frame, which is what lets stages
run in parallel without colliding in this file.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable, Sequence

from logseq_md import __version__, enumeration, identity, output, policy, resolution, targets, writes
from logseq_md.exits import BAD_ARGUMENTS, OK, RECORD_GONE, Refusal
from logseq_md.graph import open_graph

Handler = Callable[[argparse.Namespace], int]

_READ_ONLY = "Reads the graph and never writes to it."


def _graph(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--graph", metavar="PATH", help="the graph directory (default: $LOGSEQ_MD_GRAPH)")


def _read_output(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--children", action="store_true", help="include each block's subtree")
    parser.add_argument("--raw", action="store_true", help="keep every property, ignoring the drop list")
    parser.add_argument("--keep", metavar="KEY", action="append", help="keep one dropped property key (repeatable)")
    _shape(parser)


def _shape(parser: argparse.ArgumentParser) -> None:
    shape = parser.add_mutually_exclusive_group()
    shape.add_argument("--json", action="store_true", help="print JSON, for scripts")
    shape.add_argument("--paths", action="store_true", help="print one file path per line")


def _dry_run(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--dry-run", action="store_true", help="print the change as a unified diff and write nothing")


def _verb(
    verbs: argparse._SubParsersAction,
    name: str,
    summary: str,
    writes: str,
    example: str,
) -> argparse.ArgumentParser:
    """One subcommand, with the help every verb carries: what, what it writes, an example."""
    return verbs.add_parser(
        name,
        help=summary,
        description=f"{summary} {writes}",
        epilog=f"example:\n  {example}",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )


def build_parser() -> argparse.ArgumentParser:  # noqa: PLR0915 - one registration per verb
    """The argument parser, built separately so a test can inspect it."""
    parser = argparse.ArgumentParser(
        prog="logseq-md",
        description="Read and write file-based Logseq markdown graphs.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    verbs = parser.add_subparsers(dest="verb", metavar="<verb>")

    blocks = _verb(
        verbs,
        "blocks",
        "List blocks matching every filter given, each with its ancestors.",
        _READ_ONLY,
        "logseq-md blocks --graph ~/notes --marker TODO --tag planning",
    )
    blocks.epilog = (
        f"{blocks.epilog}\n\n--since and --until select journals by their date; a page has no date, so either\n"
        "flag leaves pages out.\n\n" + output.BLOCKS_JSON
    )
    _graph(blocks)
    blocks.add_argument("--marker", metavar="MARKER", help="only blocks whose marker is MARKER")
    blocks.add_argument("--tag", metavar="TAG", help="only blocks tagged with or linking to TAG")
    blocks.add_argument("--has-property", metavar="KEY", help="only blocks carrying the property KEY")
    blocks.add_argument("--since", metavar="DATE", help="only journal blocks on or after DATE (YYYY-MM-DD)")
    blocks.add_argument("--until", metavar="DATE", help="only journal blocks on or before DATE (YYYY-MM-DD)")
    blocks.add_argument("--page", metavar="PAGE", help="only blocks on PAGE")
    _read_output(blocks)

    show = _verb(
        verbs,
        "show",
        "Show one block or page with its ancestors and its references resolved.",
        _READ_ONLY,
        "logseq-md show --graph ~/notes 69676218-6ca0-4d45-8d0f-d229c8721922",
    )
    show.epilog = (
        f"{show.epilog}\n\nA page shows its top-level blocks, and its whole outline with --children.\n"
        "Every reference is reported: resolved, dangling, ambiguous, or a cycle where it is met.\n\n" + output.SHOW_JSON
    )
    _graph(show)
    show.add_argument("target", help="a uuid, a page name, a journal date or page:line")
    show.add_argument(
        "--depth", metavar="N", type=int, default=1, help="resolve references N levels deep (default 1, 0 for none)"
    )
    _read_output(show)

    backlinks = _verb(
        verbs,
        "backlinks",
        "List every block that links to a page, each with its ancestors.",
        _READ_ONLY,
        'logseq-md backlinks --graph ~/notes "Bread Starter"',
    )
    backlinks.epilog = (
        f"{backlinks.epilog}\n\nA link is [[page]], #page or #[[page]], compared as Logseq compares names.\n\n"
        + output.BLOCKS_JSON
    )
    _graph(backlinks)
    backlinks.add_argument("page", help="the page name")
    _read_output(backlinks)

    pages = _verb(
        verbs,
        "pages",
        "List every page and journal in the graph, including those with no outline.",
        _READ_ONLY,
        "logseq-md pages --graph ~/notes",
    )
    pages.epilog = f"{pages.epilog}\n\n{output.PAGES_JSON}"
    _graph(pages)
    _shape(pages)

    properties = _verb(
        verbs,
        "properties",
        "Print the property keys dropped from read output.",
        "Needs no graph and writes nothing.",
        "logseq-md properties",
    )
    properties.add_argument("--json", action="store_true", help="print JSON, for scripts")

    ensure_id = _verb(
        verbs,
        "ensure-id",
        "Print a block's id, giving it a new one first if it has none.",
        "Writes at most one id:: line into the block's file, and nothing else.",
        "logseq-md ensure-id --graph ~/notes 69676218-6ca0-4d45-8d0f-d229c8721922",
    )
    _graph(ensure_id)
    ensure_id.epilog = (
        f'{ensure_id.epilog}\n  logseq-md ensure-id --graph ~/notes "Bread Starter:4"\n\n'
        "Prints the id either way. A new id:: goes immediately after the block's content,\n"
        "indented like its other properties. page:line is accepted here, and only here, so a\n"
        "block without an id can get one; every other write takes the id this prints."
    )
    ensure_id.add_argument("target", help="the block: a uuid, or page:line")
    _dry_run(ensure_id)

    set_property = _verb(
        verbs,
        "set-property",
        "Set one property on a block, replacing its value if the key is already there.",
        "Writes one property line and nothing else; the key is copied, never read.",
        "logseq-md set-property --graph ~/notes 69676218-6ca0-4d45-8d0f-d229c8721922 reviewed yes",
    )
    _graph(set_property)
    set_property.epilog = (
        f"{set_property.epilog}\n\nA line already carrying KEY gets the new value in place; otherwise the line\n"
        "goes after the block's last property. id is refused: ensure-id gives a block its id."
    )
    set_property.add_argument("uuid", help="the block's id")
    set_property.add_argument("key", help="the property key, chosen by the caller")
    set_property.add_argument("value", help="the property value")
    _dry_run(set_property)

    append_child = _verb(
        verbs,
        "append-child",
        "Add a block as the last child of a block, or as the last block of a page or journal.",
        "Writes the new lines, and with --record-as one property on the parent; never a :LOGBOOK:.",
        'logseq-md append-child --graph ~/notes 69676218-6ca0-4d45-8d0f-d229c8721922 --text "checked"',
    )
    _graph(append_child)
    append_child.epilog = (
        f"{append_child.epilog}\n"
        '  logseq-md append-child --graph ~/notes 2026-11-12 --create --text "started the review"\n\n'
        "The child goes after the parent's properties, drawers and existing children, indented\n"
        "like its siblings, or as the file indents at that depth. Each line of a multi-line TEXT\n"
        "becomes a wrapped line of the one new block.\n\n"
        "--record-as KEY gives the child an id and sets the property KEY to that id on the parent,\n"
        "in one write, and prints the id. When the parent already carries KEY, the recorded block's\n"
        "content is replaced instead; when that block is gone, exit 4 names its id. Clearing KEY\n"
        "on the parent starts again. KEY needs a block target, not a page.\n\n"
        "--create makes the journal for a YYYY-MM-DD date when it has no file; without it, a\n"
        "missing journal is exit 1."
    )
    append_child.add_argument("target", help="the parent: a block's id, a page name or a journal date")
    append_child.add_argument("--text", required=True, help="the new block's content")
    append_child.add_argument(
        "--record-as",
        metavar="KEY",
        help="record the child's id under KEY on the parent, and update that child on later runs",
    )
    append_child.add_argument("--create", action="store_true", help="create the journal file if it does not exist")
    _dry_run(append_child)

    set_content = _verb(
        verbs,
        "set-content",
        "Replace a block's content, leaving its properties, drawers and children.",
        "Writes the content lines of that one block and nothing else.",
        'logseq-md set-content --graph ~/notes 69676218-6ca0-4d45-8d0f-d229c8721922 --text "rechecked"',
    )
    _graph(set_content)
    set_content.epilog = (
        f"{set_content.epilog}\n\nThe content is the bullet line and its wrapped lines, marker included. Each line\n"
        "of a multi-line TEXT becomes a wrapped line, indented like the block's own. Text that\n"
        "would read as a bullet, a property, a drawer or an open code fence is refused."
    )
    set_content.add_argument("uuid", help="the block's id")
    set_content.add_argument("--text", required=True, help="the new content")
    _dry_run(set_content)

    set_marker = _verb(
        verbs,
        "set-marker",
        "Set, change or remove the task marker on a block.",
        "Writes the marker word on the block's first line and nothing else; never a :LOGBOOK:.",
        "logseq-md set-marker --graph ~/notes 69676218-6ca0-4d45-8d0f-d229c8721922 DOING",
    )
    _graph(set_marker)
    set_marker.epilog = (
        f"{set_marker.epilog}\n  logseq-md set-marker --graph ~/notes 69676218-6ca0-4d45-8d0f-d229c8721922 none"
    )
    set_marker.add_argument("uuid", help="the block's id")
    set_marker.add_argument("marker", help="TODO, DOING, DONE, LATER, NOW, WAITING, CANCELED, or none to remove it")
    _dry_run(set_marker)

    return parser


def _shape_of(args: argparse.Namespace) -> str:
    return "json" if args.json else "paths" if getattr(args, "paths", False) else "text"


def _blocks(args: argparse.Namespace) -> int:
    filters = enumeration.Filters(
        marker=enumeration.parse_marker(args.marker),
        tag=args.tag,
        has_property=args.has_property,
        since=enumeration.parse_date("--since", args.since),
        until=enumeration.parse_date("--until", args.until),
        page=args.page,
    )
    graph = open_graph(args.graph)
    hits = enumeration.find(graph, filters)
    output.emit_blocks(graph, hits, _shape_of(args), output.options(args.children, args.raw, args.keep), sys.stdout)
    return OK


def _show(args: argparse.Namespace) -> int:
    if args.depth < 0:
        raise Refusal(BAD_ARGUMENTS, f"--depth {args.depth}: must be 0 or more")
    graph = open_graph(args.graph)
    target = targets.resolve(graph, args.target)
    resolver = resolution.Resolver(graph)
    opts = output.options(args.children, args.raw, args.keep)
    page = target.page
    shape = _shape_of(args)
    if target.block is None:
        shown = [page.blocks[root] for root in page.roots]
        if args.children:
            shown = list(page.blocks)
        resolved = resolver.resolve(target.path, page.references, args.depth)
        for block in shown:
            resolved += resolver.resolve(target.path, block.references, args.depth, resolution.chain_of(block))
        sys.stdout.write(output.show(graph, target, resolved, shape, opts))
        return OK
    shown = [page.blocks[target.block]]
    if args.children:
        shown += output.descendants(page, target.block)
    resolved = ()
    for block in shown:
        resolved += resolver.resolve(target.path, block.references, args.depth, resolution.chain_of(block))
    sys.stdout.write(output.show(graph, target, resolved, shape, opts))
    return OK


def _backlinks(args: argparse.Namespace) -> int:
    graph = open_graph(args.graph)
    hits = [output.Hit(path, page, block) for path, page, block in resolution.backlinks(graph, args.page)]
    output.emit_blocks(graph, hits, _shape_of(args), output.options(args.children, args.raw, args.keep), sys.stdout)
    return OK


def _pages(args: argparse.Namespace) -> int:
    graph = open_graph(args.graph)
    output.emit_pages(graph, list(enumeration.pages(graph)), _shape_of(args), sys.stdout)
    return OK


def _properties(args: argparse.Namespace) -> int:
    if args.json:
        print(json.dumps({"dropped": list(policy.DROPPED)}))
    else:
        print("\n".join(policy.DROPPED))
    return OK


def _ensure_id(args: argparse.Namespace) -> int:
    target, block = writes.block_for_write(open_graph(args.graph), args.target, page_line=True)
    found, edit = writes.plan_ensure_id(target.page, block, identity.mint)
    writes.run(target, edit, dry_run=args.dry_run)
    if not args.dry_run:
        print(found)
    return OK


def _set_property(args: argparse.Namespace) -> int:
    target, block = writes.block_for_write(open_graph(args.graph), args.uuid)
    edit = writes.plan_set_property(target.page, block, args.key, args.value)
    writes.run(target, edit, dry_run=args.dry_run)
    return OK


def _set_content(args: argparse.Namespace) -> int:
    target, block = writes.block_for_write(open_graph(args.graph), args.uuid)
    edit = writes.plan_set_content(target.page, block, args.text)
    writes.run(target, edit, dry_run=args.dry_run)
    return OK


def _set_marker(args: argparse.Namespace) -> int:
    marker = writes.parse_marker(args.marker)
    target, block = writes.block_for_write(open_graph(args.graph), args.uuid)
    edit = writes.plan_set_marker(target.page, block, marker)
    writes.run(target, edit, dry_run=args.dry_run)
    return OK


def _append_child(args: argparse.Namespace) -> int:
    graph = open_graph(args.graph)
    where = writes.append_target(graph, args.target, create=args.create)
    parent = None if where.parent is None else where.page.blocks[where.parent]
    if args.record_as is None:
        edits = writes.plan_append_child(where.page, parent, args.text)
        writes.run_edits(where.path, where.page, edits, dry_run=args.dry_run, create=where.create)
        return OK
    writes.check_key(args.record_as)
    if parent is None:
        raise Refusal(BAD_ARGUMENTS, f"{args.target}: --record-as records on a block; give the parent block's id")
    recorded = writes.carrying(parent, args.record_as)
    if recorded is None:
        child = identity.mint()
        edits = writes.plan_append_child(where.page, parent, args.text, child_id=child, record_as=args.record_as)
        writes.run_edits(where.path, where.page, edits, dry_run=args.dry_run)
    else:
        child = recorded.value.strip()
        if not identity.UUID.fullmatch(child):
            raise Refusal(BAD_ARGUMENTS, f"line {recorded.line + 1}: {args.record_as} does not hold a block id")
        if child.lower() not in identity.scan(graph).found:
            raise Refusal(RECORD_GONE, f"{child}: recorded as {args.record_as}, but no block carries this id")
        target, block = writes.block_for_write(graph, child)
        writes.run(target, writes.plan_set_content(target.page, block, args.text), dry_run=args.dry_run)
    if not args.dry_run:
        print(child)
    return OK


def _not_implemented(args: argparse.Namespace) -> int:
    print(f"logseq-md {args.verb}: not implemented yet", file=sys.stderr)
    return BAD_ARGUMENTS


#: Verb name to handler. A later stage replaces one entry and nothing else.
HANDLERS: dict[str, Handler] = {
    "blocks": _blocks,
    "show": _show,
    "backlinks": _backlinks,
    "pages": _pages,
    "properties": _properties,
    "ensure-id": _ensure_id,
    "set-property": _set_property,
    "append-child": _append_child,
    "set-content": _set_content,
    "set-marker": _set_marker,
}


def placeholders() -> list[str]:
    """The verbs still waiting for a real handler."""
    return sorted(name for name, handler in HANDLERS.items() if handler is _not_implemented)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command and return its exit code.

    Returning rather than exiting keeps the whole command testable in-process;
    `run` is the thin wrapper the console script points at. A `Refusal` raised
    anywhere below becomes its message on stderr and its code.
    """
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.verb is None:
        parser.print_help()
        return OK
    try:
        return HANDLERS[args.verb](args)
    except Refusal as refusal:
        print(f"logseq-md {args.verb}: {refusal.message}", file=sys.stderr)
        return refusal.code


def run() -> None:
    """Console script entry point."""
    sys.exit(main())
