"""Decklist parsing.

TopDeck returns a decklist either as a structured ``deckObj`` or as free text
pasted by the player, so both shapes have to work. Every deck builder in the
Lorcana ecosystem formats text slightly differently; the line parser below is
deliberately forgiving and reports what it could not read instead of guessing.
"""

from __future__ import annotations

import re

from .models import DeckCard

# "4 Elsa - Snow Queen", "4x Elsa - Snow Queen", "Elsa - Snow Queen x4"
_LEADING_COUNT = re.compile(r"^\s*(\d{1,2})\s*[xX]?[\s.)-]+(.*)$")
_TRAILING_COUNT = re.compile(r"^(.*?)\s+[xX](\d{1,2})\s*$")
# Section headers a paste often carries: "Characters (47)", "~~Mainboard~~", "Deck:"
_HEADER = re.compile(
    r"^\s*(?:~~.*~~|\**\s*(?:main\s*deck|mainboard|deck|characters?|actions?|songs?|items?|locations?|sideboard|total)\b.*)\s*$",
    re.IGNORECASE,
)
# Trailing set/collector annotations: "(TFC) 42", "(TFC 42)", "[ROF]", "#123"
_ANNOTATION = re.compile(r"\s*(?:\((?:[A-Za-z0-9 ]{2,12})\)|\[[^\]]{1,16}\]|#\d+)\s*$")


#: A bare trailing collector number, e.g. "Elsa - Snow Queen 42".
_TRAILING_NUMBER = re.compile(r"\s+\d{1,3}$")


def _clean_name(name: str) -> str:
    """Strip the trailing bookkeeping deck builders append to a card name.

    Both patterns are applied until the name stops changing, because they stack:
    ``Mickey Mouse - Brave Little Tailor (TFC) 42`` needs the number gone before
    the set code is at the end to be seen.
    """
    name = name.strip().strip("*").strip()
    previous = None
    while previous != name:
        previous = name
        name = _ANNOTATION.sub("", name).strip()
        name = _TRAILING_NUMBER.sub("", name).strip()
    return name


def parse_decklist_text(text: str) -> list[DeckCard]:
    """Parse a pasted decklist into card lines, skipping headers and noise."""
    cards: dict[str, int] = {}
    for raw_line in (text or "").splitlines():
        line = raw_line.strip()
        if not line or _HEADER.match(line):
            continue

        count: int | None = None
        name = line

        match = _LEADING_COUNT.match(line)
        if match:
            count, name = int(match.group(1)), match.group(2)
        else:
            match = _TRAILING_COUNT.match(line)
            if match:
                name, count = match.group(1), int(match.group(2))

        if count is None or not (1 <= count <= 20):
            continue

        name = _clean_name(name)
        if len(name) < 3:
            continue
        cards[name] = cards.get(name, 0) + count

    return [DeckCard(name=n, count=c) for n, c in cards.items()]


def parse_deck_obj(obj: dict) -> list[DeckCard]:
    """Parse TopDeck's structured ``deckObj``.

    Shape varies by game and import source, so accept both
    ``{"Mainboard": {"Card": 4}}`` and ``{"Mainboard": {"Card": {"count": 4}}}``,
    and ignore non-mainboard buckets (Lorcana has no sideboard in constructed).
    """
    cards: dict[str, int] = {}
    if not isinstance(obj, dict):
        return []

    buckets = [v for k, v in obj.items() if isinstance(v, dict) and k.lower() != "sideboard"]
    if not buckets:
        buckets = [obj]

    for bucket in buckets:
        for name, value in bucket.items():
            if isinstance(value, dict):
                count = value.get("count", value.get("qty", value.get("quantity")))
            else:
                count = value
            try:
                count = int(count)
            except (TypeError, ValueError):
                continue
            if 1 <= count <= 20:
                clean = _clean_name(str(name))
                if len(clean) >= 3:
                    cards[clean] = cards.get(clean, 0) + count

    return [DeckCard(name=n, count=c) for n, c in cards.items()]


def extract_cards(standing: dict) -> list[DeckCard]:
    """Pull a card list out of one TopDeck standing entry, structured shape first."""
    for key in ("deckObj", "deckobj", "deck_obj"):
        if isinstance(standing.get(key), dict):
            cards = parse_deck_obj(standing[key])
            if cards:
                return cards

    raw = standing.get("decklist")
    if isinstance(raw, dict):
        cards = parse_deck_obj(raw)
        if cards:
            return cards
    if isinstance(raw, str):
        return parse_decklist_text(raw)
    return []
