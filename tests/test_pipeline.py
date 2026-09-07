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
from lorcana_meta.decklist import parse_decklist_text  # noqa: E402
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


def test_expected_copies_is_the_field_mean_however_it_is_grouped():
    """Copies per deck drawn at random from the field.

    It used to be assembled as a weighted sum over ink pairs and now comes straight
    off the field. The numbers must be identical - pairs partition the field, so the
    weights always collapsed to "copies in the field over decks in the field" - and
    these assertions are unchanged from when the weighted version wrote them.
    """
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


# ------------------------------------------------------------ the event filters

def test_min_players_drops_small_events_and_keeps_unknown_ones():
    """A twelve-person Friday is a different game from a 200-player regional.

    Decks whose event size is unknown are kept, on the same principle as the placing
    cut: we do not silently discard data we cannot judge.
    """
    from lorcana_meta.cli import _apply_min_players

    decks = [
        Deck(source="t", deck_id="big", player="P", tournament_players=200),
        Deck(source="t", deck_id="edge", player="P", tournament_players=32),
        Deck(source="t", deck_id="small", player="P", tournament_players=12),
        Deck(source="t", deck_id="unknown", player="P", tournament_players=None),
    ]
    kept = [d.deck_id for d in _apply_min_players(decks, 32)]
    check(kept == ["big", "edge", "unknown"], f"32 and up, plus unknown: {kept}")

    check(
        len(_apply_min_players(decks, None)) == 4,
        "no minimum means no filtering",
    )
    check(len(_apply_min_players(decks, 0)) == 4, "zero means no filtering")


def test_top_cut_keeps_decks_with_no_recorded_placing():
    from lorcana_meta.cli import _apply_top_cut

    decks = [
        Deck(source="t", deck_id="won", player="P", standing=1),
        Deck(source="t", deck_id="deep", player="P", standing=40),
        Deck(source="t", deck_id="unplaced", player="P", standing=None),
    ]
    kept = [d.deck_id for d in _apply_top_cut(decks, 32)]
    check(kept == ["won", "unplaced"], f"the 40th is cut, the unknown is kept: {kept}")
    check(len(_apply_top_cut(decks, 0)) == 3, "top 0 keeps everything")


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


# ------------------------------------------------------- movement in the window

def _dated_field(dates: list[str], pair="amber-steel"):
    """One deck per date, all in the same ink pair, so only the dates vary."""
    cards = (
        [DeckCard("Elsa - Snow Queen", 30), DeckCard("Hades - Lord of the Underworld", 30)]
        if pair == "amber-steel"
        else [DeckCard("Elsa - Snow Queen", 60)]
    )
    return [
        Deck(
            source="test",
            deck_id=f"{pair}-{i}",
            player=f"P{i}",
            cards=list(cards),
            standing=1,
            wins=4,
            losses=2,
            draws=0,
            tournament_id=f"T{i}",
            tournament_name="Cup",
            tournament_date=date,
        )
        for i, date in enumerate(dates)
    ]


def _built(decks, start="2026-08-01", end="2026-08-14", min_pair_decks=1):
    days = (
        __import__("datetime").date.fromisoformat(end)
        - __import__("datetime").date.fromisoformat(start)
    ).days + 1
    return build_meta(
        decks,
        _index(),
        period={"start": start, "end": end, "days": days},
        source={"name": "test", "attribution": "test", "attribution_url": ""},
        filters={"format": "Core Constructed", "top": 32},
        generated_at="2026-08-27T00:00:00+00:00",
        min_pair_decks=min_pair_decks,
    )


