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

#: What to call a format when the source does not name one and the flag is silent.
DEFAULT_FORMAT = "Core Constructed"

CARD_DB_CREDIT = {
    "name": "lorcana-api.com",
    "url": "https://lorcana-api.com/",
}


def _build_version() -> dict:
    """What built this report: package version, commit, and whether the tree was dirty.

    A `report.html` sits on disk and gets opened weeks later. It already records the
    window, the placing cut and the clustering threshold - everything about the
    *question* - but nothing about the code that answered it. When a number looks
    wrong, "which build produced this" is the first thing you want and the one thing
    it could not tell you.

    `dirty` matters as much as the commit: a report built from a working tree with
    uncommitted changes cannot be reproduced from that commit, and saying so is the
    difference between a reproducible artefact and one that merely looks like one.

    Git absence is not an error. An install from a wheel has no repository, and a
    report is still perfectly valid without a commit to name.
    """
    import subprocess

    from . import __version__

    info: dict = {"version": __version__, "commit": None, "dirty": None}
    repo = Path(__file__).resolve().parents[2]
    if not (repo / ".git").exists():
        return info

    def git(*args: str) -> str | None:
        try:
            done = subprocess.run(
                ["git", "-C", str(repo), *args],
                capture_output=True,
                text=True,
                timeout=5,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        return done.stdout.strip() if done.returncode == 0 else None

    info["commit"] = git("rev-parse", "--short", "HEAD")
    status = git("status", "--porcelain")
    if info["commit"] is not None and status is not None:
        info["dirty"] = bool(status)
    return info


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
        "--inkdecks-max-decks",
        type=int,
        default=1500,
        help="stop after this many decks, best-placed first, so a mistyped date range "
        "cannot become thousands of requests (default: 1500)",
    )

    # --format lives here, not next to --source, because it only ever labels decks that
    # arrive without a format of their own. Sitting at the top it read like the switch
    # that picks the format to fetch, which for inkdecks is --inkdecks-category.
    local = build.add_argument_group("local source", "Ignored unless --source local.")
    local.add_argument(
        "--local-dir",
        default="data/decks",
        help="directory of local decklists (default: data/decks)",
    )
    local.add_argument(
        "--format",
        default=None,
        dest="fmt",
        help="format label for decks that carry none themselves - the local source "
        "only. inkdecks names its own format from --inkdecks-category, so this is "
        "ignored there (default: Core Constructed)",
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
    # On by default: for the default source the single file is the only way to read
    # the report, and leaving it as a second command let it go silently stale.
    build.add_argument(
        "--no-bundle",
        dest="bundle",
        action="store_false",
        help="skip writing report.html (the data alone is enough when serving site/)",
    )
    build.add_argument(
        "--bundle-out",
        default="report.html",
        help="where to write the single-file report (default: report.html)",
    )
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
_INKDECKS_RANKS = (
    (1, "winners"),
    (2, "top2"),
    (4, "top4"),
    (8, "top8"),
    (16, "top16"),
    (32, "top32"),
)


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


#: Fields computed and consumed inside the pipeline, then stripped before the report
#: is written. They are real inputs - `_threats` needs `avg_copies_overall` and
#: `pair_share`, `signature_cards` ranks on `edge` and `is_character` - but no reader
#: of the finished file has any use for them, and on a 320-deck field they were 15%
#: of it. Build fully, serialise leanly.
_INTERNAL_FIELDS = {
    "card_row": ("avg_copies_overall", "total_copies"),
    "signature": ("edge", "is_character"),
    "card": ("set_id",),
}


def _lean(report: dict) -> dict:
    """Strip working fields, and card details nothing left in the report points at.

    Runs last, once every derived number is final. Anything removed here must have no
    reader in `site/assets/app.js`; `tests/test_report_shape.py` holds that line.
    """
    for pair in report.get("pairs", []):
        for row in pair.get("cards", []):
            for key in _INTERNAL_FIELDS["card_row"]:
                row.pop(key, None)
        for variant in pair.get("variants", []):
            for row in variant.get("cards", []):
                for key in _INTERNAL_FIELDS["card_row"]:
                    row.pop(key, None)
            for entry in variant.get("signature", []):
                for key in _INTERNAL_FIELDS["signature"]:
                    entry.pop(key, None)

    # Brews carry no card table (see analyze._variants), so cards played only by a
    # one-off list are no longer reachable from anywhere. Keep the map to what the
    # report can actually ask about.
    reachable = {threat["name"] for threat in report.get("threats", [])}
    for pair in report.get("pairs", []):
        reachable |= {row["name"] for row in pair.get("cards", [])}
        for variant in pair.get("variants", []):
            reachable |= {row["name"] for row in variant.get("cards", [])}
            reachable |= {entry["name"] for entry in variant.get("signature", [])}

    cards = report.get("cards", {})
    report["totals"]["cards_described"] = len(reachable)
    report["cards"] = {name: card for name, card in cards.items() if name in reachable}
    for card in report["cards"].values():
        for key in _INTERNAL_FIELDS["card"]:
            card.pop(key, None)

    return report


def _bundle(data: Path, out: Path) -> int:
    """Write the single-file report, as the last step of a build.

    Folded into `build` rather than left as a second command, and not for the
    keystroke: the two-step version let `report.html` go quietly stale. Rebuild the
    data, forget the bundle, open the file - it renders perfectly and shows last
    week's meta. The embedded build stamp is the only clue, and it only helps someone
    who thinks to look.

    For the default source the bundle is not optional anyway: an inkdecks report may
    not be published, so the local file is the only way to read it.
    """
    from .bundle import SITE
    from .bundle import build as bundle_build

    index = SITE / "index.html"
    if not index.exists():
        log.warning(
            "no %s, so no single-file report was written. Bundling needs the site "
            "directory from a checkout; the data itself is in %s",
            index,
            data,
        )
        return 0
    return bundle_build(index, data, out)


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

    if args.fmt and getattr(source, "fmt", None):
        log.warning(
            "--format %r ignored: %s names its own format (%r). The flag is for a "
            "source that carries none, such as --source local.",
            args.fmt,
            source.name,
            source.fmt,
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
            # and "all" means the format is per deck rather than one label. `--format`
            # is for a source that carries no format of its own, and it used to be
            # silently ignored by the default source - a flag that looks like it does
            # something and does not.
            "format": getattr(source, "fmt", None) or args.fmt or DEFAULT_FORMAT,
            "top": args.top,
            "min_players": args.min_players,
            "min_pair_decks": args.min_pair_decks,
        },
        generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        built_by=_build_version(),
        cluster_threshold=args.cluster_threshold,
        # Applied inside, before anything is derived from a pair - see build_meta.
        min_pair_decks=args.min_pair_decks,
    )
    report = _lean(report)  # last: every derived number is final by here

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
            "unpublishable: tests/check_report.py will refuse it. The single file "
            "written beside it is the way to read it."
        )
    if not totals["decks"]:
        log.error("no decks in the report - check the window, the format and the source")
        return 1

    if args.bundle:
        code = _bundle(out, Path(args.bundle_out))
        if code:
            return code
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
