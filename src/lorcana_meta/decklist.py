"""Decklist parsing.

Every deck builder in the Lorcana ecosystem formats a pasted list slightly
differently, so the line parser below is deliberately forgiving: it reports what it
could not read rather than guessing, and a line it cannot make sense of is skipped
rather than turned into a plausible-looking wrong card.
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