def test_the_window_splits_in_the_middle_by_date():
    """A 14-day window splits on day 8, so each half is a week.

    Not by deck count: halves of equal length are what "the second week" means, and
    balancing on decks would let a quiet weekend move the boundary instead of showing
    up as a thin half.
    """
    report = _built(_dated_field(["2026-08-01"] * 20 + ["2026-08-08"] * 20))
    trend = report["trend"]
    check(trend["split"] == "2026-08-08", f"split date: {trend['split']}")
    check(trend["first"] == {"start": "2026-08-01", "end": "2026-08-07", "decks": 20},
          f"first half: {trend['first']}")
    check(trend["second"] == {"start": "2026-08-08", "end": "2026-08-14", "decks": 20},
          f"second half: {trend['second']}")
    check(trend["usable"], f"40 decks split evenly is usable: {trend['reason']}")


def test_the_split_boundary_belongs_to_the_second_half():
    """A deck dated exactly on the split must land on one side, not both or neither."""
    report = _built(_dated_field(["2026-08-07"] * 16 + ["2026-08-08"] * 16))
    check(report["trend"]["first"]["decks"] == 16, "the 7th is the first half")
    check(report["trend"]["second"]["decks"] == 16, "the 8th is the second half")
    check(
        report["trend"]["first"]["decks"] + report["trend"]["second"]["decks"]
        == report["totals"]["decks"],
        "every dated deck is counted once",
    )


def test_a_thin_half_refuses_to_show_movement_and_says_why():
    """Silence would read as "nothing moved". It has to read as "we cannot tell"."""
    report = _built(_dated_field(["2026-08-01"] * 30 + ["2026-08-10"] * 2))
    trend = report["trend"]
    check(not trend["usable"], "two decks in a half is not a trend")
    check("2 deck(s)" in (trend["reason"] or ""), f"the reason names the number: {trend['reason']}")
    check(
        all(pair["trend"] is None for pair in report["pairs"]),
        "and no row carries a delta the report has said is unavailable",
    )


def test_a_window_too_short_to_halve_says_so():
    report = _built(_dated_field(["2026-08-01"] * 40), start="2026-08-01", end="2026-08-03")
    check(not report["trend"]["usable"], "a 3-day window has no two halves")
    check("too short" in (report["trend"]["reason"] or ""), report["trend"]["reason"])


def test_shares_are_of_their_own_half_and_the_delta_is_their_difference():
    """The delta on screen must equal the two numbers printed beside it.

    Subtracting the raw shares and rounding afterwards can leave the displayed
    arithmetic off by a tenth, which reads as a bug to anyone who checks it.
    """
    decks = _dated_field(["2026-08-01"] * 15 + ["2026-08-10"] * 5)
    decks += _dated_field(["2026-08-01"] * 5 + ["2026-08-10"] * 15, pair="amber")
    report = _built(decks)
    check(report["trend"]["usable"], f"20 a side: {report['trend']['reason']}")

    by_key = {pair["key"]: pair for pair in report["pairs"]}
    two_ink = by_key["amber-steel"]["trend"]
    check(two_ink["first_share"] == 75.0, f"15 of 20 in the first half: {two_ink}")
    check(two_ink["second_share"] == 25.0, f"5 of 20 in the second: {two_ink}")
    check(two_ink["delta"] == -50.0, f"and the delta is the difference: {two_ink['delta']}")
    check(
        round(two_ink["second_share"] - two_ink["first_share"], 1) == two_ink["delta"],
        "the printed arithmetic checks out",
    )

    mono = by_key["amber"]["trend"]
    check(mono["delta"] == 50.0, f"the other side moved the other way: {mono['delta']}")


def test_a_row_with_too_few_decks_gets_no_delta_of_its_own():
    """A pair seen 3 times can swing 20 points on one deck. That is not movement."""
    decks = _dated_field(["2026-08-01"] * 15 + ["2026-08-10"] * 15)
    decks += _dated_field(["2026-08-01", "2026-08-10", "2026-08-11"], pair="amber")
    report = _built(decks)
    by_key = {pair["key"]: pair for pair in report["pairs"]}
    check(report["trend"]["usable"], "the window itself splits fine")
    check(by_key["amber-steel"]["trend"] is not None, "30 decks gets a delta")
    check(by_key["amber"]["trend"] is None, "3 decks does not")


