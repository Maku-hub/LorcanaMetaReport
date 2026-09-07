"""Domain types. Deliberately plain dataclasses - they get serialised to JSON."""

from __future__ import annotations

from dataclasses import dataclass, field

# Canonical ink order used by Ravensburger. Everything (keys, labels, sort order)
# derives from this tuple so an ink pair always renders in the same direction.
INKS: tuple[str, ...] = ("amber", "amethyst", "emerald", "ruby", "sapphire", "steel")
INK_ORDER = {ink: i for i, ink in enumerate(INKS)}


@dataclass(frozen=True)
class Card:
    """One printed card, as far as the meta analysis cares about it."""

    name: str  # full name as it appears in decklists, e.g. "Elsa - Snow Queen"
    inks: tuple[str, ...]  # 1 ink, or 2 for dual-ink cards
    cost: int | None
    type: str  # Character / Action / Action - Song / Item / Location
    inkable: bool
    lore: int | None
    strength: int | None
    willpower: int | None
    text: str
    image: str
    set_id: str
    rarity: str

    @property
    def is_song(self) -> bool:
        return "song" in self.type.lower()

    @property
    def base_type(self) -> str:
        """`Action - Song` collapses to `Action` for grouping purposes."""
        return self.type.split(" - ")[0].strip() or self.type


@dataclass
class DeckCard:
    """A line of a decklist: how many copies of which card name."""

    name: str
    count: int


@dataclass
class Deck:
    """A single tournament decklist together with how it placed."""

    source: str  # e.g. "inkdecks.com"
    deck_id: str
    player: str
    cards: list[DeckCard] = field(default_factory=list)

    #: Whatever the player called the list. Kept for display only - archetypes are
    #: worked out from card overlap in `lorcana_meta.cluster`, never from names,
    #: because the same deck arrives under a dozen different names.
    deck_name: str = ""

    standing: int | None = None
    #: The placing exactly as the source worded it ("1st", "Top8"). Kept because a
    #: bucket and an exact placing are different claims and `standing` flattens them.
    standing_label: str = ""
    wins: int | None = None
    losses: int | None = None
    draws: int | None = None

    tournament_id: str = ""
    tournament_name: str = ""
    tournament_date: str = ""  # ISO date, "YYYY-MM-DD"
    tournament_players: int | None = None
    top_cut: int | None = None
    fmt: str = ""
    url: str = ""

    @property
    def total_cards(self) -> int:
        return sum(c.count for c in self.cards)


@dataclass
class ResolvedDeck:
    """A deck whose card names have been matched against the card database."""

    deck: Deck
    entries: list[tuple[Card, int]] = field(default_factory=list)
    unknown: list[DeckCard] = field(default_factory=list)
    inks: tuple[str, ...] = ()

    @property
    def pair_key(self) -> str:
        """Stable identifier for the deck's ink identity, e.g. ``amber-amethyst``."""
        return "-".join(self.inks) if self.inks else "unknown"

    @property
    def pair_label(self) -> str:
        return " / ".join(i.capitalize() for i in self.inks) if self.inks else "Unknown"
