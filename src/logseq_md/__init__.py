"""Read and write file-based Logseq markdown graphs.

A Logseq file graph is a directory of markdown: `pages/` for topics, `journals/`
for dates, one block per bullet, nested by indentation. This package reads that
shape and writes back into it without reformatting the parts it did not touch.
"""

from __future__ import annotations

__all__ = ["__version__"]

#: Resolved from the installed distribution rather than written here, so there is
#: one version in the repository and the release job owns it. A source checkout
#: that was never installed has no distribution metadata, and reports that rather
#: than guessing.
try:  # pragma: no cover - the except branch needs an uninstalled checkout
    from importlib.metadata import PackageNotFoundError, version

    __version__ = version("logseq-md")
except PackageNotFoundError:  # pragma: no cover
    __version__ = "0.0.0+unknown"
