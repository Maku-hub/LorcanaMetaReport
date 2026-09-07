"""Tests that the report and the page it feeds agree on their shape.

Two failures are silent, and this file is here to make both loud.

A key the site reads but the build stops emitting renders as "undefined" or a blank
cell - no error, no console warning, just a wrong-looking number that nobody can
explain. A key the build emits but nothing reads is the opposite problem: dead weight
in a file that is shipped whole to the browser and inlined into `report.html`. On real
data, working fields nothing read were 37% of the report.

So: every key in a built report must have a reader somewhere, and everything `_lean`
strips must have no reader at all. Anything genuinely written for a consumer other
than the page is listed in `READ_ELSEWHERE`, with the consumer named - the point is
that the exceptions are enumerated, not that there are none.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lorcana_meta.analyze import build_meta  # noqa: E402
from lorcana_meta.cards import CardIndex  # noqa: E402
from lorcana_meta.cli import _INTERNAL_FIELDS, _lean  # noqa: E402
from lorcana_meta.console import configure_output  # noqa: E402
from lorcana_meta.models import Card, Deck, DeckCard  # noqa: E402

FAILURES: list[str] = []

APP_JS = ROOT / "site" / "assets" / "app.js"

# Fields whose reader is deliberately not the page. Keyed by full path, not by name:
# keying by name would have exempted `pairs[].variants` along with `totals.variants`,
# and a blanket exemption is how a real gap hides behind a legitimate one. Each entry
# names what does read it - an unexplained exception is indistinguishable from a field
# nobody wants.
READ_ELSEWHERE = {
    ".source.publishable": "tests/check_report.py - the gate that keeps private data private",
    ".anomalies.unknown_cards": "cli.py logs the first few; check_report.py names them",
    ".anomalies.unknown_cards[].count": "part of the unknown_cards entries above",
    ".totals.variants": "tests/check_report.py - 'no archetypes' plus the summary line",
}

# Maps whose keys are values, not field names: the card index is keyed by card name,
# a copy spread by the number of copies. Their keys are data and change with the field.
DATA_KEYED = {"cards", "copies_spread"}


def check(condition, message):
    if not condition:
        FAILURES.append(message)


def _index() -> CardIndex:
    def card(name, inks, cost=3, type_="Character"):
        return Card(
            name=name,
            inks=tuple(inks),
            cost=cost,
            type=type_,
            inkable=True,
            lore=1,
            strength=2,
            willpower=3,
            text="",
            image=f"https://example.invalid/{name}.png",
            set_id="TFC",
            rarity="Common",
        )

    return CardIndex(
        [
            card("Elsa - Snow Queen", ["amber"], cost=4),
            card("Hades - Lord of the Underworld", ["steel"], cost=6),
            card("Be Prepared", ["steel"], cost=7, type_="Action - Song"),
            card("Mickey Mouse - Brave Little Tailor", ["ruby"], cost=8),
            card("Dragon Fire", ["ruby"], cost=5, type_="Action"),
        ]
    )


def _field() -> list[Deck]:
    """An archetype with several near-identical lists, plus a genuine one-off brew.

    Both branches have to be present or the test only covers half the shape: the brew
    is what makes `cards` and `cost_curve` come back empty.
    """
    decks = []
    for i in range(6):
        decks.append(
            Deck(
                source="test",
                deck_id=f"as{i}",
                player=f"P{i}",
                cards=[
                    DeckCard("Elsa - Snow Queen", 30),
                    DeckCard("Hades - Lord of the Underworld", 26),
                    DeckCard("Be Prepared", 4),
                ],
                standing=i + 1,
                wins=5,
                losses=2,
                draws=0,
                tournament_id="T1",
                tournament_name="Test Cup",
                tournament_date="2026-08-01",
                tournament_players=64,
                deck_name="Amber Steel Songs",
            )
        )
    # Same inks, nothing else in common - one deck, so a brew.
    decks.append(
        Deck(
            source="test",
            deck_id="brew",
            player="Brewer",
            cards=[
                DeckCard("Mickey Mouse - Brave Little Tailor", 4),
                DeckCard("Dragon Fire", 56),
            ],
            standing=7,
            wins=4,
            losses=3,
            draws=0,
            tournament_id="T1",
            tournament_name="Test Cup",
            tournament_date="2026-08-01",
            tournament_players=64,
            deck_name="Big Red Nonsense",
        )
    )
    return decks


def _report() -> dict:
    report = build_meta(
        _field(),
        _index(),
        period={"start": "2026-08-01", "end": "2026-08-14", "days": 14},
        source={
            "name": "test",
            "attribution": "test",
            "attribution_url": "",
            "publishable": False,
            "card_db": {"name": "db", "url": "https://example.invalid"},
        },
        filters={"format": "Core Constructed", "top": 32, "min_players": 32},
        generated_at="2026-09-07T00:00:00+00:00",
    )
    report["totals"]["decks_fetched"] = len(_field())
    return _lean(report)


def _paths(report: dict) -> list[str]:
    """Every distinct field path in the report.

    Every path, not one per key name: `decks` lives at `totals.decks`,
    `pairs[].decks`, `inks[].decks` and `trend.first.decks`, and each of those is a
    separate promise to the page. Recording one path per name made the result depend
    on dictionary ordering - whichever occurrence happened to be walked first was the
    only one checked.
    """
    found: set[str] = set()

    def walk(node, path):
        if isinstance(node, dict):
            keyed_by_data = path.rsplit(".", 1)[-1] in DATA_KEYED
            for key, value in node.items():
                if not keyed_by_data:
                    found.add(f"{path}.{key}")
                walk(value, path if keyed_by_data else f"{path}.{key}")
        elif isinstance(node, list):
            for value in node[:3]:  # shapes repeat; three is enough to see them all
                walk(value, f"{path}[]")

    walk(report, "")
    return sorted(found)


def _readable_js() -> str:
    """`app.js` with the places that only *write* a field taken out.

    `withDefaults()` fills in blocks an older report does not carry, so it mentions
    every key it defaults - which made a key with no reader anywhere look read. That
    is the exact false assurance this file exists to prevent, so its body does not
    count as a reader.
    """
    js = APP_JS.read_text(encoding="utf-8")
    start = js.find("function withDefaults(")
    if start == -1:
        return js
    end = js.find("\n}", start)
    return js[:start] + js[end:]


def _reads(js: str, key: str) -> bool:
    return re.search(rf"\b{re.escape(key)}\b", js) is not None


def _reads_path(js: str, path: str) -> bool:
    """Does `app.js` read this exact field, rather than something of the same name?

    Matching the bare key name is too loose, and it let a real gap through:
    `totals.variants` has no reader in the page at all, but `pair.variants` does, so
    the name matched and the field was approved by coincidence. A test that approves
    by coincidence is the same false assurance as one that counts a writer.

    So where the parent is a plain object key, require the dotted access -
    `totals.variants`, not `variants`. Where the parent is a list element
    (`pairs[].variants`) the chain is broken by the indexing and cannot be matched
    statically without parsing the JavaScript, so those fall back to the name.
    """
    segments = [s for s in path.split(".") if s]
    if len(segments) < 2 or segments[-2].endswith("[]"):
        return _reads(js, segments[-1])
    parent, key = segments[-2], segments[-1]
    return (
        re.search(rf"\b{re.escape(parent)}\??\.{re.escape(key)}\b", js) is not None
        or re.search(rf"\b{re.escape(parent)}\[[\"']{re.escape(key)}[\"']\]", js) is not None
    )


def test_every_report_key_has_a_reader():
    js = _readable_js()
    for path in _paths(_report()):
        if path in READ_ELSEWHERE or _reads_path(js, path):
            continue
        FAILURES.append(
            f"nothing reads {path} - give it a reader in app.js, add it to "
            f"READ_ELSEWHERE with its consumer, or stop emitting it"
        )


def test_stripped_fields_have_no_reader():
    js = _readable_js()
    for group, keys in _INTERNAL_FIELDS.items():
        for key in keys:
            check(
                not _reads(js, key),
                f"app.js reads {key!r}, but _lean strips it ({group}) - the page would "
                f"show undefined",
            )


def test_stripped_fields_are_actually_gone():
    report = _report()
    pair = report["pairs"][0]
    for row in pair["cards"]:
        for key in _INTERNAL_FIELDS["card_row"]:
            check(key not in row, f"{key} survived _lean on a pair card row")
    for variant in pair["variants"]:
        for entry in variant["signature"]:
            for key in _INTERNAL_FIELDS["signature"]:
                check(key not in entry, f"{key} survived _lean on a signature card")
    for card in report["cards"].values():
        for key in _INTERNAL_FIELDS["card"]:
            check(key not in card, f"{key} survived _lean on a card description")


def test_brews_keep_their_identity_but_carry_no_card_table():
    report = _report()
    variants = [v for pair in report["pairs"] for v in pair["variants"]]
    brews = [v for v in variants if v["is_brew"]]
    real = [v for v in variants if not v["is_brew"]]

    check(len(brews) == 1, f"the one-off list is a brew: {[v['label'] for v in brews]}")
    check(len(real) == 1, f"the six-deck archetype is not: {[v['label'] for v in real]}")

    for brew in brews:
        check(brew["cards"] == [], "a brew carries no card table")
        check(brew["cost_curve"] == [], "a brew carries no cost curve")
        # What makes the brew worth showing at all has to survive.
        check(bool(brew["label"]), "a brew keeps its label")
        check(brew["decks"] >= 1, "a brew keeps its deck count")
        check("share_of_field" in brew, "a brew keeps its share")
        check(bool(brew["signature"]), "a brew keeps its tells")
        check(bool(brew["named_by_players"]), "a brew keeps the names players gave it")

    for archetype in real:
        check(bool(archetype["cards"]), "a real archetype still has its card table")
        check(bool(archetype["cost_curve"]), "a real archetype still has its curve")


def test_the_page_guards_the_empty_brew_fields():
    """The three places that would render a blank card or a wrong number for a brew."""
    js = APP_JS.read_text(encoding="utf-8")
    check("!scope.cards.length" in js, "the card table is suppressed for an empty list")
    check(
        "(scope.cost_curve || []).length" in js,
        "the curve section is suppressed for an empty curve",
    )
    check(
        'scope.cards.length ? "Distinct cards played"' in js,
        "the distinct-cards tile does not claim 0 cards for a brew",
    )


def test_card_descriptions_cover_every_card_the_report_names():
    """A named card with no description renders a broken image and an empty tooltip."""
    report = _report()
    described = set(report["cards"])
    named: set[str] = {threat["name"] for threat in report["threats"]}
    for pair in report["pairs"]:
        named |= {row["name"] for row in pair["cards"]}
        for variant in pair["variants"]:
            named |= {row["name"] for row in variant["cards"]}
            named |= {entry["name"] for entry in variant["signature"]}

    missing = sorted(named - described)
    check(not missing, f"named but not described: {missing}")
    check(
        report["totals"]["cards_described"] == len(described),
        f"the count matches what shipped: {report['totals']['cards_described']} vs "
        f"{len(described)}",
    )


def main() -> int:
    configure_output()
    if not APP_JS.exists():
        print(f"{APP_JS} is missing", file=sys.stderr)
        return 1

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
