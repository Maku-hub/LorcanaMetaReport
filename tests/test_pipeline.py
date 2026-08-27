"""Tests for the parts that can be wrong quietly.

Dependency-free on purpose - `python tests/test_pipeline.py` is the whole story,
and CI runs the same line.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lorcana_meta.analyze import (  # noqa: E402
    Anomalies,
    build_meta,
    derive_inks,
    resolve_deck,
)
from lorcana_meta.cards import CardIndex, normalize_name  # noqa: E402
from lorcana_meta.console import configure_output  # noqa: E402
from lorcana_meta.decklist import (  # noqa: E402
    extract_cards,
    parse_deck_obj,
    parse_decklist_text,
)
from lorcana_meta.models import Card, Deck, DeckCard  # noqa: E402

FAILURES: list[str] = []


def check(condition, message):
    if not condition:
        FAILURES.append(message)


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
        image="",
        set_id="TFC",
        set_name="The First Chapter",
        unique_id=name[:3].upper(),
        rarity="Common",
    )


# ---------------------------------------------------------------- normalisation

def test_normalize():
    check(normalize_name("Elsa - Snow Queen") == "elsa snow queen", "plain hyphen")
    check(normalize_name("Elsa – Snow Queen") == "elsa snow queen", "en dash folds")
    check(normalize_name("Café Life") == "cafe life", "accents fold")
    check(
        normalize_name("Let’s Get Down to Business")
        == normalize_name("Let's Get Down to Business"),
        "curly and straight apostrophes agree",
    )
    check(normalize_name("  MICKEY   MOUSE  ") == "mickey mouse", "case and spacing fold")


# ------------------------------------------------------------- decklist parsing

def test_decklist_text():
    text = """Characters (3)
4 Elsa - Snow Queen
3x Hades - Lord of the Underworld
2 Mickey Mouse - Brave Little Tailor (TFC) 42

