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

from lorcana_meta.analyze import CONTRIBUTORS_SHOWN  # noqa: E402
from lorcana_meta.console import configure_output  # noqa: E402

DEFAULT = Path("site/data/meta.json")


def _check_charts_reconcile(report: dict, totals: dict) -> list[str]:
    """The overview's three charts are three cuts of one field. They have to agree.

    A reader who adds up one chart and compares it with another is doing the obvious
    thing, and the numbers have to survive it. The archetype chart is deliberately
    incomplete - one-off brews are not in it, a quarter of a real field - which is
    stated on the page; what must never happen is a pair whose variants do not add up
    to it, or an ink whose count disagrees with the pairs it appears in.
    """
    problems = []
    pairs = report.get("pairs", [])
    total = totals.get("decks", 0)
    if not pairs or not total:
        return problems

    if sum(pair["decks"] for pair in pairs) != total - totals.get(
        "decks_dropped_thin_pairs", 0
    ):
        problems.append(
            f"the ink pairs hold {sum(p['decks'] for p in pairs)} decks, the field says "
            f"{total} and {totals.get('decks_dropped_thin_pairs', 0)} were dropped as thin"
        )

    for pair in pairs:
        inside = sum(variant["decks"] for variant in pair.get("variants", []))
        if inside != pair["decks"]:
            problems.append(
                f"{pair['label']}: its archetypes hold {inside} decks but the pair says "
                f"{pair['decks']} - every deck belongs to exactly one archetype"
            )
        within = sum(variant["share_of_pair"] for variant in pair.get("variants", []))
        if pair.get("variants") and not (99.0 <= within <= 101.0):
            problems.append(f"{pair['label']}: archetype shares of the pair sum to {within:.1f}%")

    # Single-ink presence counts every deck that plays an ink, so it must equal the
    # pairs that ink appears in - the chart is a different cut, not a different field.
    from collections import Counter

    implied: Counter = Counter()
    for pair in pairs:
        for ink in pair["inks"]:
            implied[ink] += pair["decks"]
    for row in report.get("inks", []):
        if row["decks"] != implied[row["ink"]]:
            problems.append(
                f"single-ink {row['ink']}: chart says {row['decks']} decks, the ink pairs "
                f"imply {implied[row['ink']]}"
            )
    return problems


def _check_threats(report: dict, totals: dict) -> list[str]:
    """The threat board must describe the same field as everything else.

    It names archetypes now, not ink pairs, and the decks it names have to add up:
    every deck running a card belongs to exactly one contributing group. Brews carry
    no card table in the report, so an attribution assembled from the report alone
    would lose them - a quarter of a real field - and the loss would look like nothing.
    """
    problems = []
    total = totals.get("decks", 0)
    if not total:
        return problems

    for threat in report.get("threats", []):
        named = sum(group["decks"] for group in threat["archetypes"])
        shown = len(threat["archetypes"])
        # A short list is either the cap or a lost contributor, and the two look the
        # same from the counts alone - a first version of this check could not tell
        # them apart and let a dropped group through.
        expected = min(threat["contributor_count"], CONTRIBUTORS_SHOWN)
        if shown != expected:
            problems.append(
                f"{threat['name']}: {shown} contributor(s) shipped, expected {expected} "
                f"of {threat['contributor_count']}"
            )
        if shown < threat["contributor_count"]:
            # The list is capped for size; only the counts can be reconciled.
            if named > threat["decks"]:
                problems.append(
                    f"{threat['name']}: the groups shown already name {named} decks but "
                    f"only {threat['decks']} run it"
                )
        elif named != threat["decks"]:
            problems.append(
                f"{threat['name']}: contributors name {named} decks, {threat['decks']} "
                f"run it - a deck must belong to exactly one group"
            )

        if threat["decks"] > total:
            problems.append(
                f"{threat['name']}: run by {threat['decks']} decks in a {total}-deck field"
            )
        presence = round(100.0 * threat["decks"] / total, 1)
        if abs(threat["field_presence"] - presence) > 0.05:
            problems.append(
                f"{threat['name']}: field presence {threat['field_presence']}% does not "
                f"match {threat['decks']} of {total} decks ({presence}%)"
            )
    return problems


def _check_trend(report: dict, totals: dict) -> list[str]:
    """Movement has to add up, or say why it is not there.

    A delta is the number a reader acts on - "this deck is rising, bring the answer" -
    so a split that quietly lost a third of the field, or a row claiming movement the
    report has already said it cannot show, is worse than no movement section at all.
    """
    trend = report.get("trend")
    if trend is None:
        return ["no movement block in the report - the About page reads from it"]

    problems = []
    rows = [(p["label"], p.get("trend")) for p in report.get("pairs", [])]
    rows += [
        (f"{p['label']} / {v['label']}", v.get("trend"))
        for p in report.get("pairs", [])
        for v in p.get("variants", [])
    ]
    rows += [(f"ink {i['label']}", i.get("trend")) for i in report.get("inks", [])]
    rows += [(f"card {c['name']}", c.get("trend")) for c in report.get("threats", [])]

    if not trend.get("usable"):
        if not trend.get("reason"):
            problems.append("movement is not shown and the report does not say why")
        named = [label for label, row in rows if row]
        if named:
            problems.append(
                f"{len(named)} row(s) carry a delta while movement is switched off, "
                f"first: {named[0]}"
            )
        return problems

    counted = (
        trend["first"]["decks"] + trend["second"]["decks"] + trend.get("undated_decks", 0)
    )
    if counted != totals.get("decks"):
        problems.append(
            f"the window halves account for {counted} decks but the field has "
            f"{totals.get('decks')} - some decks fell between the halves"
        )

    for label, row in rows:
        if not row:
            continue
        expected = round(row["second_share"] - row["first_share"], 1)
        if abs(row["delta"] - expected) > 0.05:
            problems.append(
                f"{label}: delta {row['delta']} is not the difference between the two "
                f"shares on screen ({row['first_share']} → {row['second_share']})"
            )
    return problems


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

    # The gate that makes a private-use licence stick. Nothing in this repo publishes
    # any more (docs/DECISIONS.md section 11), so this is the check anything added
    # later would have to be told to ignore before inkdecks data could go live.
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

    problems += _check_charts_reconcile(report, totals)
    problems += _check_threats(report, totals)
    problems += _check_trend(report, totals)

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
