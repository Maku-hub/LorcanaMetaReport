"""Make console output survive a non-UTF-8 terminal.

Card names are not ASCII. A Windows console running a legacy code page (cp1250,
cp852, cp437 - anything but 65001) cannot encode them, and Python's default
behaviour splits two ways, both bad:

* ``print("アリエル - Spectacular Singer")`` raises ``UnicodeEncodeError`` and takes
  the whole build down, and
* ``logging`` survives but writes ``\\u30a2\\u30ea\\u30a8\\u30eb - Spectacular Singer``,
  which is unreadable exactly when you are trying to read it - the log line that
  reports unmatched card names.

Reconfiguring the streams to UTF-8 fixes both. Modern Windows terminals and every
POSIX shell are already UTF-8, so this is usually a no-op.

Note this is only about the *console*. Every file this project reads or writes names
its encoding explicitly, which is why the pipeline itself never depended on the
platform default.
"""

from __future__ import annotations

import sys


def configure_output() -> None:
    """Switch stdout/stderr to UTF-8 when the terminal is on something else.

    Safe to call more than once, and safe when the streams are redirected, captured
    or replaced by something that cannot be reconfigured.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue  # a captured or wrapped stream - leave it alone

        encoding = (getattr(stream, "encoding", "") or "").lower().replace("-", "")
        if encoding in ("utf8", "utf8mb4"):
            continue

        try:
            # `replace` rather than `strict`: a report is still worth printing with
            # one mangled character in it, and worth nothing if it raises instead.
            reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError, OSError):
            pass
