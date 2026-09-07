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
from dataclasses import dataclass, field, replace
from datetime import date, timedelta

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

#: Decks each half of the window needs before any movement is shown at all.
MIN_TREND_DECKS_PER_HALF = 15
#: Decks a pair or archetype needs across the window before its own delta is shown.
#: Below this the delta is arithmetic on two or three lists, which reads as a trend
#: and is not one.
MIN_TREND_ROW_DECKS = 8


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


def _tally(group: list[ResolvedDeck]) -> tuple[Counter, Counter, dict[str, Counter]]:
    """Per card across `group`: decks running it, total copies, and the copy spread.

    Extracted because the threat board needs the same counts as the archetype tables
    and must not re-derive them: the per-deck rollup below is the subtle part, and two
    implementations of it would eventually disagree.
    """
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

    return decks_with, copies, distribution


def _card_stats_for(group: list[ResolvedDeck]) -> list[dict]:
    """Inclusion and copy counts for every card played by a group of decks."""
    decks_with, copies, distribution = _tally(group)
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
    # `tournament_date` is optional on Deck, and comparing None with a string raises -
    # an undated deck used to take the whole build down here. Undated sorts last among
    # equal placings rather than first, so a known date wins the tie.
    ordered = sorted(
        group,
        key=lambda i: (
            i.deck.standing or 999,
            i.deck.tournament_date is None,
            i.deck.tournament_date or "",
        ),
    )
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


@dataclass(frozen=True)
class Halves:
    """The window cut in two, and how many decks landed either side.

    The cut is by calendar date, not by deck count. Halves of equal length are what
    "the back half of the window" means to whoever reads it; halves of equal deck
    count would be two unequal stretches of time presented as if they were not, and a
    quiet weekend would move the boundary rather than show up as a thin half.

    This is a split of one window, not a comparison with a previous month. Nothing
    here fetches a second date range - the decks are the ones already in hand.
    """

    split: str  #: first date belonging to the second half, YYYY-MM-DD
    first: tuple[str, str]
    second: tuple[str, str]
    first_decks: int
    second_decks: int
    undated: int
    #: Why no movement may be shown, in words, or None. Set once by :func:`_halves`
    #: so that one decision governs both the report-level block and every row - a
    #: row cannot end up with a delta the page has already said is not available.
    blocked: str | None = None

    @property
    def usable(self) -> bool:
        return self.blocked is None

    def side(self, item: ResolvedDeck) -> int:
        """0 for the first half, 1 for the second, -1 for a deck with no date."""
        date = (item.deck.tournament_date or "").strip()
        if not date:
            return -1
        return 1 if date >= self.split else 0

    def as_dict(self) -> dict:
        return {
            "usable": self.usable,
            "reason": self.blocked,
            "split": self.split,
            "first": {"start": self.first[0], "end": self.first[1], "decks": self.first_decks},
            "second": {"start": self.second[0], "end": self.second[1], "decks": self.second_decks},
            "undated_decks": self.undated,
            # The per-half floor is not emitted: when it bites, `reason` already says
            # the number in words, and when it does not, nothing on screen wants it.
            "min_decks_per_row": MIN_TREND_ROW_DECKS,
        }


def _why_no_trend(halves: Halves, period: dict) -> str | None:
    """Say in words why the window could not be split, or None if it could.

    Blank space where a number was expected invites the reader to assume a bug or,
    worse, to assume nothing moved. Both are worse than a sentence saying the field
    is too small to tell.
    """
    if not halves.split:
        return f"the window {period.get('start')} to {period.get('end')} is not two dates"
    if period.get("days", 0) < 4:
        return f"a {period.get('days')}-day window is too short to have two halves"
    thin = min(halves.first_decks, halves.second_decks)
    if thin < MIN_TREND_DECKS_PER_HALF:
        return (
            f"one half of the window holds only {thin} deck(s), under the "
            f"{MIN_TREND_DECKS_PER_HALF} needed for a share to mean anything"
        )
    return None


