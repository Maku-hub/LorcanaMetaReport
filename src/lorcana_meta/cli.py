"""Command line entry point.

    python -m lorcana_meta build --last 30 --top 32

Writes ``site/data/meta.json``; the static site in ``site/`` reads nothing else.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from .analyze import build_meta
from .cards import CardIndex
from .console import configure_output
from .models import Deck
from .sources import InkdecksSource, LocalSource, SourceError

log = logging.getLogger("lorcana_meta")

CARD_DB_CREDIT = {
    "name": "lorcana-api.com",
    "url": "https://lorcana-api.com/",
}


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="lorcana_meta",
        description="Build a Lorcana tournament-meta report from tournament decklists.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    build = sub.add_parser("build", help="fetch decks, aggregate, write site data")
    build.add_argument(
        "--source",
        default="inkdecks",
        choices=("inkdecks", "local"),
        help="where decklists come from. 'inkdecks' needs their written permission - "
        "see --inkdecks-consent (default: inkdecks)",
    )
    build.add_argument(
        "--format",
        default="Core Constructed",
        dest="fmt",
        help="Format label for decks that do not carry one, which in practice means "
        "--source local. For inkdecks the format follows --inkdecks-category "
        "(default: Core Constructed)",
    )

    window = build.add_argument_group("time window")
    window.add_argument("--last", type=int, help="days back from today")
    window.add_argument("--start", help="first tournament date, YYYY-MM-DD")
    window.add_argument("--end", help="last tournament date, YYYY-MM-DD")

    build.add_argument(
        "--top",
        type=int,
        default=32,
        help="only keep decks that placed this high or better; 0 keeps everything "
        "(default: 32)",
    )
    build.add_argument(
        "--min-players",
        type=int,
        default=None,
        help="ignore events smaller than this. A twelve-person Friday night is a "
        "different game from a 200-player regional. Decks whose event size is unknown "
        "are kept",
    )
    build.add_argument(
        "--min-pair-decks",
        type=int,
        default=3,
        help="ink pairs with fewer decks than this are dropped as noise (default: 3)",
    )
    build.add_argument(
        "--cluster-threshold",
        type=float,
        default=0.60,
        help="how much card overlap counts as the same archetype, 0-1. Lower merges "
        "more lists into one deck, higher splits them (default: 0.60)",
    )
    inkdecks = build.add_argument_group(
        "inkdecks source",
        "Their terms require written permission for automated access. These options "
        "do nothing for the other sources.",
    )
    inkdecks.add_argument(
        "--inkdecks-category",
        default="core",
        choices=("core", "infinity", "poorcana", "all"),
        help="which of the site's tabs to read: All / Core / Infinity / Poorcana. "
        "This is what selects the format for this source, not --format. 'all' mixes "
        "them and labels each deck with its own (default: core)",
    )
    inkdecks.add_argument(
        "--inkdecks-consent",
        action="store_true",
        help="confirm you have inkdecks' written permission (or set INKDECKS_CONSENT=1)",
    )
    inkdecks.add_argument(
        "--inkdecks-delay",
        type=float,
        default=3.0,
        help="seconds between requests, one at a time. Grows automatically if the site "
        "rate-limits, and never shrinks within a run (default: 3.0)",
    )
    inkdecks.add_argument(
        "--inkdecks-scraper",
        default="auto",
        choices=("auto", "plain", "curl_cffi"),
        dest="inkdecks_transport",
        help="how to make the requests. 'auto' uses plain HTTP and escalates to "
        "curl_cffi only if the site refuses the client; 'plain' never escalates; "
        "'curl_cffi' starts there. Whichever worked is remembered (default: auto)",
    )
    inkdecks.add_argument(
        "--inkdecks-max-decks",
        type=int,
        default=1500,
        help="stop after this many decks, best-placed first, so a mistyped date range "
        "cannot become thousands of requests (default: 1500)",
    )

    build.add_argument(
        "--local-dir",
        default="data/decks",
        help="directory of local decklists when --source local (default: data/decks)",
    )
    build.add_argument(
        "--out",
        default="site/data/meta.json",
        help="where to write the report (default: site/data/meta.json)",
    )
    build.add_argument(
        "--refresh-cards", action="store_true", help="re-download the card database"
    )
    build.add_argument("--indent", type=int, default=None, help="pretty-print the JSON")
    build.add_argument("-v", "--verbose", action="store_true")

    return parser.parse_args(argv)


def _resolve_window(args: argparse.Namespace) -> tuple[date, date]:
    today = datetime.now(timezone.utc).date()
    if args.start or args.end:
        start = date.fromisoformat(args.start) if args.start else today - timedelta(days=30)
        end = date.fromisoformat(args.end) if args.end else today
    else:
        end = today
        start = today - timedelta(days=args.last or 30)
    if start > end:
        raise SystemExit(f"empty window: start {start} is after end {end}")
    return start, end


#: Placing filters inkdecks offers, smallest bucket first.
_INKDECKS_RANKS = ((1, "winners"), (2, "top2"), (4, "top4"), (8, "top8"), (16, "top16"), (32, "top32"))


def _inkdecks_rank(top: int) -> str:
    """Map --top onto the tightest server-side filter that still covers it.

    Letting the site do the cut means fetching 8 pages instead of 41 for a top-8
    report. Anything the filter cannot express is left to the local --top cut.
    """
    if not top:
        return ""
    for bound, name in _INKDECKS_RANKS:
        if top <= bound:
            return name
    return ""


def _build_source(args: argparse.Namespace):
    if args.source == "local":
        return LocalSource(args.local_dir, fmt=args.fmt)
    if args.source == "inkdecks":
        return InkdecksSource(
            category=args.inkdecks_category,
            rank=_inkdecks_rank(args.top),
            consent=args.inkdecks_consent,
            delay=args.inkdecks_delay,
            max_decks=args.inkdecks_max_decks,
            transport=args.inkdecks_transport,
            # Attendance is on the listing row, so this filters before any deck page
            # is fetched - it saves requests rather than wasting them.
            min_players=args.min_players,
        )
    raise SourceError(f"Unknown source {args.source!r}")


def _apply_top_cut(decks: list[Deck], top: int) -> list[Deck]:
    """Keep the top N of each event. Decks with no recorded placing are kept."""
    if not top:
        return decks
    return [d for d in decks if d.standing is None or d.standing <= top]


def _apply_min_players(decks: list[Deck], minimum: int | None) -> list[Deck]:
    """Drop decks from events smaller than `minimum` players.

    A twelve-person Friday night is a different game from a 200-player regional, and
    mixing them flattens the meta towards whatever the locals happen to brew. This is
    the filter that says "only real events".

    A deck whose event size is unknown is kept, on the same principle as the placing
    cut: we do not silently discard data we cannot judge.
    """
    if not minimum:
        return decks
    return [d for d in decks if d.tournament_players is None or d.tournament_players >= minimum]


def _drop_thin_pairs(report: dict, minimum: int) -> dict:
    """Fold ink pairs with too few decks out of the report.

    A pair seen twice is not a meta reading, and leaving it in makes a 1-deck
    novelty look like a 3% archetype. Dropped pairs are reported as a count so the
    number is never silently missing.
    """
    if minimum <= 1:
        return report

    kept = [p for p in report["pairs"] if p["decks"] >= minimum]
    dropped = [p for p in report["pairs"] if p["decks"] < minimum]
    if not dropped:
        return report

    total = sum(p["decks"] for p in kept)
    for pair in kept:
        pair["share"] = round(100.0 * pair["decks"] / total, 1) if total else 0.0
        # Archetype shares are quoted against the field, so they move with it too.
        for variant in pair.get("variants", []):
            variant["share_of_field"] = (
                round(100.0 * variant["decks"] / total, 1) if total else 0.0
            )

    report["pairs"] = kept
    report["totals"]["decks_in_pairs"] = total
    report["totals"]["pairs"] = len(kept)
    report["totals"]["decks_dropped_thin_pairs"] = sum(p["decks"] for p in dropped)
    report["totals"]["thin_pairs_dropped"] = len(dropped)
    from .analyze import _threats  # local import keeps the public surface small

    report["threats"] = _threats(kept, report["cards"])
    return report


def cmd_build(args: argparse.Namespace) -> int:
    start, end = _resolve_window(args)
    source = _build_source(args)

    log.info("fetching %s decks from %s: %s .. %s", args.fmt, source.name, start, end)
    decks = source.fetch(start, end)
    log.info("fetched %d decklists", len(decks))

    decks = _apply_top_cut(decks, args.top)
    log.info("%d decklists after the top-%s cut", len(decks), args.top or "all")

    # A source may already have filtered this out - inkdecks does, before fetching -
    # so this is the backstop that makes the rule hold for every source.
    if args.min_players:
        before = len(decks)
        decks = _apply_min_players(decks, args.min_players)
        if before != len(decks):
            log.info(
                "%d decklists after dropping events under %d players (%d removed)",
                len(decks),
                args.min_players,
                before - len(decks),
            )

    index = CardIndex.load(refresh=args.refresh_cards)
    log.info("card database: %d printings", len(index))

    report = build_meta(
        decks,
        index,
        period={"start": start.isoformat(), "end": end.isoformat(), "days": (end - start).days + 1},
        source={
            "name": source.name,
            "attribution": source.attribution,
            "attribution_url": source.attribution_url,
            "publishable": getattr(source, "publishable", True),
            "skipped_decks": len(getattr(source, "skipped", [])),
            "card_db": CARD_DB_CREDIT,
        },
        filters={
            # The source knows better than the flag: inkdecks selects by category,
            # and "all" means the format is per deck rather than one label.
            "format": getattr(source, "fmt", args.fmt),
            "top": args.top,
            "min_players": args.min_players,
            "min_pair_decks": args.min_pair_decks,
        },
        generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        cluster_threshold=args.cluster_threshold,
    )
    report = _drop_thin_pairs(report, args.min_pair_decks)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(report, ensure_ascii=False, indent=args.indent), encoding="utf-8"
    )

    totals = report["totals"]
    anomalies = report["anomalies"]
    log.info(
        "wrote %s - %d decks, %d tournaments, %d ink pairs, %d archetypes",
        out,
        totals["decks"],
        totals["tournaments"],
        totals["pairs"],
        totals.get("variants", 0),
    )
    if anomalies["unknown_card_count"]:
        log.warning(
            "%d card names could not be matched (top: %s)",
            anomalies["unknown_card_count"],
            ", ".join(c["name"] for c in anomalies["unknown_cards"][:5]),
        )
    if not report["source"].get("publishable", True):
        log.warning(
            "this report is built from data licensed for private use, so it is marked "
            "unpublishable: tests/check_report.py will refuse it and the Pages workflow "
            "will not deploy it. Read it locally instead: python tools/bundle_report.py"
        )
    if not totals["decks"]:
        log.error("no decks in the report - check the window, the format and the source")
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    # Before anything can print a card name to a legacy Windows console.
    configure_output()
    args = _parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if getattr(args, "verbose", False) else logging.INFO,
        format="%(levelname)s %(message)s",
        # stdout, not the usual stderr. These lines are progress, not failure, and
        # Windows PowerShell renders anything a native command puts on stderr as a
        # red NativeCommandError block - so a normal build looked like a crash.
        # Failure is still signalled the way a CLI should: a non-zero exit code.
        stream=sys.stdout,
    )
    try:
        if args.command == "build":
            return cmd_build(args)
    except SourceError as error:
        log.error("%s", error)
        return 2
    raise SystemExit(f"unknown command {args.command!r}")


if __name__ == "__main__":
    sys.exit(main())