def test_undated_decks_are_counted_rather_than_dropped_quietly():
    decks = _dated_field(["2026-08-01"] * 15 + ["2026-08-10"] * 15)
    undated = _dated_field(["2026-08-01"] * 2)
    for deck in undated:
        deck.tournament_date = None
    report = _built(decks + undated)
    trend = report["trend"]
    check(trend["undated_decks"] == 2, f"the two are counted: {trend['undated_decks']}")
    check(
        trend["first"]["decks"] + trend["second"]["decks"] + trend["undated_decks"]
        == report["totals"]["decks"],
        "and nothing is lost between the halves",
    )


def test_archetype_movement_uses_one_clustering_over_the_whole_window():
    """Clustering per half would leave us matching archetypes across halves.

    That is the problem card overlap exists to avoid, so the clusters are built once
    over the full window and their members merely counted per half.
    """
    decks = _dated_field(["2026-08-01"] * 15 + ["2026-08-10"] * 15)
    report = _built(decks)
    variants = [v for pair in report["pairs"] for v in pair["variants"]]
    check(len(variants) == 1, f"one archetype over the window: {len(variants)}")
    trend = variants[0]["trend"]
    check(trend is not None, "and it carries movement")
    check(
        trend["first_decks"] + trend["second_decks"] == variants[0]["decks"],
        f"its members split across the halves: {trend}",
    )


def test_a_deck_with_no_event_date_does_not_take_the_build_down():
    """`tournament_date` is optional, and sorting mixed None with str raises.

    This crashed every build containing one undated deck - inside _examples, sorting
    the sample finishes. Neither real source omits the date, so nothing hit it until a
    hand-imported paste did. It is a TypeError, not a wrong number, so it takes the
    whole report with it.
    """
    decks = _dated_field(["2026-08-01", "2026-08-02"])
    decks[0].tournament_date = None
    report = _built(decks)
    examples = report["pairs"][0]["examples"]
    check(len(examples) == 2, f"both decks still shown: {len(examples)}")
    check(
        [e["date"] for e in examples] == ["2026-08-02", None],
        f"the dated one sorts first: {[e['date'] for e in examples]}",
    )


def test_single_ink_presence_carries_movement_on_the_same_measure():
    """An ink moves like a pair does: decks playing it, over its own half.

    An ink can rise while every pair it appears in falls - it only takes players
    moving between that ink's pairs - which is the thing worth knowing about an ink,
    so the chart has to carry it rather than leave the reader to derive it.
    """
    decks = _dated_field(["2026-08-01"] * 15 + ["2026-08-10"] * 5)
    decks += _dated_field(["2026-08-01"] * 5 + ["2026-08-10"] * 15, pair="amber")
    report = _built(decks)

    inks = {row["ink"]: row for row in report["inks"]}
    # Every deck plays amber, in both halves, so amber cannot have moved.
    check(inks["amber"]["decks"] == 40, f"all 40 play amber: {inks['amber']['decks']}")
    check(inks["amber"]["trend"]["delta"] == 0.0, f"amber flat: {inks['amber']['trend']}")

    # Steel is only in the two-ink half of the field, which shrank.
    steel = inks["steel"]["trend"]
    check(steel["first_share"] == 75.0, f"15 of 20: {steel}")
    check(steel["second_share"] == 25.0, f"5 of 20: {steel}")
    check(steel["delta"] == -50.0, f"and the delta follows: {steel['delta']}")

    for ink, row in inks.items():
        if row["decks"] and row["trend"]:
            check(
                row["trend"]["first_decks"] + row["trend"]["second_decks"] == row["decks"],
                f"{ink}: halves account for every deck playing it: {row['trend']}",
            )


def test_an_ink_nobody_plays_gets_no_movement():
    """A zero row must not claim a delta, and must not raise computing one."""
    report = _built(_dated_field(["2026-08-01"] * 15 + ["2026-08-10"] * 15))
    unplayed = [row for row in report["inks"] if row["decks"] == 0]
    check(bool(unplayed), "the test field leaves some inks unplayed")
    for row in unplayed:
        check(row["trend"] is None, f"{row['ink']}: no decks, no delta ({row['trend']})")
        check(row["share"] == 0.0, f"{row['ink']}: zero share")