def _halves(period: dict, resolved: list[ResolvedDeck]) -> Halves:
    start, end = period.get("start", ""), period.get("end", "")
    try:
        first_day = date.fromisoformat(start)
        last_day = date.fromisoformat(end)
    except ValueError:  # a window we cannot read is a window we cannot split
        return Halves(
            "",
            ("", ""),
            ("", ""),
            0,
            0,
            len(resolved),
            blocked=f"the window {start!r} to {end!r} is not two dates",
        )

    days = (last_day - first_day).days + 1
    # An odd number of days gives the extra day to the first half, so the second half
    # is never the shorter one: recent movement is the half people act on.
    split_day = first_day + timedelta(days=(days + 1) // 2)
    halves = Halves(
        split=split_day.isoformat(),
        first=(first_day.isoformat(), (split_day - timedelta(days=1)).isoformat()),
        second=(split_day.isoformat(), last_day.isoformat()),
        first_decks=0,
        second_decks=0,
        undated=0,
    )
    sides = Counter(halves.side(item) for item in resolved)
    counted = Halves(
        split=halves.split,
        first=halves.first,
        second=halves.second,
        first_decks=sides[0],
        second_decks=sides[1],
        undated=sides[-1],
    )
    # One decision, taken here, governs both the report-level block and every row.
    return replace(counted, blocked=_why_no_trend(counted, period))


def _trend_for(members: list[ResolvedDeck], halves: Halves) -> dict | None:
    """Movement of one pair or archetype between the two halves of the window.

    Shares are rounded before subtracting, so the delta on screen is exactly the
    difference between the two numbers next to it. A reader checking the arithmetic
    should find it correct, not off by a tenth.
    """
    if not halves.usable:
        return None
    dated = [item for item in members if halves.side(item) >= 0]
    if len(dated) < MIN_TREND_ROW_DECKS:
        return None

    first = sum(1 for item in dated if halves.side(item) == 0)
    second = len(dated) - first
    first_share = _pct(first, halves.first_decks)
    second_share = _pct(second, halves.second_decks)
    return {
        "first_decks": first,
        "second_decks": second,
        "first_share": first_share,
        "second_share": second_share,
        "delta": round(second_share - first_share, 1),
    }


def _variants(
    clusters: list[Cluster],
    group: list[ResolvedDeck],
    total_field: int,
    halves: Halves,
) -> list[dict]:
    """Describe the archetypes of one ink pair.

    Two lists in the same pair can be entirely different decks, and the same deck
    arrives under a different name every time, so the split is done on contents. See
    :mod:`lorcana_meta.cluster` for the measure.

    The clustering itself happens in :func:`build_meta` and is handed in, because the
    threat board needs the same membership to attribute cards to archetypes. Running
    `cluster_decks` twice would risk two answers to "which deck is this".
    """
    rows = []
    for index_, cluster in enumerate(clusters, start=1):
        signature = signature_cards(cluster, clusters)
        fallback = "Core list" if len(clusters) == 1 else f"Variant {index_}"
        is_brew = len(cluster.members) <= BREW_MAX_DECKS

        # A brew gets no card table. For a single deck, "inclusion" is 100% on every
        # card it plays and the copy spread is one bin - it is that deck's decklist
        # wearing the clothes of an analysis. On a real 320-deck field those tables
        # were 320 KB, 37% of the report, and told you nothing you could act on.
        # The brew still appears, with its label, size, record and tells.
        rows.append(
            {
                "key": f"v{index_}",
                "label": label_for(signature, fallback),
                "decks": len(cluster.members),
                "share_of_pair": _pct(len(cluster.members), len(group)),
                "share_of_field": _pct(len(cluster.members), total_field),
                "is_brew": is_brew,
                "signature": signature,
                "named_by_players": deck_names(cluster),
                "record": _record(cluster.members),
                "cost_curve": [] if is_brew else _cost_curve(cluster.members),
                "cards": [] if is_brew else _card_stats_for(cluster.members),
                "examples": _examples(cluster.members, limit=5),
                # Clustering ran once, over the whole window, so an archetype has the
                # same identity in both halves and its decks only need counting.
                # Clustering each half separately would leave us matching archetypes
                # across halves - the problem card overlap exists to avoid.
                "trend": _trend_for(cluster.members, halves),
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
    built_by: dict | None = None,
    cluster_threshold: float = DEFAULT_THRESHOLD,
    min_pair_decks: int = 1,
) -> dict:
    """Aggregate decklists into the JSON payload the site renders."""
    resolved, anomalies = resolve_all(decks, index)
    if not resolved:
        log.warning("no decks survived resolution - the site will render an empty state")

    grouped: dict[str, list[ResolvedDeck]] = defaultdict(list)
    for item in resolved:
        grouped[item.pair_key].append(item)

    # Thin pairs go before anything is derived from them. A pair seen twice is not a
    # meta reading, and leaving it in makes a one-deck novelty look like a 3%
    # archetype. This used to be a post-filter that had to walk back over the finished
    # report re-deriving every share and rebuilding the threat board against a
    # different denominator - two chances to leave a number quoted against a field
    # that no longer existed. Drop first, compute once.
    by_pair = {k: g for k, g in grouped.items() if len(g) >= max(min_pair_decks, 1)}
    dropped = [g for k, g in grouped.items() if k not in by_pair]

    # Everything downstream is quoted against the field that survived, and `field` is
    # that field - the decks the report actually describes.
    field = [item for group in by_pair.values() for item in group]
    total = len(field)

    halves = _halves(period, field)
    if halves.blocked:
        log.info("no movement shown: %s", halves.blocked)

    card_payloads: dict[str, dict] = {}
    for item in field:
        for card, _count in item.entries:
            card_payloads.setdefault(card.name, _card_payload(card))

    pairs = []
    archetype_groups: list[dict] = []
    for key, group in by_pair.items():
        sample = group[0]
        clusters = cluster_decks(group, cluster_threshold)
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
                "trend": _trend_for(group, halves),
                "variants": _variants(clusters, group, total, halves),
            }
        )

        # What the threat board attributes cards to. Real archetypes stand alone; the
        # one-off lists of a pair are pooled, because a contributor row per brew reads
        # 100% inclusion on everything and buries the decks worth preparing for.
        brews: list[ResolvedDeck] = []
        for index_, cluster in enumerate(clusters, start=1):
            if len(cluster.members) <= BREW_MAX_DECKS:
                brews.extend(cluster.members)
                continue
            archetype_groups.append(
                {
                    "pair_key": key,
                    "pair_label": sample.pair_label,
                    "label": pairs[-1]["variants"][index_ - 1]["label"],
                    "members": cluster.members,
                    "is_brews": False,
                }
            )
        if brews:
            archetype_groups.append(
                {
                    "pair_key": key,
                    "pair_label": sample.pair_label,
                    "label": f"{BREW_GROUP_LABEL} ({sample.pair_label})",
                    "members": brews,
                    "is_brews": True,
                }
            )

    pairs.sort(key=lambda p: (-p["decks"], p["label"]))

    # Single-ink presence: an ink's share of the field counts every deck that plays it,
    # so these add up to ~200% for a field of two-ink decks. Labelled as such on screen.
    #
    # Movement per ink is the same measure as per pair - decks playing it as a share of
    # its own half - so an ink can rise while every pair it appears in falls, which is
    # exactly the thing worth knowing about an ink.
    ink_rows = []
    for ink in INKS:
        playing = [item for item in field if ink in item.inks]
        ink_rows.append(
            {
                "ink": ink,
                "label": ink.capitalize(),
                "decks": len(playing),
                "share": _pct(len(playing), total),
                "trend": _trend_for(playing, halves),
            }
        )
    ink_rows.sort(key=lambda r: -r["decks"])

    tournaments = {i.deck.tournament_id or i.deck.tournament_name for i in field}

    return {
        "generated_at": generated_at,
        # What built it, not just when: see cli._build_version.
        "built_by": built_by or {"version": None, "commit": None, "dirty": None},
        "period": period,
        "source": source,
        "filters": {**filters, "cluster_threshold": cluster_threshold},
        "totals": {
            "decks": total,
            "decks_fetched": len(decks),
            "decks_resolved": len(resolved),
            "tournaments": len(tournaments),
            "pairs": len(pairs),
            "variants": sum(len(p["variants"]) for p in pairs),
            # Anything dropped is counted and shown - the About page reads both.
            "thin_pairs_dropped": len(dropped),
            "decks_dropped_thin_pairs": sum(len(g) for g in dropped),
        },
        "trend": halves.as_dict(),
        "inks": ink_rows,
        "pairs": pairs,
        "threats": _threats(field, archetype_groups, card_payloads, halves),
        "cards": card_payloads,
        "anomalies": anomalies.as_dict(),
    }


