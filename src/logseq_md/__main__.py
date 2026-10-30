"""Allow `python -m logseq_md` as well as the console script."""

from __future__ import annotations

from logseq_md.cli import run

if __name__ == "__main__":
    run()