# ------------------------------------------------------- the threat board

def _split_pair_field():
    """One ink pair holding two archetypes that disagree completely about one card.

    This is the shape that exposed the bug: on real data, "Maleficent - Vengeful
    Sorceress, played by Amber/Amethyst 63.2%" was one archetype running it in every
    list and another running it in none.
    """
    decks = []
    for i in range(8):  # archetype A: always runs the song
        decks.append(
            Deck(
                source="test",
                deck_id=f"a{i}",
                player=f"A{i}",
                cards=[
                    DeckCard("Elsa - Snow Queen", 30),
                    DeckCard("Hades - Lord of the Underworld", 26),
                    DeckCard("Be Prepared", 4),
                ],
                standing=i + 1,
                wins=4,
                losses=2,
                draws=0,
                tournament_id="T1",
                tournament_name="Cup",
                tournament_date="2026-08-01",
            )
        )
    for i in range(8):  # archetype B: same inks, never runs it
        decks.append(
            Deck(
                source="test",
                deck_id=f"b{i}",
                player=f"B{i}",
                cards=[
                    DeckCard("Elsa - Snow Queen", 4),
                    DeckCard("Hades - Lord of the Underworld", 56),
                ],
                standing=i + 1,
                wins=4,
                losses=2,
                draws=0,
                tournament_id="T2",
                tournament_name="Cup",
                tournament_date="2026-08-10",
            )
        )
    return decks


def test_threats_name_archetypes_not_ink_pairs():
    """The average of "always" and "never" is a number nobody plays."""
    report = _built(_split_pair_field())
    threat = next(t for t in report["threats"] if t["name"] == "Be Prepared")

    inclusions = sorted(c["inclusion"] for c in threat["archetypes"])
    check(
        inclusions == [100.0],
        f"only the archetype that runs it is named, at 100%: {inclusions}",
    )
    check(
        all(not c["is_brews"] for c in threat["archetypes"]),
        "and it is named as an archetype, not a pool of one-offs",
    )
    named = threat["archetypes"][0]
    check(named["decks"] == 8, f"the archetype's own deck count: {named['decks']}")
    # The label has to name the deck, not the pair. Archetype-level numbers under a
    # pair's name read as "the whole pair does this", which is the claim being fixed -
    # and the numbers alone cannot catch that, so assert the label too.
    check(
        named["label"] != named["pair_label"],
        f"the badge names the archetype, not {named['pair_label']}",
    )
    check(
        named["pair_label"] == "Amber / Steel",
        f"with the pair kept alongside for context: {named['pair_label']}",
    )
    check(
        named["share_of_field"] == 50.0,
        f"and its share of the field, for ordering: {named['share_of_field']}",
    )
    check(
        threat["field_presence"] == 50.0,
        f"half the field meets it - not 100% of one pair: {threat['field_presence']}",
    )


def test_threat_figures_match_the_decks_they_came_from():
    """expected_copies and field_presence recomputed by hand from the same field."""
    report = _built(_split_pair_field())
    total = report["totals"]["decks"]
    threat = next(t for t in report["threats"] if t["name"] == "Be Prepared")

    check(
        threat["expected_copies"] == 2.0,
        f"32 copies over {total} decks: {threat['expected_copies']}",
    )
    check(threat["decks"] == 8, f"8 decks run it: {threat['decks']}")
    check(threat["typical_copies"] == 4, f"and they run 4: {threat['typical_copies']}")


