"""Generate a synthetic sample of tournament decks.

Why this exists: the pipeline needs a TopDeck API key, and the site needs data to
render. This produces a plausible-looking field so you can run everything end to
end before you have a key, and so the tests have something deterministic to work on.

The card names are real (pulled from the public card database); the decks, players,
placings and events are invented. Output goes to ``data/decks/sample-field.json``
and every deck is stamped so it can never be mistaken for a real result.

Two things about the sample are deliberate, because they are what the analysis has
to cope with in real data:

* Lists inside one archetype share a large core and differ by a handful of flex
  slots - which is what "the same deck with modifications" means in practice, and
  what the clustering has to hold together.
* Two ink pairs carry **two different archetypes each**, and every archetype is
  submitted under several different names. Grouping by name would report those as
  one deck; grouping by contents splits them correctly.

    python tools/generate_sample_decks.py

Delete ``data/decks/sample-field.json`` once you are pulling real tournaments.
"""

from __future__ import annotations

import json
import random
import sys
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lorcana_meta.cards import CardIndex  # noqa: E402
from lorcana_meta.console import configure_output  # noqa: E402
from lorcana_meta.models import INKS  # noqa: E402

SEED = 20260827
OUT = Path("data/decks/sample-field.json")

# Roughly how many of a 60-card list is fixed by the archetype. Real constructed
# lists inside one archetype agree on about this much.
CORE_COPIES = 48

# (inks, how the archetype leans, decks, names players submit it under)
FIELD = [
    (
        ("amber", "amethyst"),
        "cheap",
        12,
        ["Yurple", "A/P Midrange", "yellow purple", "Sample Bounce"],
    ),
    (
        ("amber", "amethyst"),  # same pair, different deck - the case names hide
        "top",
        7,
        ["Samethyst Control", "A/P Big Stuff", "purple ramp"],
    ),
    (("amber", "steel"), "mid", 10, ["Samber", "A/S Aggro", "steel amber tempo"]),
    (
        ("amber", "steel"),
        "song",
        5,
        ["Samber Songs", "A/S Singers", "amber steel sing"],
    ),
    (("ruby", "sapphire"), "mid", 9, ["Rusa", "R/S Midrange", "ruby sapphire"]),
    (("emerald", "steel"), "cheap", 8, ["Greensteel", "E/S Aggro", "emerald steel"]),
    (("amethyst", "steel"), "top", 6, ["Amethyst Steel", "A/S Ramp"]),
    (("ruby", "amethyst"), "mid", 5, ["Rurple", "R/A Tempo"]),
    (("amber", "emerald"), "cheap", 4, ["Ambrald", "A/E Aggro"]),
]

EVENTS = [
    ("Sample Regional Qualifier", 128, 8),
    ("Sample Store Championship", 42, 8),
    ("Sample Weekly Constructed", 24, 4),
    ("Sample Set Championship", 210, 16),
]

PLAYERS = [
    "A. Sample", "B. Fixture", "C. Placeholder", "D. Dummy", "E. Example",
    "F. Synthetic", "G. Mock", "H. Testcase", "I. Filler", "J. Stub",
    "K. Demo", "L. Draft", "M. Sketch", "N. Trial", "O. Proxy",
]


def pick_pool(index: CardIndex, inks: tuple[str, str]) -> dict[str, list[str]]:
    """Split a pair's legal cards into cheap / mid / expensive / song buckets."""
    buckets: dict[str, list[str]] = defaultdict(list)
    allowed = set(inks)

    for card in index.cards:
        if not card.inks or not set(card.inks) <= allowed:
            continue
        if card.set_id in ("", "AOV"):  # skip the newest set: thin data, and promos
            continue
        if card.cost is None:
            continue
        if card.is_song:
            buckets["song"].append(card.name)
        elif card.cost <= 2:
            buckets["cheap"].append(card.name)
        elif card.cost <= 4:
            buckets["mid"].append(card.name)
        else:
            buckets["top"].append(card.name)

    for names in buckets.values():
        names.sort()
    return buckets