def _card_trends(
    group: list[ResolvedDeck], halves: Halves
) -> dict[str, dict | None]:
    """Per card: how its share of the field moved between the halves of the window.

    The most actionable line in the report. An archetype rising tells you which deck
    to prepare for; a card rising tells you what to prepare for regardless of which
    deck brings it - "everyone is adding this" is the thing you want to know before
    building, and it can happen without any archetype moving at all.

    Same discipline as everywhere else: a card played by a handful of decks can swing
    ten points on one list, so it gets no delta until it clears the row floor. Shares
    are of each half's own deck count, and rounded before subtracting so the delta is
    the difference between the two numbers printed beside it.
    """
    if not halves.usable:
        return {}

    first = [item for item in group if halves.side(item) == 0]
    second = [item for item in group if halves.side(item) == 1]
    in_first, _, _ = _tally(first)
    in_second, _, _ = _tally(second)

    trends: dict[str, dict | None] = {}
    for name in set(in_first) | set(in_second):
        played = in_first[name] + in_second[name]
        if played < MIN_TREND_ROW_DECKS:
            trends[name] = None
            continue
        first_share = _pct(in_first[name], halves.first_decks)
        second_share = _pct(in_second[name], halves.second_decks)
        trends[name] = {
            "first_decks": in_first[name],
            "second_decks": in_second[name],
            "first_share": first_share,
            "second_share": second_share,
            "delta": round(second_share - first_share, 1),
        }
    return trends


