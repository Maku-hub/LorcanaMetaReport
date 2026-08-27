"""Card database.

Source: https://lorcana-api.com/ - free, open source, no key required. One bulk
endpoint returns every printing, so we fetch it once and cache it on disk.
"""

from __future__ import annotations

import json
import time
import unicodedata
from pathlib import Path

import requests

from .models import INKS, Card

CARDS_URL = "https://api.lorcana-api.com/cards/all"
DEFAULT_CACHE = Path(".cache/cards.json")
CACHE_TTL_SECONDS = 24 * 3600
USER_AGENT = "lorcana-meta/0.1 (+https://github.com/)"


def normalize_name(name: str) -> str:
    """Fold a card name to a comparison key.

    Decklists arrive from a dozen deck builders, so the same card shows up as
    ``Elsa - Snow Queen``, ``Elsa – Snow Queen`` (en dash), ``Elsa - Snow Queen (TFC 42)``
    or with a curly apostrophe. Strip everything that isn't a letter or digit.

    The browser does the same folding in ``site/assets/app.js`` so a list pasted
    into the site matches the same cards - keep the two in step, ASCII
    alphanumerics only, if you change either.
    """
    s = unicodedata.normalize("NFKD", name)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = s.casefold()
    kept = [ch if ("a" <= ch <= "z" or "0" <= ch <= "9") else " " for ch in s]
    return " ".join("".join(kept).split())


def _parse_inks(color: str) -> tuple[str, ...]:
    """``"Amethyst, Sapphire"`` -> ``("amethyst", "sapphire")``, in canonical order."""
    parts = [p.strip().casefold() for p in (color or "").split(",")]
    inks = [p for p in parts if p in INKS]
    return tuple(sorted(set(inks), key=INKS.index))


def _as_int(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


class CardIndex:
    """Name -> Card lookup, tolerant about how decklists spell things."""

    def __init__(self, cards: list[Card]) -> None:
        self.cards = cards
        self._by_key: dict[str, Card] = {}
        # Fallback index on the part before the " - " (a character's name without its
        # version). Only usable when exactly one card matches, which we track here.
        base_hits: dict[str, list[Card]] = {}

        for card in cards:
            key = normalize_name(card.name)
            # Later sets reprint the same name; first printing wins, they are identical
            # for meta purposes and the first is the one players name.
            self._by_key.setdefault(key, card)
            base = card.name.split(" - ")[0]
            if base != card.name:
                base_hits.setdefault(normalize_name(base), []).append(card)

        self._by_base = {k: v[0] for k, v in base_hits.items() if len({c.name for c in v}) == 1}

    def __len__(self) -> int:
        return len(self.cards)

    def get(self, name: str) -> Card | None:
        key = normalize_name(name)
        card = self._by_key.get(key)
        if card is not None:
            return card
        return self._by_base.get(key)

    # -- loading ---------------------------------------------------------------

    @classmethod
    def load(
        cls,
        cache: Path | str = DEFAULT_CACHE,
        *,
        refresh: bool = False,
        timeout: int = 120,
    ) -> "CardIndex":
        cache = Path(cache)
        raw = None
        if cache.exists() and not refresh:
            age = time.time() - cache.stat().st_mtime
            if age < CACHE_TTL_SECONDS:
                raw = json.loads(cache.read_text(encoding="utf-8"))

        if raw is None:
            raw = cls._download(timeout=timeout)
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text(json.dumps(raw), encoding="utf-8")

        return cls([cls._to_card(entry) for entry in raw])

    @staticmethod
    def _download(*, timeout: int) -> list[dict]:
        response = requests.get(
            CARDS_URL, timeout=timeout, headers={"User-Agent": USER_AGENT}
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list):
            raise ValueError(f"unexpected card payload of type {type(payload).__name__}")
        return payload

    @staticmethod
    def _to_card(entry: dict) -> Card:
        return Card(
            name=(entry.get("Name") or "").strip(),
            inks=_parse_inks(entry.get("Color", "")),
            cost=_as_int(entry.get("Cost")),
            type=(entry.get("Type") or "").strip(),
            inkable=bool(entry.get("Inkable")),
            lore=_as_int(entry.get("Lore")),
            strength=_as_int(entry.get("Strength")),
            willpower=_as_int(entry.get("Willpower")),
            text=(entry.get("Body_Text") or "").strip(),
            image=(entry.get("Image") or "").strip(),
            set_id=(entry.get("Set_ID") or "").strip(),
            set_name=(entry.get("Set_Name") or "").strip(),
            unique_id=(entry.get("Unique_ID") or "").strip(),
            rarity=(entry.get("Rarity") or "").strip(),
        )
