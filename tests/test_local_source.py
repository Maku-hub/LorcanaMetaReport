"""Tests for reading decklists off disk, and for the paste importer.

The one that matters most is `test_refuses_importer_input`. Reading a multi-deck
paste as a single deck does not raise anything - it just produces one 200-card
"deck" with nonsense card ratios that counts once instead of N times. That is a
quiet, plausible-looking way to skew a whole report, so it gets a test.
"""

from __future__ import annotations

import json
import sys
import tempfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

from lorcana_meta.console import configure_output  # noqa: E402
from lorcana_meta.sources import LocalSource  # noqa: E402

from import_pasted_decks import parse_header, split_decks  # noqa: E402

FAILURES: list[str] = []

def _deck_text(prefix: str, distinct: int = 15) -> str:
    """A realistic 60-card list: `distinct` names at 4 copies each.

    Counts have to be plausible - the parser rejects anything over 20 copies,
    because a Lorcana deck holds at most 4 of a card and a bigger number means the
    line was misread. Names avoid trailing digits, which the parser strips as
    collector numbers.
    """
    words = [
        "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight",
        "Nine", "Ten", "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen",
    ]
    return "\n".join(f"4 {prefix} - {word}" for word in words[:distinct])


DECK_A = _deck_text("Alpha")
DECK_B = _deck_text("Beta")


def check(condition, message):
    if not condition:
        FAILURES.append(message)


def write(root: Path, name: str, text: str) -> None:
    (root / name).write_text(text, encoding="utf-8")


# ------------------------------------------------------------- local source

def test_reads_txt_and_json():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        write(
            root,
            "one.txt",
            "\n".join(
                [
                    "player: Ada",
                    "deck_name: Yurple",
                    "standing: 3",
                    "tournament_date: 2026-08-12",
                    "",
                    DECK_A,
                ]
            ),
        )
        write(
            root,
            "two.json",
            json.dumps(
                [
                    {
                        "player": "Bob",
                        "deck_name": "Samber",
                        "tournament_date": "2026-08-13",
                        "cards": [{"name": f"Beta - {w}", "count": 4} for w in ("One", "Two")],
                    }
                ]
            ),
        )

        decks = LocalSource(root).fetch(date(2026, 8, 1), date(2026, 8, 31))
        by_name = {d.deck_name: d for d in decks}
        check(set(by_name) == {"Yurple", "Samber"}, f"both files read: {sorted(by_name)}")
        check(by_name["Yurple"].standing == 3, "header integers parsed")
        check(by_name["Yurple"].total_cards == 60, "card counts read")
        check(by_name["Samber"].player == "Bob", "json fields read")


def test_refuses_importer_input():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        write(
            root,
            "notes.txt",
            "\n".join(
                [
                    "### Yurple | Ada | 3 | Cup | 2026-08-12 | 40",
                    DECK_A,
                    "",
                    "### Samber | Bob | 5 | Cup | 2026-08-12 | 40",
                    DECK_B,
                ]
            ),
        )
        decks = LocalSource(root).fetch(date(2026, 8, 1), date(2026, 8, 31))
        check(decks == [], f"importer input skipped, got {len(decks)} deck(s)")


def test_window_filter():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        for day in ("2026-07-01", "2026-08-15"):
            write(root, f"{day}.txt", f"tournament_date: {day}\n\n{DECK_B}")

        decks = LocalSource(root).fetch(date(2026, 8, 1), date(2026, 8, 31))
        check(len(decks) == 1, f"only the in-window deck kept, got {len(decks)}")
        check(decks and decks[0].tournament_date == "2026-08-15", "kept the right one")


def test_undated_notes_are_always_in_scope():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        write(root, "undated.txt", f"player: Ada\n\n{DECK_B}")
        decks = LocalSource(root).fetch(date(2026, 8, 1), date(2026, 8, 31))
        check(len(decks) == 1, "a deck with no date is not filtered out")


def test_readme_is_not_read_as_a_deck():
    """`data/decks/README.md` lives beside the decks and must be ignored."""
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        write(root, "README.md", f"# notes\n\n{DECK_B}")
        write(root, "real.txt", f"tournament_date: 2026-08-15\n\n{DECK_B}")
        decks = LocalSource(root).fetch(date(2026, 8, 1), date(2026, 8, 31))
        check(len(decks) == 1, f"only the .txt read, got {len(decks)}")


# ---------------------------------------------------------------- importer

def test_split_decks():
    text = "\n".join(
        [
            "### Yurple | Tom G. | 20 | The Dice Cellar Quest | 2026-08-22 | 57",
            "characters (40)",
            DECK_A,
            "",
            "### Samber |  | 3 | Store Championship | 2026-08-19 |",
            DECK_B,
        ]
    )
    blocks = split_decks(text)
    check(len(blocks) == 2, f"two decks found, got {len(blocks)}")

    first, second = blocks
    check(first[0]["deck_name"] == "Yurple", f"name parsed: {first[0]}")
    check(first[0]["player"] == "Tom G.", "player parsed")
    check(first[0]["standing"] == 20, "standing parsed as an int")
    check(first[0]["players"] == 57, "attendance parsed as an int")
    check("Alpha - One" in first[1], "card list captured")
    check(second[0]["player"] == "", "an empty field stays empty")
    check(second[0]["players"] is None, "a missing number is None, not 0")


def test_header_tolerates_missing_fields():
    meta = parse_header("Just A Name")
    check(meta["deck_name"] == "Just A Name", f"name only: {meta}")
    check(meta["standing"] is None, "no standing")
    check(meta["tournament_name"] == "", "no event name")


def test_text_before_the_first_header_is_ignored():
    blocks = split_decks("copied from a browser tab\nsome junk\n\n### Real | | | | |\n" + DECK_B)
    check(len(blocks) == 1, f"one deck, got {len(blocks)}")
    check(blocks[0][0]["deck_name"] == "Real", "the header after the junk is used")


def main() -> int:
    configure_output()
    tests = [value for name, value in sorted(globals().items()) if name.startswith("test_")]
    for test in tests:
        try:
            test()
        except Exception as error:
            FAILURES.append(f"{test.__name__} raised {error!r}")

    if FAILURES:
        print(f"{len(FAILURES)} failure(s):")
        for failure in FAILURES:
            print(f"  - {failure}")
        return 1
    print(f"{len(tests)} tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
