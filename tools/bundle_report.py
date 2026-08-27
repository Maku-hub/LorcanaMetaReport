"""Bundle the whole report into one HTML file you can just double-click.

Why you want this: GitHub Pages cannot host a private site. A Pages site published
from a private personal repository is **public** - the repo stays private, the page
does not, and access control is a GitHub Enterprise Cloud feature for
organization-owned repositories only. So "private repo + Pages" does not give you a
private report.

A single file does. It needs no server, no hosting and no account, it opens straight
from your filesystem, and nothing about it leaves your machine.

    python tools/bundle_report.py
    # -> report.html, double-click it

The CSS, the JavaScript and the report data are all inlined, which is also what makes
it work from ``file://``: a page opened from disk is not allowed to fetch a sibling
JSON file, so the data has to travel inside the page.

One caveat: card images are still loaded from Ravensburger's CDN, so the card
inspector shows placeholders when you are offline. Everything else - shares,
archetypes, inclusion rates, the threat board, your-deck comparison - works with no
connection at all.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lorcana_meta.console import configure_output  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"

STYLESHEET = re.compile(r'\s*<link rel="stylesheet" href="([^"]+)"\s*/?>')
SCRIPT = re.compile(r'\s*<script src="([^"]+)"></script>')


def _inline_safe(text: str) -> str:
    """Escape the sequences that would end an inline <script> block early.

    A `</script>` inside a card's rules text, or a stray `<!--`, would terminate the
    element and break the page. Escaping `<` and the separators keeps the JSON valid
    while making it impossible to close the tag from inside.
    """
    for raw, escaped in (
        ("<", "\\u003c"),
        (">", "\\u003e"),
        (chr(0x2028), "\\u2028"),  # LINE SEPARATOR: legal in JSON, breaks JS
        (chr(0x2029), "\\u2029"),  # PARAGRAPH SEPARATOR: same
    ):
        text = text.replace(raw, escaped)
    return text


def build(index: Path, data: Path, out: Path) -> int:
    html = index.read_text(encoding="utf-8")
    report = json.loads(data.read_text(encoding="utf-8"))

    def replace_stylesheet(match: re.Match) -> str:
        css = (SITE / match.group(1)).read_text(encoding="utf-8")
        return f"\n    <style>\n{css}\n    </style>"

    def replace_script(match: re.Match) -> str:
        source = (SITE / match.group(1)).read_text(encoding="utf-8")
        payload = _inline_safe(json.dumps(report, ensure_ascii=False, separators=(",", ":")))
        return (
            f'\n    <script type="application/json" id="meta-data">{payload}</script>'
            f"\n    <script>\n{source}\n    </script>"
        )

    html, styles = STYLESHEET.subn(replace_stylesheet, html)
    html, scripts = SCRIPT.subn(replace_script, html)

    if not styles or not scripts:
        print(
            f"Expected a stylesheet and a script tag in {index}, found "
            f"{styles} and {scripts}. Has site/index.html changed?",
            file=sys.stderr,
        )
        return 1

    # A bundled file has no server, so say where it came from.
    html = html.replace(
        "<title>Lorcana Meta Report</title>",
        "<title>Lorcana Meta Report</title>\n    "
        "<!-- Self-contained report. Built by tools/bundle_report.py - "
        "no server needed, open it directly. -->",
    )

    out.write_text(html, encoding="utf-8")

    size_mb = out.stat().st_size / (1024 * 1024)
    totals = report.get("totals", {})
    period = report.get("period", {})
    print(f"Wrote {out} ({size_mb:.1f} MB)")
    print(
        f"  {totals.get('decks', 0)} decks, {totals.get('variants', 0)} archetypes, "
        f"{period.get('start')} to {period.get('end')}"
    )
    print("  Open it by double-clicking - no server, nothing leaves your machine.")
    return 0


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