#: How a group of one-off lists is labelled where it contributes to a threat. They are
#: not an archetype, and calling them one would put a category on the same footing as
#: a deck; but their cards are part of the field and have to be counted somewhere.
BREW_GROUP_LABEL = "One-off lists"

#: How many contributing groups each threat row carries. A staple can be in thirty,
#: and shipping them all would put the size saving of `_lean` straight back.
CONTRIBUTORS_SHOWN = 6


def _threats(
    field: list[ResolvedDeck],
    by_archetype: list[dict],
    card_payloads: dict[str, dict],
    halves: Halves,
    limit: int = 150,
) -> list[dict]:
    """Rank cards by how many copies you expect to face, and say which decks bring them.

    `expected_copies` and `field_presence` are computed straight off the whole field,
    not summed over groups. Both used to be assembled as a weighted sum over ink
    pairs, which was exact - pairs partition the field, so the weights collapse to
    "copies in the field over decks in the field" - but it made the numbers look like
    they depended on the grouping, and it is one fewer thing to get wrong.

    The attribution is by **archetype**, which is the fix this function exists for. It
    used to name ink pairs, and on real data that produced numbers nobody plays:
    "Maleficent - Vengeful Sorceress, played by Amber/Amethyst 63.2%" was one
    archetype running it in every list and another running it in none. 63.2% invites
    preparing for a coin flip when the truth is "one deck always has it, the other
    never does" - and which one is across the table is exactly what the signature
    cards tell you. Averaging a card across an ink pair is the mush that clustering by
    card overlap exists to avoid; the threat board was the last place still doing it.

    One-off lists are grouped rather than listed. Each is one deck, so its inclusion
    is 100% on everything it plays - a contributor row per brew would bury the decks
    worth preparing for under dozens of rows that all read 100%.
    """
    total = len(field)
    if not total:
        return []

    decks_with, copies, distribution = _tally(field)
    trends = _card_trends(field, halves)

    played_by: dict[str, list[dict]] = defaultdict(list)
    for group in by_archetype:
        members = group["members"]
        if not members:
            continue
        group_decks, _group_copies, group_spread = _tally(members)
        for name, n_decks in group_decks.items():
            played_by[name].append(
                {
                    "pair": group["pair_key"],
                    "label": group["label"],
                    "pair_label": group["pair_label"],
                    "decks": n_decks,
                    "share_of_field": _pct(n_decks, total),
                    "inclusion": _pct(n_decks, len(members)),
                    "typical_copies": _modal_copies(group_spread[name]),
                    "is_brews": group["is_brews"],
                }
            )

    rows = []
    for name, n_decks in decks_with.items():
        # Ordered by how much of the field each deck actually is: the first row is the
        # one you are most likely to be sitting across from.
        contributors = sorted(
            played_by[name], key=lambda c: (-c["share_of_field"], c["label"])
        )
        payload = card_payloads.get(name, {})
        rows.append(
            {
                "name": name,
                # A true expectation over the whole field - copies per deck drawn at
                # random - so it is deliberately fractional.
                "expected_copies": round(copies[name] / total, 2),
                # The other half of the answer: when you do meet it, how many. The
                # mode among the decks that actually play it, not the biggest group's.
                "typical_copies": _modal_copies(distribution[name]),
                "field_presence": _pct(n_decks, total),
                "decks": n_decks,
                # Capped for size; the page needs the real count or its "+N more"
                # badge silently maxes out at the cap and understates how widely
                # spread a staple is.
                "archetypes": contributors[:CONTRIBUTORS_SHOWN],
                "contributor_count": len(contributors),
                "trend": trends.get(name),
                "cost": payload.get("cost"),
                "base_type": payload.get("base_type"),
                "inks": payload.get("inks", []),
            }
        )

    rows.sort(key=lambda r: (-r["expected_copies"], r["name"]))
    return rows[:limit]
