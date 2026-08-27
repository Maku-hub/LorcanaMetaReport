"""Turn a pile of decklists into meta statistics.

The numbers this module produces, and what a player is meant to do with them:

* **pair share** - how much of the field an ink pair is. Tells you what you will
  actually sit across from.
* **inclusion %** - of the decks in a pair, how many run at least one copy. A card
  at 95% is part of the archetype's definition; at 30% it is a pilot's choice.
* **average copies** - the mean among the lists that run it. Useful, but a mean is
  the wrong answer to "how many will I face": across 45 real lists of one archetype,
  one card averaged 2.40 copies while 28 of them ran exactly 2.
* **typical copies** - the mode, plus the full spread of how many decks run 1, 2, 3
  or 4. This is the number to build against, and the spread shows whether the
  archetype agrees with itself or is split.
* **expected copies** - inclusion and pair share multiplied out over the whole
  field: the number of copies of a card in a deck drawn at random from the meta.
  This is the ranking to build tech against, because it already accounts for how
  popular the deck playing that card is.
"""

from __future__ import annotations

import logging
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from .cards import CardIndex
from .cluster import (
    BREW_MAX_DECKS,
    DEFAULT_THRESHOLD,
    Cluster,
    cluster_decks,
    deck_names,
    label_for,
    signature_cards,
)
from .models import INKS, Card, Deck, DeckCard, ResolvedDeck

log = logging.getLogger(__name__)

#: A card at or above this inclusion rate is treated as part of the archetype's core.
CORE_INCLUSION = 0.80
#: Below this, a card is a fringe/pilot choice rather than a real part of the pair.
FRINGE_INCLUSION = 0.15
#: A constructed deck is 60 cards; well under that means the paste was truncated.
MIN_RESOLVED_CARDS = 40


@dataclass
class Anomalies:
    """Things that did not add up, surfaced instead of silently dropped."""

    unknown_cards: Counter = field(default_factory=Counter)
    undetermined_inks: int = 0
    over_two_inks: int = 0
    short_decks: int = 0

    def as_dict(self) -> dict:
        return {
            "unknown_cards": [
                {"name": name, "occurrences": count}
                for name, count in self.unknown_cards.most_common(50)
            ],
            "unknown_card_count": len(self.unknown_cards),
            "undetermined_inks": self.undetermined_inks,
            "over_two_inks": self.over_two_inks,
            "short_decks": self.short_decks,
        }


def derive_inks(entries: list[tuple[Card, int]]) -> tuple[str, ...]:
    """Work out which inks a deck is built on.

    Single-ink cards decide it. A dual-ink card is only legal when both of its
    inks are in the deck, so it fills in the second ink of an otherwise mono list.
    """
    singles: set[str] = set()
    duals: list[tuple[str, ...]] = []
    for card, _count in entries:
        if len(card.inks) == 1:
            singles.add(card.inks[0])
        elif len(card.inks) == 2:
            duals.append(card.inks)

    inks = set(singles)
    if len(inks) < 2:
        for dual in duals:
            inks.update(dual)

    if not inks or len(inks) > 2:
        return ()
    return tuple(sorted(inks, key=INKS.index))


def resolve_deck(deck: Deck, index: CardIndex, anomalies: Anomalies) -> ResolvedDeck | None:
    """Match a deck's card names against the card database."""
    entries: list[tuple[Card, int]] = []
    unknown: list[DeckCard] = []

    for line in deck.cards:
        card = index.get(line.name)
        if card is None:
            unknown.append(line)
            anomalies.unknown_cards[line.name] += 1
        else:
            entries.append((card, line.count))

    if not entries:
        return None

    if sum(count for _card, count in entries) < MIN_RESOLVED_CARDS:
        anomalies.short_decks += 1
        return None

    inks = derive_inks(entries)
    if not inks:
        singles = {c.inks[0] for c, _ in entries if len(c.inks) == 1}
        if len(singles) > 2:
            anomalies.over_two_inks += 1
        else:
            anomalies.undetermined_inks += 1

    return ResolvedDeck(deck=deck, entries=entries, unknown=unknown, inks=inks)


def resolve_all(decks: list[Deck], index: CardIndex) -> tuple[list[ResolvedDeck], Anomalies]:
    anomalies = Anomalies()
    resolved = []
    for deck in decks:
        item = resolve_deck(deck, index, anomalies)
        if item is not None and item.inks:
            resolved.append(item)
    return resolved, anomalies


def _card_payload(card: Card) -> dict:
    return {
        "name": card.name,
        "inks": list(card.inks),
        "cost": card.cost,
        "type": card.type,
        "base_type": card.base_type,
        "inkable": card.inkable,
        "lore": card.lore,
        "strength": card.strength,
        "willpower": card.willpower,
        "text": card.text,
        "image": card.image,
        "set_id": card.set_id,
        "rarity": card.rarity,
    }


def _pct(part: float, whole: float) -> float:
    return round(100.0 * part / whole, 1) if whole else 0.0


