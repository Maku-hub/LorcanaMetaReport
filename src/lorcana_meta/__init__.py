"""Lorcana tournament-meta aggregator.

Pulls tournament standings and decklists for a date window, resolves card names
against a public card database (lorcana-api.com), groups the decks by what is in
them, and writes a single JSON artefact that the page in ``site/`` renders.
"""

__version__ = "1.0.0"
