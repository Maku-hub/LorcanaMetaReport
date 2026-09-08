"""Write the single-file report, as a command of its own.

`lorcana-meta build` already does this at the end of every build, so reach for this
when you want to re-bundle without refetching anything - after editing the page, say,
or to write a copy somewhere else.

    python tools/bundle_report.py
    # -> report.html, double-click it

The logic lives in `lorcana_meta.bundle`; this file is the entry point.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lorcana_meta.bundle import SITE, build  # noqa: E402
from lorcana_meta.console import configure_output  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    configure_output()
    parser = argparse.ArgumentParser(
        description="Bundle the report into a single self-contained HTML file.",
        epilog="Use this instead of GitHub Pages when the report should stay private.",
    )
    parser.add_argument(
        "--data",
        default=str(SITE / "data" / "meta.json"),
        help="the report to embed (default: site/data/meta.json)",
    )
    parser.add_argument(
        "--out",
        default="report.html",
        help="where to write the bundle (default: report.html)",
    )
    args = parser.parse_args(argv)

    data = Path(args.data)
    if not data.exists():
        print(f"{data} does not exist - run a build first", file=sys.stderr)
        return 1

    return build(SITE / "index.html", data, Path(args.out))


if __name__ == "__main__":
    raise SystemExit(main())