def _modal_copies(distribution: Counter) -> int:
    """The copy count most lists actually run.

    A mean is the wrong summary for a question like "how many will I face". Across
    45 real lists of one archetype, Ursula - Whisper of Vanessa averages 2.40 copies,
    which sounds like "2 or 3" - but 28 of the 43 lists that play her run exactly 2.
    The mode is the number to build against.

    Ties go to the higher count: if a card is equally often a 2-of and a 3-of, the
    useful assumption when preparing is the one that hurts more.
    """
    return max(distribution.items(), key=lambda item: (item[1], item[0]))[0]


def _card_stats_for(group: list[ResolvedDeck]) -> list[dict]:
    """Inclusion and copy counts for every card played by a group of decks."""
    decks_with: Counter = Counter()
    copies: Counter = Counter()
    # How many decks run exactly N copies. The mean hides this, and the shape is
    # what tells you whether "3.5 copies" means everyone is on 3-4 or the archetype
    # is split down the middle.
    distribution: dict[str, Counter] = defaultdict(Counter)

    for item in group:
        # Total this deck's copies per card first. A card can appear on two lines of
        # one list (a paste split by section, or two printings of the same name), and
        # the distribution has to record one bin per deck, not one per line.
        per_deck: Counter = Counter()
        for card, count in item.entries:
            per_deck[card.name] += count

        for name, count in per_deck.items():
            copies[name] += count
            decks_with[name] += 1
            distribution[name][count] += 1

    total = len(group)
    stats = []
    for name, n_decks in decks_with.items():
        inclusion = n_decks / total
        spread = distribution[name]
        stats.append(
            {
                "name": name,
                "decks": n_decks,
                "inclusion": round(100.0 * inclusion, 1),
                "avg_copies": round(copies[name] / n_decks, 2),
                "avg_copies_overall": round(copies[name] / total, 2),
                "typical_copies": _modal_copies(spread),
                #: {copies: how many decks run exactly that many}
                "copies_spread": {str(k): v for k, v in sorted(spread.items())},
                "total_copies": copies[name],
                "tier": (
                    "core"
                    if inclusion >= CORE_INCLUSION
                    else "fringe"
                    if inclusion < FRINGE_INCLUSION
                    else "flex"
                ),
            }
        )

    stats.sort(key=lambda s: (-s["inclusion"], -s["avg_copies"], s["name"]))
    return stats


def _cost_curve(group: list[ResolvedDeck]) -> list[dict]:
    """Average number of cards at each ink cost, across the group's decks."""
    buckets: Counter = Counter()
    for item in group:
        for card, count in item.entries:
            if card.cost is not None:
                buckets[min(card.cost, 10)] += count

    if not group or not buckets:
        return []
    return [
        {"cost": cost, "avg_cards": round(buckets.get(cost, 0) / len(group), 2)}
        for cost in range(1, max(buckets) + 1)
    ]


def _type_mix(group: list[ResolvedDeck]) -> list[dict]:
    buckets: Counter = Counter()
    for item in group:
        for card, count in item.entries:
            buckets[card.base_type or "Other"] += count
    total = sum(buckets.values())
    return [
        {"type": name, "avg_cards": round(count / len(group), 1), "share": _pct(count, total)}
        for name, count in buckets.most_common()
    ]


def _record(group: list[ResolvedDeck]) -> dict:
    wins = sum(i.deck.wins or 0 for i in group)
    losses = sum(i.deck.losses or 0 for i in group)
    draws = sum(i.deck.draws or 0 for i in group)
    games = wins + losses + draws
    standings = [i.deck.standing for i in group if i.deck.standing]
    return {
        "wins": wins,
        "losses": losses,
        "draws": draws,
        "win_rate": _pct(wins, games) if games else None,
        "avg_standing": round(sum(standings) / len(standings), 1) if standings else None,
        "top8_decks": sum(1 for s in standings if s <= 8),
    }


def _examples(group: list[ResolvedDeck], limit: int = 8) -> list[dict]:
    ordered = sorted(group, key=lambda i: (i.deck.standing or 999, i.deck.tournament_date))
    return [
        {
            "player": i.deck.player,
            "standing": i.deck.standing,
            # Sources differ: "1st" is exact, "Top8" is a bucket that `standing`
            # flattens to 8. Show what the source actually said.
            "standing_label": i.deck.standing_label,
            "tournament": i.deck.tournament_name,
            "date": i.deck.tournament_date,
            "players": i.deck.tournament_players,
            "url": i.deck.url,
        }
        for i in ordered[:limit]
    ]


