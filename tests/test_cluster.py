"""Tests for archetype detection.

The thing being defended here: deck names must never influence grouping, and a
deck must survive being modified. Both are easy to break by accident and neither
fails loudly - the report just quietly reports the wrong archetypes.
"""

from __future__ import annotations

import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lorcana_meta.cluster import (  # noqa: E402
    cluster_decks,
    deck_names,
    label_for,
    signature_cards,
    similarity,
)
from lorcana_meta.models import Card, Deck, ResolvedDeck  # noqa: E402
from lorcana_meta.console import configure_output  # noqa: E402

FAILURES: list[str] = []


def check(condition, message):
    if not condition:
        FAILURES.append(message)


def card(name, cost=3, type_="Character"):
    return Card(
        name=name,
        inks=("amber",),
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


CARDS = {f"C{i}": card(f"C{i}") for i in range(40)}


def deck(name, cards: dict, standing=1, deck_id=None):
    """A ResolvedDeck from a {card name: copies} mapping."""
    entries = [(CARDS.setdefault(n, card(n)), c) for n, c in cards.items()]
    return ResolvedDeck(
        deck=Deck(
            source="test",
            deck_id=deck_id or name,
            player="P",
            deck_name=name,
            standing=standing,
        ),
        entries=entries,
        inks=("amber", "steel"),
    )


def spread(names, copies=4):
    return {n: copies for n in names}


CORE = [f"C{i}" for i in range(13)]  # 13 x 4 = 52 cards
OTHER = [f"C{i}" for i in range(20, 33)]


# --------------------------------------------------------------- similarity

def test_similarity_bounds():
    a = spread(CORE)
    check(similarity(a, a) == 1.0, "identical lists score 1.0")
    check(similarity(a, spread(OTHER)) == 0.0, "disjoint lists score 0.0")
    check(similarity(a, {}) == 0.0, "empty list scores 0.0")
    check(similarity({}, {}) == 0.0, "two empty lists do not divide by zero")


def test_similarity_counts_copies():
    four = {"C1": 4}
    one = {"C1": 1}
    check(similarity(four, one) == 0.25, f"1 of 4 copies = 0.25, got {similarity(four, one)}")
    check(
        similarity(four, one) < similarity(four, {"C1": 3}),
        "more shared copies means more similar",
    )


def test_similarity_tolerates_modifications():
    base = spread(CORE)
    tweaked = dict(base)
    tweaked["C0"] = 2  # cut two copies
    tweaked["C99"] = 2  # add a new card
    score = similarity(base, tweaked)
    check(0.85 < score < 1.0, f"a four-card swap stays close: {score:.3f}")


# --------------------------------------------------------------- clustering

def test_modifications_stay_one_archetype():
    """Five pilots on the same deck, each with their own flex slots."""
    decks = []
    for i in range(5):
        cards = spread(CORE)
        cards[f"F{i}"] = 4  # a different flex card each
        cards["C0"] = 3 if i % 2 else 4
        decks.append(deck(f"pilot{i}", cards, standing=i + 1))

    clusters = cluster_decks(decks)
    check(len(clusters) == 1, f"one archetype expected, got {len(clusters)}")
    check(len(clusters[0].members) == 5, "every list in it")


def test_different_decks_split():
    """Two genuinely different builds that share an ink pair."""
    decks = [deck(f"a{i}", spread(CORE), standing=i + 1) for i in range(4)]
    decks += [deck(f"b{i}", spread(OTHER), standing=i + 10) for i in range(3)]

    clusters = cluster_decks(decks)
    check(len(clusters) == 2, f"two archetypes expected, got {len(clusters)}")
    sizes = sorted(len(c.members) for c in clusters)
    check(sizes == [3, 4], f"split 4/3, got {sizes}")
    check(len(clusters[0].members) == 4, "biggest cluster comes first")


def test_names_do_not_group():
    """The whole point: the same name on different decks, and vice versa."""
    same_name_different_decks = [
        deck("Samber", spread(CORE), standing=1, deck_id="x1"),
        deck("Samber", spread(OTHER), standing=2, deck_id="x2"),
    ]
    clusters = cluster_decks(same_name_different_decks)
    check(len(clusters) == 2, f"one name, two decks -> two clusters, got {len(clusters)}")

    different_names_same_deck = [
        deck("Yurple", spread(CORE), standing=1, deck_id="y1"),
        deck("A/P Midrange", spread(CORE), standing=2, deck_id="y2"),
        deck("yellow purple", spread(CORE), standing=3, deck_id="y3"),
    ]
    clusters = cluster_decks(different_names_same_deck)
    check(len(clusters) == 1, f"three names, one deck -> one cluster, got {len(clusters)}")
    check(
        [row["name"] for row in deck_names(clusters[0])]
        == ["A/P Midrange", "Yurple", "yellow purple"],
        f"all three names reported for reference: {deck_names(clusters[0])}",
    )


def test_clustering_is_order_independent():
    decks = [deck(f"a{i}", spread(CORE), standing=i + 1) for i in range(4)]
    decks += [deck(f"b{i}", spread(OTHER), standing=i + 10) for i in range(4)]

    baseline = [sorted(m.deck.deck_id for m in c.members) for c in cluster_decks(decks)]
    for seed in range(5):
        shuffled = decks[:]
        random.Random(seed).shuffle(shuffled)
        result = [sorted(m.deck.deck_id for m in c.members) for c in cluster_decks(shuffled)]
        check(result == baseline, f"seed {seed} changed the clusters: {result} != {baseline}")


def test_threshold_controls_granularity():
    """Two builds sharing about two thirds of their cards."""
    overlap = CORE[:9]
    a = spread(overlap + CORE[9:13])
    b = spread(overlap + OTHER[:4])
    decks = [deck("a", a, standing=1), deck("b", b, standing=2)]

    check(len(cluster_decks(decks, threshold=0.9)) == 2, "a strict threshold splits them")
    check(len(cluster_decks(decks, threshold=0.3)) == 1, "a loose threshold merges them")


# ----------------------------------------------------------------- labelling

def test_signature_finds_the_distinguishing_cards():
    shared = CORE[:10]
    decks = [deck(f"a{i}", spread(shared + ["UNIQUE_A"]), standing=i + 1) for i in range(3)]
    decks += [deck(f"b{i}", spread(shared + ["UNIQUE_B"]), standing=i + 20) for i in range(3)]

    clusters = cluster_decks(decks, threshold=0.9)
    check(len(clusters) == 2, f"expected a split, got {len(clusters)}")

    names = {c.members[0].deck.deck_name[0]: signature_cards(c, clusters) for c in clusters}
    for prefix, signature in names.items():
        top = [row["name"] for row in signature]
        want = f"UNIQUE_{prefix.upper()}"
        check(want in top, f"{want} should be a signature of cluster {prefix}, got {top}")
        check(
            all(row["name"] not in shared for row in signature),
            f"cards the whole pair plays are not a signature: {top}",
        )


def test_label_prefers_the_card_a_player_would_name():
    signature = [
        {"name": "Be Prepared", "edge": 100.0, "is_character": False, "cost": 7, "avg_copies": 4},
        {
            "name": "Wreck-It Ralph - Admiral Underpants",
            "edge": 100.0,
            "is_character": True,
            "cost": 7,
            "avg_copies": 4,
        },
    ]
    # signature_cards() applies the ordering; label_for takes the first two as given.
    check(
        label_for(signature, "fallback") == "Be Prepared + Wreck-It Ralph",
        f"version suffix dropped from the label: {label_for(signature, 'fallback')}",
    )
    check(label_for([], "Core list") == "Core list", "no signature falls back")


def test_signature_ordering_prefers_characters_then_cost():
    shared = CORE[:10]
    CARDS["Cheap Guy"] = card("Cheap Guy", cost=1)
    CARDS["Big Threat"] = card("Big Threat", cost=8)
    CARDS["A Spell"] = card("A Spell", cost=8, type_="Action")

    decks = [
        deck(f"a{i}", spread(shared + ["Cheap Guy", "Big Threat", "A Spell"]), standing=i + 1)
        for i in range(3
        )
    ]
    clusters = cluster_decks(decks)
    # A lone cluster has no "outside", so every card it plays is a signature; ask for
    # the whole ranking rather than the top four the site shows.
    signature = signature_cards(clusters[0], clusters, limit=50)
    names = [row["name"] for row in signature]
    check(
        names.index("Big Threat") < names.index("A Spell"),
        f"an 8-cost character outranks an 8-cost action: {names}",
    )
    check(
        names.index("Big Threat") < names.index("Cheap Guy"),
        f"the expensive character outranks the cheap one: {names}",
    )


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
