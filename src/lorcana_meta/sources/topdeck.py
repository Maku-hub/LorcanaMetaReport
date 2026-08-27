"""TopDeck.gg tournament source.

API docs: https://topdeck.gg/docs/tournaments-v2
Keys are free from https://topdeck.gg/developers.

Two obligations that come with the API and are honoured elsewhere in this repo:
  * a visible credit + link back to TopDeck.gg (rendered in the site footer), and
  * the documented rate limit of ~100 requests/minute (we make one request per
    month of the requested window, well under it).
"""

from __future__ import annotations

import logging
import os
import time
from datetime import date, datetime, timedelta, timezone

import requests

from ..decklist import extract_cards
from ..models import Deck
from .base import SourceError

log = logging.getLogger(__name__)

API_URL = "https://topdeck.gg/api/v2/tournaments"
GAME = "Disney Lorcana"
#: Case-sensitive, as documented.
FORMATS = ("Core Constructed", "Infinity Constructed", "Sealed", "Pack Rush")
COLUMNS = ["name", "id", "decklist", "deckObj", "standing", "wins", "losses", "draws"]


def _unix(day: date) -> int:
    return int(datetime(day.year, day.month, day.day, tzinfo=timezone.utc).timestamp())


def _month_windows(start: date, end: date):
    """Split a date range into <=31-day windows so no single query is a bulk query."""
    cursor = start
    while cursor <= end:
        stop = min(cursor + timedelta(days=30), end)
        yield cursor, stop
        cursor = stop + timedelta(days=1)


class TopdeckSource:
    name = "topdeck.gg"
    attribution = "Tournament data by TopDeck.gg"
    attribution_url = "https://topdeck.gg"

    def __init__(
        self,
        api_key: str | None = None,
        *,
        fmt: str = "Core Constructed",
        min_players: int | None = None,
        timeout: int = 60,
    ) -> None:
        self.api_key = api_key or os.environ.get("TOPDECK_API_KEY", "")
        if not self.api_key:
            raise SourceError(
                "No TopDeck API key. Get a free one at https://topdeck.gg/developers "
                "and export it as TOPDECK_API_KEY."
            )
        if fmt not in FORMATS:
            raise SourceError(f"Unknown format {fmt!r}; expected one of {FORMATS}")
        self.fmt = fmt
        self.min_players = min_players
        self.timeout = timeout
        self._session = requests.Session()
        self._session.headers.update(
            {
                "Authorization": self.api_key,
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "lorcana-meta/0.1",
            }
        )

    # -- fetching --------------------------------------------------------------

    def fetch(self, start: date, end: date) -> list[Deck]:
        decks: list[Deck] = []
        windows = list(_month_windows(start, end))
        for index, (window_start, window_end) in enumerate(windows):
            if index:
                time.sleep(1.0)  # stay comfortably inside the documented rate limit
            payload = self._query(window_start, window_end)
            log.info(
                "topdeck: %s..%s -> %d tournaments",
                window_start,
                window_end,
                len(payload),
            )
            for tournament in payload:
                decks.extend(self._decks_from_tournament(tournament))
        return decks

    def _query(self, start: date, end: date) -> list[dict]:
        body = {
            "game": GAME,
            "format": self.fmt,
            "start": _unix(start),
            "end": _unix(end + timedelta(days=1)),
            "columns": COLUMNS,
        }
        if self.min_players:
            body["participantMin"] = self.min_players

        for attempt in range(4):
            response = self._session.post(API_URL, json=body, timeout=self.timeout)
            if response.status_code == 429:
                wait = float(response.headers.get("Retry-After", 5 * (attempt + 1)))
                log.warning("topdeck: rate limited, sleeping %.0fs", wait)
                time.sleep(wait)
                continue
            if response.status_code in (401, 403):
                raise SourceError(
                    f"TopDeck rejected the API key ({response.status_code}). "
                    "Check TOPDECK_API_KEY."
                )
            if response.status_code >= 500:
                time.sleep(2 * (attempt + 1))
                continue
            response.raise_for_status()
            payload = response.json()
            if isinstance(payload, dict):
                payload = payload.get("data") or payload.get("tournaments") or []
            return payload if isinstance(payload, list) else []

        raise SourceError("TopDeck: giving up after repeated rate limits / 5xx")

    # -- shaping ---------------------------------------------------------------

    def _decks_from_tournament(self, tournament: dict) -> list[Deck]:
        tid = str(tournament.get("TID") or tournament.get("tid") or "")
        started = tournament.get("startDate")
        try:
            day = datetime.fromtimestamp(int(started), tz=timezone.utc).date().isoformat()
        except (TypeError, ValueError):
            day = ""

        standings = tournament.get("standings") or []
        players = tournament.get("playerCount") or len(standings) or None

        decks: list[Deck] = []
        for entry in standings:
            if not isinstance(entry, dict):
                continue
            cards = extract_cards(entry)
            if not cards:
                continue  # a standing without a submitted decklist tells us nothing

            player_id = str(entry.get("id") or entry.get("name") or len(decks))
            decks.append(
                Deck(
                    source=self.name,
                    deck_id=f"{tid}:{player_id}",
                    player=str(entry.get("name") or "Unknown"),
                    # Not a documented column, so read it opportunistically. It is
                    # display-only anyway: archetypes come from card overlap.
                    deck_name=str(
                        entry.get("deckName") or entry.get("deck_name") or entry.get("archetype") or ""
                    ),
                    cards=cards,
                    standing=_int(entry.get("standing")),
                    wins=_int(entry.get("wins")),
                    losses=_int(entry.get("losses")),
                    draws=_int(entry.get("draws")),
                    tournament_id=tid,
                    tournament_name=str(tournament.get("tournamentName") or "Unknown event"),
                    tournament_date=day,
                    tournament_players=players,
                    top_cut=_int(tournament.get("topCut")),
                    fmt=str(tournament.get("format") or self.fmt),
                    url=f"https://topdeck.gg/event/{tid}" if tid else "",
                )
            )
        return decks


def _int(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