def build_archetype(rng: random.Random, pool: dict[str, list[str]], leans: str):
    """A fixed core plus a small flex pool - the shape a real archetype has.

    ``leans`` tilts which bucket the core is drawn from, so two archetypes in the
    same ink pair end up genuinely different lists rather than reshuffles.
    """
    weights = {
        "cheap": {"cheap": 7, "mid": 4, "top": 1, "song": 0},
        "mid": {"cheap": 3, "mid": 6, "top": 3, "song": 0},
        "top": {"cheap": 2, "mid": 3, "top": 6, "song": 1},
        "song": {"cheap": 3, "mid": 3, "top": 2, "song": 4},
    }[leans]

    core: list[str] = []
    for bucket, count in weights.items():
        names = pool.get(bucket, [])
        core += rng.sample(names, min(count, len(names)))
    rng.shuffle(core)

    # The flex pool is small and archetype-specific: pilots pick from the same
    # short list of options, they do not each invent 12 cards.
    everything = [n for b in ("cheap", "mid", "top", "song") for n in pool.get(b, [])]
    candidates = [n for n in everything if n not in core]
    flex = rng.sample(candidates, min(10, len(candidates)))
    return core, flex


def build_deck(rng: random.Random, core: list[str], flex: list[str]):
    """One pilot's list: the archetype's core, then their own flex slots."""
    cards: dict[str, int] = {}

    for name in core:
        if sum(cards.values()) >= CORE_COPIES:
            break
        copies = 4 if rng.random() > 0.2 else rng.choice((2, 3))
        cards[name] = min(copies, CORE_COPIES - sum(cards.values()))

    order = flex[:]
    rng.shuffle(order)
    for name in order:
        remaining = 60 - sum(cards.values())
        if remaining <= 0:
            break
        cards[name] = min(rng.choice((1, 2, 2, 3, 4)), remaining)

    # Top the list up on the core if the flex slots ran out early.
    for name in core:
        remaining = 60 - sum(cards.values())
        if remaining <= 0:
            break
        if cards.get(name, 0) < 4:
            cards[name] = cards.get(name, 0) + min(4 - cards.get(name, 0), remaining)

    return [{"name": name, "count": count} for name, count in cards.items() if count]


def main() -> int:
    configure_output()
    rng = random.Random(SEED)
    index = CardIndex.load()
    today = date.today()
    pools: dict[tuple, dict] = {}

    decks = []
    for inks, leans, wanted, names in FIELD:
        if not set(inks) <= set(INKS):
            raise SystemExit(f"bad ink pair {inks}")
        pool = pools.setdefault(inks, pick_pool(index, inks))  # type: ignore[arg-type]
        core, flex = build_archetype(rng, pool, leans)

        for _ in range(wanted):
            event, players, top_cut = rng.choice(EVENTS)
            standing = rng.randint(1, min(32, top_cut * 4))
            wins = max(0, 7 - (standing // 5) - rng.randint(0, 1))
            decks.append(
                {
                    "player": rng.choice(PLAYERS),
                    # Every list in this archetype gets one of its several names, so
                    # the report has to reconcile them from contents.
                    "deck_name": rng.choice(names),
                    "standing": standing,
                    "wins": wins,
                    "losses": max(0, 7 - wins - 1),
                    "draws": 0,
                    "tournament_name": event,
                    "tournament_id": f"sample-{event.lower().replace(' ', '-')}",
                    "tournament_date": (today - timedelta(days=rng.randint(1, 28))).isoformat(),
                    "tournament_players": players,
                    "top_cut": top_cut,
                    "format": "Core Constructed",
                    "note": "SYNTHETIC SAMPLE DATA - not a real tournament result",
                    "cards": build_deck(rng, core, flex),
                }
            )

    rng.shuffle(decks)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(decks, ensure_ascii=False, indent=1), encoding="utf-8")

    pairs = len({inks for inks, _, _, _ in FIELD})
    print(
        f"wrote {OUT} - {len(decks)} synthetic decks, "
        f"{len(FIELD)} archetypes across {pairs} ink pairs"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
