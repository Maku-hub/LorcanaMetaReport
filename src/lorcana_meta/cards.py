"""Card database.

Source: https://lorcanajson.org/ - free, no key required. One bulk file holds every
card, so it is fetched once and cached on disk.

## Why LorcanaJSON and not lorcana-api.com

lorcana-api.com was the original source and was dropped in October 2026 because it
had stopped keeping up: measured then, it carried 2694 printings across sets 1-13
and **no set 14 at all**, while LorcanaJSON carried 3556 cards across sets 1-14 plus
the three Illumineer's Quest sets. A card the database has never heard of is not a
small gap - see `analyze.resolve_deck` for what a decklist does with one.

An "official Ravensburger API" was considered and rejected: there is no documented
public endpoint for it. What community projects call by that name appears to be
whatever the official app talks to - unversioned, undocumented, with no published
terms. This project rests on written permission and documented terms everywhere
else, and that is not a thing to make an exception for. LorcanaJSON publishes the
same data under Ravensburger's Community Code Policy, which is the same footing
this project stands on, and its image URLs point at Ravensburger's own CDN anyway.

Their site asks callers to prefer the zipped file to save bandwidth, so that is what
is fetched - 1.2 MB instead of roughly 12 MB.
"""

from __future__ import annotations

import io
import json
import time
import unicodedata
import zipfile
from pathlib import Path

import requests

from .models import INKS, Card

CARDS_URL = "https://lorcanajson.org/files/current/en/allCards.json.zip"
DEFAULT_CACHE = Path(".cache/cards.json")
CACHE_TTL_SECONDS = 24 * 3600
USER_AGENT = "lorcana-meta/1.1 (+https://github.com/)"


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
    """``"Amethyst-Sapphire"`` -> ``("amethyst", "sapphire")``, in canonical order.

    LorcanaJSON joins a dual-ink card's colours with a hyphen; the previous source
    used a comma. Both separators are accepted because getting this wrong is silent:
    the card keeps its name and loses its inks, and a dual-ink deck then has no ink
    pair to be counted under.
    """
    parts = [p.strip().casefold() for p in (color or "").replace("-", ",").split(",")]
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
    ) -> CardIndex:
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

        try:
            with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
                names = [n for n in archive.namelist() if n.endswith(".json")]
                if not names:
                    raise ValueError("the archive holds no .json file")
                payload = json.loads(archive.read(names[0]).decode("utf-8"))
        except zipfile.BadZipFile as error:
            raise ValueError(
                f"{CARDS_URL} did not return a zip archive - the download may have "
                f"been truncated or replaced by an error page ({error})"
            ) from error

        cards = payload.get("cards") if isinstance(payload, dict) else None
        if not isinstance(cards, list):
            raise ValueError(
                "unexpected card payload: expected an object with a 'cards' list, got "
                f"{type(payload).__name__}"
            )
        return cards

    @staticmethod
    def _to_card(entry: dict) -> Card:
        images = entry.get("images") or {}
        subtypes = tuple(str(s).strip() for s in (entry.get("subtypes") or []) if s)
        return Card(
            # fullName is "Elsa - Snow Queen", which is how decklists spell it. name
            # alone would be "Elsa", and several Elsas would collapse into one.
            name=(entry.get("fullName") or entry.get("name") or "").strip(),
            inks=_parse_inks(entry.get("color", "")),
            cost=_as_int(entry.get("cost")),
            type=(entry.get("type") or "").strip(),
            subtypes=subtypes,
            # LorcanaJSON spells this "inkwell": whether the card may be inked.
            inkable=bool(entry.get("inkwell")),
            lore=_as_int(entry.get("lore")),
            strength=_as_int(entry.get("strength")),
            willpower=_as_int(entry.get("willpower")),
            text=(entry.get("fullText") or "").strip(),
            # "full" is the card face; there is also a thumbnail and a foil mask.
            image=(images.get("full") or images.get("thumbnail") or "").strip(),
            set_id=str(entry.get("setCode") or "").strip(),
            rarity=(entry.get("rarity") or "").strip(),
        )
