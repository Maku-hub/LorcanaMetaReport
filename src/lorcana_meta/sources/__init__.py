"""Deck sources.

A source turns "give me tournament decks between these two dates" into a list of
:class:`~lorcana_meta.models.Deck`. Keeping this behind one small interface means a
new data provider is a new file here and nothing else changes.
"""

from .base import DeckSource, SourceError
from .inkdecks import InkdecksSource
from .local import LocalSource
from .topdeck import TopdeckSource

SOURCES = {
    "topdeck": TopdeckSource,
    "local": LocalSource,
    "inkdecks": InkdecksSource,
}

__all__ = [
    "DeckSource",
    "SourceError",
    "InkdecksSource",
    "LocalSource",
    "TopdeckSource",
    "SOURCES",
]
