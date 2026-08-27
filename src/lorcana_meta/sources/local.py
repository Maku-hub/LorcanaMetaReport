"""Local deck source.

Reads decks from files you control - your own tournament notes, lists a friend
sent you, or lists you are allowed to redistribute. Useful for two things: running
the whole pipeline before you have an API key, and mixing local events that no
online platform covers into the published meta.

Two file shapes are accepted in ``data/decks/``:

``*.json`` - one deck object, or a list of them::

    {"player": "Ada", "standing": 3, "tournament_name": "Store Champs",
     "tournament_date": "2026-08-12", "tournament_players": 34,
     "cards": [{"name": "Elsa - Snow Queen", "count": 4}]}

``*.txt`` - ``key: value`` header lines, a blank line, then a pasted decklist::

    player: Ada
    standing: 3
    tournament_name: Store Champs
    tournament_date: 2026-08-12
    tournament_players: 34

    4 Elsa - Snow Queen
    3 Hades - Lord of the Underworld
"""

from __future__ import annotations

import json
import logging
import re
from datetime import date
from pathlib import Path

from ..decklist import parse_decklist_text
from ..models import Deck, DeckCard
from .base import SourceError

log = logging.getLogger(__name__)

_INT_FIELDS = ("standing", "wins", "losses", "draws", "tournament_players", "top_cut")
#: Marks a file as a multi-deck paste for tools/import_pasted_decks.py.
_MULTI_DECK_HEADER = re.compile(r"^\s*#{3,}\s*\S", re.MULTILINE)


class LocalSource:
    name = "local"
    attribution = "Decklists supplied locally"
    attribution_url = ""

    def __init__(self, directory: Path | str = "data/decks", *, fmt: str = "Core Constructed") -> None:
        self.directory = Path(directory)
        self.fmt = fmt

    def fetch(self, start: date, end: date) -> list[Deck]:
        if not self.directory.is_dir():
            raise SourceError(f"{self.directory} is not a directory")

        decks: list[Deck] = []
        for path in sorted(self.directory.iterdir()):
            if path.suffix.lower() == ".json":
                decks.extend(self._from_json(path))
            elif path.suffix.lower() == ".txt":
                deck = self._from_txt(path)
                if deck:
                    decks.append(deck)

        kept = [d for d in decks if self._in_range(d, start, end)]
        log.info("local: %d decks in %s, %d inside the window", len(decks), self.directory, len(kept))
        return kept

    @staticmethod
    def _in_range(deck: Deck, start: date, end: date) -> bool:
        if not deck.tournament_date:
            return True  # undated local notes are always in scope
        try:
            day = date.fromisoformat(deck.tournament_date)
        except ValueError:
            return True
        return start <= day <= end

    # -- readers ---------------------------------------------------------------

    def _from_json(self, path: Path) -> list[Deck]:
        payload = json.loads(path.read_text(encoding="utf-8"))
        entries = payload if isinstance(payload, list) else [payload]
        decks = []
        for index, entry in enumerate(entries):
            cards = [
                DeckCard(name=str(c["name"]), count=int(c["count"]))
                for c in entry.get("cards", [])
                if c.get("name") and c.get("count")
            ]
            if not cards:
                log.warning("local: %s entry %d has no cards, skipped", path.name, index)
                continue
            decks.append(self._build(entry, cards, f"{path.stem}:{index}"))
        return decks

    def _from_txt(self, path: Path) -> Deck | None:
        text = path.read_text(encoding="utf-8")

        # A `###` line means this is a multi-deck paste meant for
        # tools/import_pasted_decks.py. Read as a single deck it would glue every
        # list in the file into one 300-card monster and quietly skew the report,
        # so refuse it and say what to do instead.
        if _MULTI_DECK_HEADER.search(text):
            log.warning(
                "local: %s holds '###' deck headers, so it is importer input rather "
                "than one deck. Convert it first: "
                "python tools/import_pasted_decks.py %s",
                path.name,
                path,
            )
            return None

        header_text, _, list_text = text.partition("\n\n")
        if not list_text.strip():
            header_text, list_text = "", text

        meta: dict[str, object] = {}
        for line in header_text.splitlines():
            key, sep, value = line.partition(":")
            if sep and value.strip():
                meta[key.strip().lower()] = value.strip()

        cards = parse_decklist_text(list_text)
        if not cards:
            log.warning("local: could not read a decklist out of %s", path.name)
            return None
        return self._build(meta, cards, path.stem)

    def _build(self, meta: dict, cards: list[DeckCard], deck_id: str) -> Deck:
        values = {}
        for field in _INT_FIELDS:
            try:
                values[field] = int(meta[field])  # type: ignore[index]
            except (KeyError, TypeError, ValueError):
                values[field] = None

        return Deck(
            source=self.name,
            deck_id=str(meta.get("deck_id") or deck_id),
            player=str(meta.get("player") or "Unknown"),
            deck_name=str(meta.get("deck_name") or meta.get("name") or ""),
            cards=cards,
            tournament_id=str(meta.get("tournament_id") or ""),
            tournament_name=str(meta.get("tournament_name") or "Local event"),
            tournament_date=str(meta.get("tournament_date") or ""),
            fmt=str(meta.get("format") or self.fmt),
            url=str(meta.get("url") or ""),
            **values,
        )
