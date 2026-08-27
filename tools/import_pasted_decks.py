"""Turn a batch of hand-copied decklists into deck files the pipeline can read.

Why this exists: some sites publish tournament decklists but prohibit automated
access in their terms of use. Copying a list you are looking at, by hand, is not
automated access - but doing it one file at a time is miserable. This takes one file
holding many decks and writes a single JSON the ``local`` source reads.

**Check the terms of any site you copy from, and don't point a scraper at one that
says no.** This tool deliberately fetches nothing; it only reformats text you already
have.

## Input format

Each deck starts with a ``###`` line of pipe-separated fields, then its card list:

    ### deck name | player | standing | event | date | players

Every field after the deck name may be left empty or dropped entirely:

    ### Yurple | Tom G. | 20 | The Dice Cellar Quest | 2026-08-22 | 57
    4 Eilonwy - Princess of Llyr
    3 Rafiki - Mystical Fighter
    ...

    ### Samber |  | 3 | Store Championship | 2026-08-19 |
    4 Beast - Selfless Protector
    ...

Card lines take any of the usual shapes (``4 Card``, ``4x Card``, ``Card x4``, with
trailing set codes or collector numbers). Section headers like ``characters (47)``
are skipped, so a whole page paste usually works unedited.

## Usage

    python tools/import_pasted_decks.py my-notes.txt
    python tools/import_pasted_decks.py my-notes.txt --out data/decks/regionals.json
    python tools/import_pasted_decks.py my-notes.txt --dry-run

Then build as usual:

    lorcana-meta build --source local --last 60
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lorcana_meta.cards import CardIndex  # noqa: E402
from lorcana_meta.console import configure_output  # noqa: E402
from lorcana_meta.decklist import parse_decklist_text  # noqa: E402

HEADER = re.compile(r"^\s*#{3,}\s*(.*)$")
FIELDS = ("deck_name", "player", "standing", "tournament_name", "tournament_date", "players")


def split_decks(text: str) -> list[tuple[dict, str]]:
    """Cut the input into (header fields, card list) pairs."""
    decks: list[tuple[dict, str]] = []
    meta: dict | None = None
    body: list[str] = []

    for line in text.splitlines():
        match = HEADER.match(line)
        if match:
            if meta is not None:
                decks.append((meta, "\n".join(body)))
            meta, body = parse_header(match.group(1)), []
        elif meta is not None:
            body.append(line)

    if meta is not None:
        decks.append((meta, "\n".join(body)))
    return decks


def parse_header(raw: str) -> dict:
    parts = [p.strip() for p in raw.split("|")]
    meta = {name: (parts[i] if i < len(parts) else "") for i, name in enumerate(FIELDS)}

    for key in ("standing", "players"):
        try:
            meta[key] = int(meta[key])
        except (TypeError, ValueError):
            meta[key] = None
    return meta


def build_entry(meta: dict, cards, index: CardIndex) -> tuple[dict, list[str]]:
    unknown = [card.name for card in cards if index.get(card.name) is None]
    entry = {
        "player": meta.get("player") or "Unknown",
        "deck_name": meta.get("deck_name") or "",
        "standing": meta.get("standing"),
        "tournament_name": meta.get("tournament_name") or "Imported event",
        "tournament_date": meta.get("tournament_date") or "",
        "tournament_players": meta.get("players"),
        "format": "Core Constructed",
        "source_note": "hand-copied decklist",
        "cards": [{"name": card.name, "count": card.count} for card in cards],
    }
    return entry, unknown


def main(argv: list[str] | None = None) -> int:
    configure_output()
    parser = argparse.ArgumentParser(
        description="Convert a file of hand-copied decklists into a local deck file.",
        epilog="Only reformats text you already have - it never fetches anything.",
    )
    parser.add_argument("input", help="text file holding one or more decks")
    parser.add_argument(
        "--out",
        default="data/decks/imported.json",
        help="where to write the decks (default: data/decks/imported.json)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="report what would be imported without writing anything",
    )
    args = parser.parse_args(argv)

    text = Path(args.input).read_text(encoding="utf-8")
    blocks = split_decks(text)
    if not blocks:
        print(
            f"No '###' header lines found in {args.input}.\n"
            "Each deck needs a line like:\n"
            "  ### deck name | player | standing | event | date | players",
            file=sys.stderr,
        )
        return 1

    index = CardIndex.load()
    entries, problems = [], []

    for position, (meta, body) in enumerate(blocks, start=1):
        cards = parse_decklist_text(body)
        total = sum(card.count for card in cards)
        label = meta.get("deck_name") or f"deck {position}"

        if total < 40:
            problems.append(f"{label}: only {total} cards read - the paste looks truncated")
            continue

        entry, unknown = build_entry(meta, cards, index)
        entries.append(entry)
        print(f"  {label}: {total} cards, {len(cards)} distinct", end="")
        if unknown:
            print(f" - {len(unknown)} unmatched: {', '.join(unknown[:3])}")
        else:
            print()

    for problem in problems:
        print(f"  skipped {problem}", file=sys.stderr)

    if not entries:
        print("Nothing to import.", file=sys.stderr)
        return 1

    if args.dry_run:
        print(f"\nDry run: {len(entries)} deck(s) would go to {args.out}")
        return 0

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(entries, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nWrote {len(entries)} deck(s) to {out}")
    print("Build with:  lorcana-meta build --source local --last 60")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