def _variants(
    group: list[ResolvedDeck],
    total_field: int,
    threshold: float,
) -> list[dict]:
    """Split an ink pair into archetypes by card overlap.

    Two lists in the same pair can be entirely different decks, and the same deck
    arrives under a different name every time, so the split is done on contents.
    See :mod:`lorcana_meta.cluster` for the measure.
    """
    clusters: list[Cluster] = cluster_decks(group, threshold)
    rows = []
    for index_, cluster in enumerate(clusters, start=1):
        signature = signature_cards(cluster, clusters)
        fallback = "Core list" if len(clusters) == 1 else f"Variant {index_}"
        rows.append(
            {
                "key": f"v{index_}",
                "label": label_for(signature, fallback),
                "decks": len(cluster.members),
                "share_of_pair": _pct(len(cluster.members), len(group)),
                "share_of_field": _pct(len(cluster.members), total_field),
                "is_brew": len(cluster.members) <= BREW_MAX_DECKS,
                "signature": signature,
                "named_by_players": deck_names(cluster),
                "record": _record(cluster.members),
                "cost_curve": _cost_curve(cluster.members),
                "cards": _card_stats_for(cluster.members),
                "examples": _examples(cluster.members, limit=5),
            }
        )
    return rows


def build_meta(
    decks: list[Deck],
    index: CardIndex,
    *,
    period: dict,
    source: dict,
    filters: dict,
    generated_at: str,
    cluster_threshold: float = DEFAULT_THRESHOLD,
) -> dict:
    """Aggregate decklists into the JSON payload the site renders."""
    resolved, anomalies = resolve_all(decks, index)
    total = len(resolved)
    if not total:
        log.warning("no decks survived resolution - the site will render an empty state")

    by_pair: dict[str, list[ResolvedDeck]] = defaultdict(list)
    for item in resolved:
        by_pair[item.pair_key].append(item)

    card_payloads: dict[str, dict] = {}
    for item in resolved:
        for card, _count in item.entries:
            card_payloads.setdefault(card.name, _card_payload(card))

    pairs = []
    for key, group in by_pair.items():
        sample = group[0]
        pairs.append(
            {
                "key": key,
                "inks": list(sample.inks),
                "label": sample.pair_label,
                "decks": len(group),
                "share": _pct(len(group), total),
                "record": _record(group),
                "cost_curve": _cost_curve(group),
                "type_mix": _type_mix(group),
                "cards": _card_stats_for(group),
                "examples": _examples(group),
                "variants": _variants(group, total, cluster_threshold),
            }
        )

    pairs.sort(key=lambda p: (-p["decks"], p["label"]))

    # Single-ink presence: an ink's share of the field counts every deck that plays it,
    # so these add up to ~200% for a field of two-ink decks. Labelled as such on screen.
    ink_rows = [
        {
            "ink": ink,
            "label": ink.capitalize(),
            "decks": sum(1 for item in resolved if ink in item.inks),
            "share": _pct(sum(1 for item in resolved if ink in item.inks), total),
        }
        for ink in INKS
    ]
    ink_rows.sort(key=lambda r: -r["decks"])

    tournaments = {i.deck.tournament_id or i.deck.tournament_name for i in resolved}

    return {
        "generated_at": generated_at,
        "period": period,
        "source": source,
        "filters": {**filters, "cluster_threshold": cluster_threshold},
        "totals": {
            "decks": total,
            "decks_fetched": len(decks),
            "tournaments": len(tournaments),
            "pairs": len(pairs),
            "variants": sum(len(p["variants"]) for p in pairs),
        },
        "inks": ink_rows,
        "pairs": pairs,
        "threats": _threats(pairs, card_payloads),
        "cards": card_payloads,
        "anomalies": anomalies.as_dict(),
    }


def _threats(pairs: list[dict], card_payloads: dict[str, dict], limit: int = 150) -> list[dict]:
    """Rank cards by how many copies you expect to face across the whole field."""
    expected: dict[str, float] = defaultdict(float)
    presence: dict[str, float] = defaultdict(float)
    played_by: dict[str, list[dict]] = defaultdict(list)

    for pair in pairs:
        weight = pair["share"] / 100.0
        for stat in pair["cards"]:
            expected[stat["name"]] += weight * stat["avg_copies_overall"]
            presence[stat["name"]] += weight * (stat["inclusion"] / 100.0)
            played_by[stat["name"]].append(
                {
                    "pair": pair["key"],
                    "label": pair["label"],
                    "inclusion": stat["inclusion"],
                    "avg_copies": stat["avg_copies"],
                    "typical_copies": stat["typical_copies"],
                    "pair_share": pair["share"],
                }
            )

    rows = []
    for name, value in expected.items():
        contributors = sorted(played_by[name], key=lambda p: -p["pair_share"])
        payload = card_payloads.get(name, {})
        rows.append(
            {
                "name": name,
                "expected_copies": round(value, 2),
                # expected_copies is a true expectation over the whole field, so it is
                # deliberately fractional. This is the other half of the answer: when
                # you do meet the deck that plays it, how many copies is it running.
                "typical_copies": contributors[0]["typical_copies"] if contributors else None,
                "field_presence": round(100.0 * presence[name], 1),
                "pairs": contributors[:6],
                "pair_count": len(contributors),
                "cost": payload.get("cost"),
                "base_type": payload.get("base_type"),
                "inks": payload.get("inks", []),
            }
        )

    rows.sort(key=lambda r: (-r["expected_copies"], r["name"]))
    return rows[:limit]