def test_every_deck_playing_a_card_is_attributed_to_exactly_one_group():
    """A card's contributors must account for every deck running it.

    Brews carry no card table in the report, so an attribution built from the report
    alone would silently lose them - a quarter of a real field. They are pooled per
    ink pair instead, which keeps the arithmetic whole.
    """
    decks = _split_pair_field()
    # Same inks and it runs the song, but the counts share almost nothing with either
    # archetype, so it clusters alone. A first attempt at this used sensible-looking
    # counts and quietly merged into archetype A - the test then proved nothing, and
    # said so only because it asserted a brew existed.
    decks.append(
        Deck(
            source="test",
            deck_id="brew",
            player="Brewer",
            cards=[
                DeckCard("Elsa - Snow Queen", 4),
                DeckCard("Hades - Lord of the Underworld", 4),
                DeckCard("Be Prepared", 52),
            ],
            standing=1,
            wins=4,
            losses=2,
            draws=0,
            tournament_id="T3",
            tournament_name="Cup",
            tournament_date="2026-08-12",
        )
    )
    report = _built(decks)
    for threat in report["threats"]:
        if len(threat["archetypes"]) > 6:
            continue  # the list is capped for display; nothing to reconcile
        named = sum(c["decks"] for c in threat["archetypes"])
        check(
            named == threat["decks"],
            f"{threat['name']}: groups name {named} decks, {threat['decks']} run it",
        )

    song = next(t for t in report["threats"] if t["name"] == "Be Prepared")
    pooled = [c for c in song["archetypes"] if c["is_brews"]]
    check(len(pooled) == 1, f"the one-off list is pooled, not listed: {song['archetypes']}")
    check(pooled[0]["decks"] == 1, f"and its deck is counted: {pooled[0]}")


def test_cards_carry_movement_with_the_same_floor_as_everything_else():
    """A card the field barely plays gets no delta, however much it swung."""
    decks = _dated_field(["2026-08-01"] * 15 + ["2026-08-10"] * 15)
    for item in decks[-4:]:
        item.cards = [
            DeckCard("Elsa - Snow Queen", 26),
            DeckCard("Hades - Lord of the Underworld", 30),
            DeckCard("Be Prepared", 4),
        ]
    report = _built(decks)

    threats = {t["name"]: t for t in report["threats"]}
    check(report["trend"]["usable"], f"the window splits: {report['trend']['reason']}")
    check(
        threats["Be Prepared"]["trend"] is None,
        f"4 decks is under the floor: {threats['Be Prepared']['trend']}",
    )
    everywhere = threats["Elsa - Snow Queen"]["trend"]
    check(everywhere is not None, "a card in every deck does get one")
    check(
        everywhere["delta"] == 0.0,
        f"and it cannot have moved, being everywhere: {everywhere}",
    )
    check(
        round(everywhere["second_share"] - everywhere["first_share"], 1)
        == everywhere["delta"],
        "the delta is the difference between its own two shares",
    )


def test_thin_pairs_are_dropped_before_anything_is_quoted_against_the_field():
    """Shares and threats must describe the field that survived, not the one before it.

    The drop used to happen after the report was built, which meant walking back over
    it re-deriving every share and rebuilding the threat board against a new
    denominator. Now it happens first, and this pins the result.
    """
    decks = _dated_field(["2026-08-01"] * 15 + ["2026-08-10"] * 15)
    decks += _dated_field(["2026-08-05"] * 2, pair="amber")  # a 2-deck novelty
    report = _built(decks, min_pair_decks=3)

    check(
        {p["key"] for p in report["pairs"]} == {"amber-steel"},
        f"the 2-deck pair is gone: {[p['key'] for p in report['pairs']]}",
    )
    check(report["pairs"][0]["share"] == 100.0, f"share: {report['pairs'][0]['share']}")
    check(report["totals"]["decks"] == 30, f"the field is what is left: {report['totals']}")
    check(
        report["totals"]["decks_dropped_thin_pairs"] == 2,
        "and the dropped decks are counted, not silently gone",
    )
    check(report["totals"]["thin_pairs_dropped"] == 1, "as is the pair")

    for threat in report["threats"]:
        named = sum(c["decks"] for c in threat["archetypes"])
        check(named <= 30, f"{threat['name']} names {named} decks in a 30-deck field")

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
