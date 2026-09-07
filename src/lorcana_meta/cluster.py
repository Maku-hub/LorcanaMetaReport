"""Group decks into archetypes by what is in them, not what they are called.

Deck names are free text. The same list gets submitted as "Yurple", "A/P Midrange"
and "yellow purple good stuff", while two lists sharing a name can be different
decks. So names are never used to group anything here - they are collected and
displayed as an afterthought ("players called this: ...").

What decides an archetype is card overlap. Two 60-card lists that differ by four
cards are the same deck with modifications; two that share half their cards are
different decks that happen to share an ink pair.

The measure is the **weighted Jaccard index** over card counts:

    similarity(a, b) = sum(min(a_i, b_i)) / sum(max(a_i, b_i))

Counting copies rather than just names matters: a list running 4 Grandmother Willow
and one running 1 are making different choices, and plain set overlap cannot see it.
Two identical lists score 1.0; two lists differing by 4 of 60 cards score about 0.87;
two lists sharing nothing score 0.0.

Clustering is leader-based: decks are visited best-finish-first, each joins the
existing cluster whose centroid it is closest to if that beats the threshold, and
otherwise starts its own. A merge pass afterwards collapses clusters that ended up
adjacent, which removes the dependence on visit order. Both passes are
deterministic - the same input always produces the same clusters.
"""

from __future__ import annotations

import logging
from collections import Counter
from dataclasses import dataclass, field

from .models import ResolvedDeck

log = logging.getLogger(__name__)

#: Weighted-Jaccard floor for "the same deck". Tuned against 60-card constructed
#: lists: 0.60 keeps a deck together across a dozen swapped cards while still
#: splitting genuinely different builds inside one ink pair.
DEFAULT_THRESHOLD = 0.60
#: A cluster this small is one pilot's brew, not an archetype. Kept and reported,
#: but flagged so the site can fold it away.
BREW_MAX_DECKS = 2
#: A card must be in at least this share of a cluster's lists to name it.
SIGNATURE_MIN_INCLUSION = 0.5
#: ...and be this much more common than in the rest of the ink pair.
SIGNATURE_MIN_EDGE = 0.25


def deck_counts(item: ResolvedDeck) -> Counter:
    counts: Counter = Counter()
    for card, count in item.entries:
        counts[card.name] += count
    return counts


def similarity(a: dict, b: dict) -> float:
    """Weighted Jaccard over card counts. Accepts float counts (centroids)."""
    low = high = 0.0
    for name in a.keys() | b.keys():
        x, y = a.get(name, 0), b.get(name, 0)
        low += min(x, y)
        high += max(x, y)
    return low / high if high else 0.0


@dataclass
class Cluster:
    members: list[ResolvedDeck] = field(default_factory=list)
    counts: list[Counter] = field(default_factory=list)
    _centroid: dict | None = None

    @property
    def centroid(self) -> dict:
        """Average copies of each card across the cluster's lists."""
        if self._centroid is None:
            total: Counter = Counter()
            for counts in self.counts:
                total.update(counts)
            size = len(self.counts) or 1
            self._centroid = {name: value / size for name, value in total.items()}
        return self._centroid

    def add(self, item: ResolvedDeck, counts: Counter) -> None:
        self.members.append(item)
        self.counts.append(counts)
        self._centroid = None

    def absorb(self, other: Cluster) -> None:
        self.members += other.members
        self.counts += other.counts
        self._centroid = None

    @property
    def best_standing(self) -> int:
        return min((m.deck.standing or 999) for m in self.members)


def _visit_order(items: list[ResolvedDeck]) -> list[ResolvedDeck]:
    """Best finish first, then by id - so the seed of each cluster is its best list."""
    return sorted(items, key=lambda i: (i.deck.standing or 999, i.deck.deck_id))


def cluster_decks(items: list[ResolvedDeck], threshold: float = DEFAULT_THRESHOLD) -> list[Cluster]:
    clusters: list[Cluster] = []

    for item in _visit_order(items):
        counts = deck_counts(item)
        best, best_score = None, 0.0
        for cluster in clusters:
            score = similarity(counts, cluster.centroid)
            if score > best_score:
                best, best_score = cluster, score

        if best is not None and best_score >= threshold:
            best.add(item, counts)
        else:
            fresh = Cluster()
            fresh.add(item, counts)
            clusters.append(fresh)

    return _merge_pass(clusters, threshold)


