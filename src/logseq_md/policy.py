"""The property keys dropped from read output, and nothing else (DESIGN.md section 6).

This is the one module the opacity test allows by path: the list below is a
policy about Logseq's own keys and its plugins' fold and drawing state, printed
by `logseq-md properties` so a person can see it rather than infer it. No code
anywhere branches on these names except to drop them from output.
"""

from __future__ import annotations

#: Dropped from read output unless `--raw` or `--keep <key>` says otherwise.
DROPPED = ("collapsed", "excalidraw-plugin")