Songs (1)
1 Be Prepared #57
Grab Your Sword x2
"""
    cards = {c.name: c.count for c in parse_decklist_text(text)}
    check(cards.get("Elsa - Snow Queen") == 4, f"leading count: {cards}")
    check(cards.get("Hades - Lord of the Underworld") == 3, f"'3x' form: {cards}")
    check(
        cards.get("Mickey Mouse - Brave Little Tailor") == 2,
        f"trailing set annotation stripped: {cards}",
    )
    check(cards.get("Be Prepared") == 1, f"trailing #number stripped: {cards}")
    check(cards.get("Grab Your Sword") == 2, f"trailing xN form: {cards}")
    check(len(cards) == 5, f"headers skipped, got {sorted(cards)}")


def test_decklist_text_rejects_noise():
    cards = parse_decklist_text("Total: 60\n\n99 Nonsense Card\nab\n")
    check(not cards, f"implausible counts and stubs rejected: {cards}")


def test_deck_obj():
    flat = parse_deck_obj({"Mainboard": {"Elsa - Snow Queen": 4}})
    nested = parse_deck_obj({"Mainboard": {"Elsa - Snow Queen": {"count": 4}}})
    check(flat == nested, f"both deckObj shapes agree: {flat} vs {nested}")
    check(flat and flat[0].count == 4, "count read")

    ignored = parse_deck_obj({"Mainboard": {"A Card": 2}, "Sideboard": {"Other": 4}})
    check(
        [c.name for c in ignored] == ["A Card"],
        f"sideboard bucket ignored: {ignored}",
    )


def test_extract_prefers_structured():
    standing = {
        "deckObj": {"Mainboard": {"Elsa - Snow Queen": 4}},
        "decklist": "1 Something Else",
    }
    cards = extract_cards(standing)
    check([c.name for c in cards] == ["Elsa - Snow Queen"], f"deckObj wins: {cards}")
    check(
        [c.name for c in extract_cards({"decklist": "2 Only Text"})] == ["Only Text"],
        "text fallback works",
    )


# ------------------------------------------------------------ ink derivation

def test_derive_inks():
    two = [(card("A", ["amber"]), 4), (card("B", ["steel"]), 4)]
    check(derive_inks(two) == ("amber", "steel"), "two single inks")

    canonical = [(card("A", ["steel"]), 4), (card("B", ["amber"]), 4)]
    check(
        derive_inks(canonical) == ("amber", "steel"),
        "pair order is canonical, not insertion order",
    )

    mono_plus_dual = [(card("A", ["ruby"]), 4), (card("B", ["ruby", "sapphire"]), 2)]
    check(
        derive_inks(mono_plus_dual) == ("ruby", "sapphire"),
        "a dual-ink card supplies the second ink",
    )

    mono = [(card("A", ["emerald"]), 4)]
    check(derive_inks(mono) == ("emerald",), "mono decks keep one ink")

    three = [
        (card("A", ["amber"]), 4),
        (card("B", ["steel"]), 4),
        (card("C", ["ruby"]), 4),
    ]
    check(derive_inks(three) == (), "three inks is not a legal pair")


# --------------------------------------------------------------- resolution

def _index():
    return CardIndex(
        [
            card("Elsa - Snow Queen", ["amber"], cost=4),
            card("Hades - Lord of the Underworld", ["steel"], cost=6),
            card("Be Prepared", ["steel"], cost=7, type_="Action - Song"),
        ]
    )


def test_resolve_reports_unknowns():
    deck = Deck(
        source="test",
        deck_id="1",
        player="P",
        cards=[
            DeckCard("Elsa - Snow Queen", 30),
            DeckCard("Hades - Lord of the Underworld", 25),
            DeckCard("Not A Real Card", 5),
        ],
    )
    anomalies = Anomalies()
    resolved = resolve_deck(deck, _index(), anomalies)
    check(resolved is not None, "deck resolved")
    check(resolved.inks == ("amber", "steel"), f"inks: {resolved.inks}")
    check(
        anomalies.unknown_cards["Not A Real Card"] == 1,
        f"unknown recorded: {anomalies.unknown_cards}",
    )
    check(len(resolved.unknown) == 1, "unknown kept on the deck")


def test_resolve_drops_truncated_lists():
    deck = Deck(
        source="test",
        deck_id="2",
        player="P",
        cards=[DeckCard("Elsa - Snow Queen", 4)],
    )
    anomalies = Anomalies()
    check(resolve_deck(deck, _index(), anomalies) is None, "4-card list dropped")
    check(anomalies.short_decks == 1, "drop counted, not silent")


def test_base_type_collapses_songs():
    check(
        card("X", ["amber"], type_="Action - Song").base_type == "Action",
        "songs group under Action",
    )


# ------------------------------------------------------------------ analysis

def _field(n_amber_steel=6, n_ruby=4):
    """Two archetypes with a known composition, so the maths is checkable by hand."""
    decks = []
    for i in range(n_amber_steel):
        cards = [DeckCard("Elsa - Snow Queen", 30), DeckCard("Hades - Lord of the Underworld", 30)]
        if i < 3:  # half the pair runs the song
            cards[1] = DeckCard("Hades - Lord of the Underworld", 26)
            cards.append(DeckCard("Be Prepared", 4))
        decks.append(
            Deck(
                source="test",
                deck_id=f"as{i}",
                player=f"P{i}",
                cards=cards,
                standing=i + 1,
                wins=5,
                losses=2,
                draws=0,
                tournament_id="T1",
                tournament_name="Test Cup",
                tournament_date="2026-08-01",
            )
        )
    for i in range(n_ruby):
        decks.append(
            Deck(
                source="test",
                deck_id=f"r{i}",
                player=f"Q{i}",
                cards=[DeckCard("Elsa - Snow Queen", 60)],
                standing=i + 1,
                wins=3,
                losses=4,
                draws=0,
                tournament_id="T2",
                tournament_name="Other Cup",
                tournament_date="2026-08-02",
            )
        )
    return decks


def test_build_meta_shares_and_inclusion():
    report = build_meta(
        _field(),
        _index(),
        period={"start": "2026-08-01", "end": "2026-08-31", "days": 31},
        source={"name": "test", "attribution": "test", "attribution_url": ""},
        filters={"format": "Core Constructed", "top": 32},
        generated_at="2026-08-27T00:00:00+00:00",
    )

    check(report["totals"]["decks"] == 10, f"all decks counted: {report['totals']}")
    check(report["totals"]["tournaments"] == 2, "tournaments counted by id")

    pairs = {p["key"]: p for p in report["pairs"]}
    check(set(pairs) == {"amber-steel", "amber"}, f"pairs found: {sorted(pairs)}")
    check(pairs["amber-steel"]["decks"] == 6, "6 two-ink decks")
    check(pairs["amber-steel"]["share"] == 60.0, f"share: {pairs['amber-steel']['share']}")

    cards = {c["name"]: c for c in pairs["amber-steel"]["cards"]}
    check(cards["Elsa - Snow Queen"]["inclusion"] == 100.0, "every list runs Elsa")
    check(
        cards["Be Prepared"]["inclusion"] == 50.0,
        f"half run the song: {cards['Be Prepared']['inclusion']}",
    )
    check(
        cards["Be Prepared"]["avg_copies"] == 4.0,
        "4 copies in the lists that run it",
    )
    check(
        cards["Be Prepared"]["avg_copies_overall"] == 2.0,
        "2 copies averaged over the whole pair",
    )
    check(cards["Be Prepared"]["tier"] == "flex", "50% is flex, not core")
    check(cards["Elsa - Snow Queen"]["tier"] == "core", "100% is core")

    ink = {row["ink"]: row for row in report["inks"]}
    check(ink["amber"]["decks"] == 10, "amber is in every deck")
    check(ink["steel"]["decks"] == 6, "steel only in the two-ink decks")

    record = pairs["amber-steel"]["record"]
    check(record["wins"] == 30 and record["losses"] == 12, f"record summed: {record}")
    check(record["win_rate"] == 71.4, f"win rate: {record['win_rate']}")


def test_expected_copies_weights_by_pair_share():
    report = build_meta(
        _field(),
        _index(),
        period={"start": "2026-08-01", "end": "2026-08-31", "days": 31},
        source={"name": "test", "attribution": "test", "attribution_url": ""},
        filters={"format": "Core Constructed", "top": 32},
        generated_at="2026-08-27T00:00:00+00:00",
    )
    threats = {t["name"]: t for t in report["threats"]}

    # Be Prepared: only the 60%-of-field pair plays it, 2.0 copies per deck there.
    check(
        threats["Be Prepared"]["expected_copies"] == 1.2,
        f"0.60 * 2.0 = 1.2, got {threats['Be Prepared']['expected_copies']}",
    )
    # ...and half of that pair's lists run it, so 60% * 50% of the field meets it.
    check(
        threats["Be Prepared"]["field_presence"] == 30.0,
        f"presence: {threats['Be Prepared']['field_presence']}",
    )
    check(
        threats["Elsa - Snow Queen"]["field_presence"] == 100.0,
        "every deck in the field runs Elsa",
    )
    check(
        list(threats)[0] == "Elsa - Snow Queen",
        f"threats ranked by expected copies, got {list(threats)[:2]}",
    )


def test_empty_field_does_not_explode():
    report = build_meta(
        [],
        _index(),
        period={"start": "2026-08-01", "end": "2026-08-31", "days": 31},
        source={"name": "test", "attribution": "test", "attribution_url": ""},
        filters={"format": "Core Constructed", "top": 32},
        generated_at="2026-08-27T00:00:00+00:00",
    )
    check(report["totals"]["decks"] == 0, "zero decks reported as zero")
    check(report["pairs"] == [], "no pairs")
    check(all(row["share"] == 0.0 for row in report["inks"]), "no division by zero")


# --------------------------------------------------------- copy distribution

def _copies_field(n_by_copies: dict):
    """A field where `n` decks run exactly `copies` of one card, plus filler."""
    decks = []
    for copies, how_many in n_by_copies.items():
        for i in range(how_many):
            decks.append(
                Deck(
                    source="test",
                    deck_id=f"c{copies}-{i}",
                    player="P",
                    cards=[
                        DeckCard("Be Prepared", copies),
                        DeckCard("Elsa - Snow Queen", 60 - copies),
                    ],
                    standing=1,
                    tournament_id="T",
                    tournament_name="Cup",
                    tournament_date="2026-08-01",
                )
            )
    return decks


def _stats_for(n_by_copies: dict, name="Be Prepared"):
    report = build_meta(
        _copies_field(n_by_copies),
        _index(),
        period={"start": "2026-08-01", "end": "2026-08-31", "days": 31},
        source={"name": "test", "attribution": "test", "attribution_url": ""},
        filters={"format": "Core Constructed", "top": 32},
        generated_at="2026-08-27T00:00:00+00:00",
        cluster_threshold=0.0,  # one archetype, so the spread is over the whole field
    )
    pair = report["pairs"][0]
    return next(c for c in pair["cards"] if c["name"] == name)


def test_copies_spread_records_the_shape():
    stats = _stats_for({4: 38, 3: 5, 2: 1, 1: 1})
    check(
        stats["copies_spread"] == {"1": 1, "2": 1, "3": 5, "4": 38},
        f"one bin per deck: {stats['copies_spread']}",
    )
    check(stats["decks"] == 45, f"45 decks play it: {stats['decks']}")


def test_typical_copies_is_the_mode_not_the_mean():
    """The case that motivated this: a mean of 2.4 where the answer is 2.

    Real data, one archetype of 45 lists: Ursula - Whisper of Vanessa averaged 2.40
    copies, and 28 of the 43 lists running her ran exactly 2. Reporting 2.4 invites
    "so, 2 or 3?" when the field has already answered.
    """
    stats = _stats_for({1: 2, 2: 28, 3: 7, 4: 6})
    check(stats["avg_copies"] == 2.4, f"the mean is still reported: {stats['avg_copies']}")
    check(stats["typical_copies"] == 2, f"the mode is 2, got {stats['typical_copies']}")


def test_a_genuinely_split_archetype_is_visible():
    """Half the lists on 4, half on 1 - the mean says 2.5, which nobody plays."""
    stats = _stats_for({4: 10, 1: 10})
    check(stats["avg_copies"] == 2.5, f"mean: {stats['avg_copies']}")
    check(
        stats["copies_spread"] == {"1": 10, "4": 10},
        f"the split is in the data rather than averaged away: {stats['copies_spread']}",
    )
    check(
        stats["typical_copies"] == 4,
        f"a tie prepares for the worse case, got {stats['typical_copies']}",
    )


def test_one_card_on_two_lines_counts_as_one_deck():
    """A paste split by section can list the same card twice.

    Counted per line, that deck would land in two bins of the distribution and be
    counted as two decks for inclusion - quietly inflating both.
    """
    decks = [
        Deck(
            source="test",
            deck_id="split",
            player="P",
            cards=[
                DeckCard("Be Prepared", 2),
                DeckCard("Be Prepared", 2),  # same card, second line
                DeckCard("Elsa - Snow Queen", 56),
            ],
            standing=1,
            tournament_id="T",
            tournament_name="Cup",
            tournament_date="2026-08-01",
        )
    ]
    report = build_meta(
        decks,
        _index(),
        period={"start": "2026-08-01", "end": "2026-08-31", "days": 31},
        source={"name": "test", "attribution": "test", "attribution_url": ""},
        filters={"format": "Core Constructed", "top": 32},
        generated_at="2026-08-27T00:00:00+00:00",
    )
    stats = next(
        c for c in report["pairs"][0]["cards"] if c["name"] == "Be Prepared"
    )
    check(stats["decks"] == 1, f"one deck, not two: {stats['decks']}")
    check(stats["copies_spread"] == {"4": 1}, f"2+2 is one 4-of: {stats['copies_spread']}")
    check(stats["typical_copies"] == 4, f"and the mode follows: {stats['typical_copies']}")


def main() -> int:
    configure_output()
    tests = [value for name, value in sorted(globals().items()) if name.startswith("test_")]
    for test in tests:
        try:
            test()
        except Exception as error:  # a raising test is a failing test
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
