"""Sanity-check a built report.

Run after `lorcana-meta build` to confirm the output is worth publishing. Exists as
a file rather than an inline script in the workflows because the same check has to
run under bash and PowerShell, and inline heredocs are bash-only.

    python tests/check_report.py [path]      # default: site/data/meta.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lorcana_meta.console import configure_output  # noqa: E402

DEFAULT = Path("site/data/meta.json")


def main(argv: list[str] | None = None) -> int:
    configure_output()
    argv = sys.argv[1:] if argv is None else argv
    path = Path(argv[0]) if argv else DEFAULT

    if not path.exists():
        print(f"{path} does not exist - run a build first", file=sys.stderr)
        return 1

    report = json.loads(path.read_text(encoding="utf-8"))
    totals = report.get("totals", {})
    period = report.get("period", {})
    anomalies = report.get("anomalies", {})

    problems = []

    # The gate that makes a private-use licence stick. The Pages workflow runs this
    # before deploying, so a report built from data you may not republish fails here
    # instead of quietly going live.
    source = report.get("source", {})
    if not source.get("publishable", True):
        problems.append(
            f"the data came from {source.get('name', 'an unpublishable source')} and is "
            "marked private - do not publish it. Read it locally: "
            "python tools/bundle_report.py"
        )

    if not totals.get("decks"):
        problems.append("no decks in the report")
    if not report.get("pairs"):
        problems.append("no ink pairs in the report")
    if not totals.get("variants"):
        problems.append("no archetypes in the report")
    if not report.get("threats"):
        problems.append("no threat ranking in the report")
    if not report.get("cards"):
        problems.append("no card details in the report")

    # Shares are quoted against the field, so they have to add up to it.
    share = sum(pair["share"] for pair in report.get("pairs", []))
    if report.get("pairs") and not (99.0 <= share <= 101.0):
        problems.append(f"ink pair shares sum to {share:.1f}%, expected ~100%")

    print(
        f"{path}: {totals.get('decks', 0)} decks, {totals.get('tournaments', 0)} events, "
        f"{totals.get('pairs', 0)} ink pairs, {totals.get('variants', 0)} archetypes, "
        f"{period.get('start')} to {period.get('end')}"
    )

    unmatched = anomalies.get("unknown_card_count", 0)
    if unmatched:
        names = ", ".join(c["name"] for c in anomalies.get("unknown_cards", [])[:5])
        print(f"warning: {unmatched} card name(s) could not be matched: {names}")

    for problem in problems:
        print(f"error: {problem}", file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
