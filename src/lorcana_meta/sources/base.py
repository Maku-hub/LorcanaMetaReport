from __future__ import annotations

from datetime import date
from typing import Protocol

from ..models import Deck


class SourceError(RuntimeError):
    """A source could not produce data (bad credentials, upstream failure, ...)."""


class DeckSource(Protocol):
    """Everything a deck provider has to offer."""

    #: Short identifier stamped onto every deck, e.g. ``"topdeck.gg"``.
    name: str
    #: Human-readable credit rendered in the site footer.
    attribution: str
    #: Link that the credit points at.
    attribution_url: str
    #: False when the licence or permission covering this data forbids publishing a
    #: report built from it. Propagates into the report, where tests/check_report.py
    #: turns it into a hard failure so the Pages workflow cannot deploy it.
    publishable: bool

    def fetch(self, start: date, end: date) -> list[Deck]:
        ...