def _merge_pass(clusters: list[Cluster], threshold: float) -> list[Cluster]:
    """Collapse clusters whose centroids sit above the threshold.

    Leader clustering depends on visit order; this removes it. Repeated until no
    pair merges, which terminates because every merge reduces the cluster count.
    """
    merged = True
    while merged and len(clusters) > 1:
        merged = False
        for i in range(len(clusters)):
            for j in range(i + 1, len(clusters)):
                if similarity(clusters[i].centroid, clusters[j].centroid) >= threshold:
                    clusters[i].absorb(clusters[j])
                    del clusters[j]
                    merged = True
                    break
            if merged:
                break

    clusters.sort(key=lambda c: (-len(c.members), c.best_standing))
    return clusters


def _inclusion(counts_list: list[Counter]) -> dict[str, float]:
    """Share of lists running at least one copy of each card."""
    total = len(counts_list) or 1
    seen: Counter = Counter()
    for counts in counts_list:
        for name in counts:
            seen[name] += 1
    return {name: value / total for name, value in seen.items()}


def _cards_in(cluster: Cluster) -> dict:
    """Name -> Card, for every card the cluster's lists play."""
    lookup = {}
    for member in cluster.members:
        for card, _count in member.entries:
            lookup.setdefault(card.name, card)
    return lookup


def signature_cards(cluster: Cluster, siblings: list[Cluster], limit: int = 4) -> list[dict]:
    """Cards that separate this cluster from the rest of its ink pair.

    Ranked first by how much more often the cluster runs a card than everyone else
    in the pair - that is what lets a player recognise the deck across the table,
    rather than the cards every list in the pair plays.

    When several cards are equally exclusive (common, since an archetype's core is
    all-or-nothing), the tie goes to the card a player would name the deck after:
    a character over a spell, then the expensive end over the cheap, then the card
    run in the most copies. Alphabetical order was the previous tie-break, which is
    how a control deck ended up called "Agustin Madrigal".
    """
    inside = _inclusion(cluster.counts)
    outside_counts = [c for sibling in siblings if sibling is not cluster for c in sibling.counts]
    outside = _inclusion(outside_counts) if outside_counts else {}
    lookup = _cards_in(cluster)

    copies: Counter = Counter()
    for counts in cluster.counts:
        copies.update(counts)
    lists = len(cluster.counts) or 1

    rows = []
    for name, share in inside.items():
        if share < SIGNATURE_MIN_INCLUSION:
            continue
        edge = share - outside.get(name, 0.0)
        if outside_counts and edge < SIGNATURE_MIN_EDGE:
            continue
        card = lookup.get(name)
        rows.append(
            {
                "name": name,
                "inclusion": round(100 * share, 1),
                "elsewhere": round(100 * outside.get(name, 0.0), 1),
                "edge": round(100 * edge, 1),
                "avg_copies": round(copies[name] / lists, 2),
                "cost": card.cost if card else None,
                "is_character": bool(card and card.base_type == "Character"),
            }
        )

    rows.sort(
        key=lambda r: (
            -r["edge"],
            not r["is_character"],
            -(r["cost"] or 0),
            -r["avg_copies"],
            r["name"],
        )
    )
    return rows[:limit]


def label_for(signature: list[dict], fallback: str) -> str:
    """Name a cluster after the cards that distinguish it.

    A deck named by its own contents survives the fact that no two players name it
    the same way. `fallback` is used when nothing separates the cluster - which
    happens when the ink pair holds exactly one archetype.
    """
    if not signature:
        return fallback
    # "Elsa - Snow Queen" reads as "Elsa" in a deck name.
    short = [row["name"].split(" - ")[0] for row in signature[:2]]
    unique = list(dict.fromkeys(short))
    return " + ".join(unique)


def deck_names(cluster: Cluster, limit: int = 6) -> list[dict]:
    """The names players gave these lists - reference only, never used to group."""
    names: Counter = Counter(
        (m.deck.deck_name or "").strip()
        for m in cluster.members
        if (m.deck.deck_name or "").strip()
    )
    # Sorted, not most_common(): Counter keeps insertion order for ties, which would
    # make the displayed order depend on which event was fetched first.
    ordered = sorted(names.items(), key=lambda item: (-item[1], item[0]))
    return [{"name": name, "count": count} for name, count in ordered[:limit]]
