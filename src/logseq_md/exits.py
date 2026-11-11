"""Exit codes, defined once.

A caller branches on the code rather than on English that is free to be
reworded, so every refusal in the package names one of these rather than a
number. The table is DESIGN.md section 10, "Exit codes".
"""

from __future__ import annotations

#: Did it.
OK = 0
#: The block or page is not there.
NOT_FOUND = 1
#: The arguments were wrong. Also argparse's own code for a usage error.
BAD_ARGUMENTS = 2
#: The file changed since it was read.
FILE_CHANGED = 3
#: A recorded block is gone.
RECORD_GONE = 4
#: The file is not valid UTF-8, or the graph is not one.
UNREADABLE = 5


class Refusal(Exception):  # noqa: N818 - a refusal is an outcome, not an error
    """A command declining to do what it was asked, with the code that says why.

    `main` turns one into its message on stderr and its code as the exit status,
    so nothing below the command line prints or exits on its own.
    """

    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
