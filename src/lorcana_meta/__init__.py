"""Lorcana tournament-meta aggregator.

Pulls tournament standings + decklists from a legitimate source (TopDeck.gg API),
resolves card names against a public card database (lorcana-api.com) and writes a
single JSON artefact that the static site in ``site/`` renders.
"""

__version__ = "0.1.0"
