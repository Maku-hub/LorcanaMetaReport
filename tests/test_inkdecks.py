"""Tests for the inkdecks source.

Everything here runs against saved HTML in `tests/fixtures/` - no network. That is
the point: these are the tests that tell you their markup changed, and they have to
work when you have no permission, no key and no connection.

The consent gate gets a test too. It is the difference between a source you may run
and one you may not, and "it still worked after I refactored the constructor" is not
something to find out in production.
"""

from __future__ import annotations

import io
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lorcana_meta.console import configure_output  # noqa: E402
from lorcana_meta.sources import SourceError  # noqa: E402
from lorcana_meta.sources.inkdecks import (  # noqa: E402
    LOCK_STALE_AFTER,
    InkdecksSource,
    max_page,
    parse_deck_page,
    parse_index_page,
    parse_standing,
)

FIXTURES = ROOT / "tests" / "fixtures"
FAILURES: list[str] = []


def check(condition, message):
    if not condition:
        FAILURES.append(message)


def fixture(name: str) -> str:
    return io.open(FIXTURES / name, encoding="utf-8").read()


# ------------------------------------------------------------------ placings

def test_parse_standing():
    for text, expected in (
        ("1st", 1),
        ("2nd", 2),
        ("3rd", 3),
        ("20th", 20),
        ("Top8", 8),
        ("Top16", 16),
        ("Top32", 32),
        ("top 4", 4),
    ):
        number, label = parse_standing(text)
        check(number == expected, f"{text!r} -> {expected}, got {number}")
        check(label == text.strip(), f"{text!r} keeps its label, got {label!r}")

    check(parse_standing("") == (None, ""), "empty stays empty")
    check(parse_standing("Swiss") == (None, "Swiss"), "an unparseable label is kept as-is")


def test_bucket_becomes_its_upper_bound():
    """A bucket must never read as better than it was.

    "Top8" means "no worse than 8th". Mapping it to 8 keeps it comparable with an
    exact placing while never overstating the result - mapping it to 1 would make
    every Top8 deck look like a winner.
    """
    check(parse_standing("Top8")[0] == 8, "Top8 is 8, not 1")
    check(parse_standing("Top32")[0] == 32, "Top32 is 32")
    check(parse_standing("Top8")[0] > parse_standing("3rd")[0], "a 3rd beats a Top8 bucket")


# -------------------------------------------------------------- listing page

def test_parse_index_page():
    stubs = parse_index_page(fixture("inkdecks-list.html"))
    check(len(stubs) == 3, f"three rows in the fixture, got {len(stubs)}")
    if not stubs:
        return

    first = stubs[0]
    check(first["deck_id"] == "521488", f"deck id: {first['deck_id']}")
    check(
        first["path"] == "/lorcana-metagame/deck-justallgoodcard-521488",
        f"path stripped of the host: {first['path']}",
    )
    check(first["deck_name"] == "JustAllGoodCard", f"deck name: {first['deck_name']!r}")
    check(first["player"] == "NotXavierNotCedTo", f"player: {first['player']!r}")
    check(first["standing"] == 16 and first["standing_label"] == "Top16", "placing")
    check(
        (first["wins"], first["losses"], first["draws"]) == (5, 2, 0),
        f"record: {first['wins']}-{first['losses']}-{first['draws']}",
    )
    check(first["inks"] == ["amber", "amethyst"], f"inks: {first['inks']}")
    check(first["archetype"] == "Midrange", f"archetype: {first['archetype']!r}")
    check(first["date"] == "2026-08-23", f"date: {first['date']}")
    check(first["players"] == 97, f"attendance: {first['players']}")
    check(
        first["tournament_name"] == "L'INKcroyable cause 2k",
        f"event name without the organiser or attendance: {first['tournament_name']!r}",
    )


def test_index_page_reads_every_row_fully():
    """No row may come back half-parsed - a missing field is a silent data gap."""
    stubs = parse_index_page(fixture("inkdecks-list.html"))
    for stub in stubs:
        for field in ("deck_id", "path", "deck_name", "player", "tournament_name", "date"):
            check(stub[field], f"{stub.get('deck_id')}: {field} is empty")
        check(stub["standing"] is not None, f"{stub['deck_id']}: no placing")
        check(1 <= len(stub["inks"]) <= 2, f"{stub['deck_id']}: inks are {stub['inks']}")


def test_ink_symbols_do_not_leak_other_images():
    """The ink cell sits next to set icons and star ratings; only inks may match."""
    from lorcana_meta.models import INKS

    for stub in parse_index_page(fixture("inkdecks-list.html")):
        for ink in stub["inks"]:
            check(ink in INKS, f"{ink!r} is not an ink")
        check(len(set(stub["inks"])) == len(stub["inks"]), f"duplicate inks: {stub['inks']}")


def test_max_page_reads_escaped_pager_links():
    """The bug this test exists for.

    Pager links come out of the template HTML-escaped, so the character before
    "page=" is ";" in "&amp;page=2", not "&". A regex looking for [?&]page= matched
    nothing, max_page() returned 1, and every build stopped after the first 20 of
    369 decks. Nothing raised; the report was just wrong and looked fine.

    The previous version of this test asserted `>= 1`, which passes when the
    function finds nothing at all. Assert the number.
    """
    escaped = (
        '<a href="/lorcana-decks/core?deck_type=tournament&amp;rank=top32&amp;page=2">2</a>'
        '<a href="/lorcana-decks/core?deck_type=tournament&amp;rank=top32&amp;page=7">7</a>'
        '<a href="/lorcana-decks/core?deck_type=tournament&amp;rank=top32&amp;page=19">19</a>'
    )
    check(max_page(escaped) == 19, f"escaped links: expected 19, got {max_page(escaped)}")

    plain = '<a href="/lorcana-decks?page=4">4</a><a href="/lorcana-decks?page=12">12</a>'
    check(max_page(plain) == 12, f"unescaped links: expected 12, got {max_page(plain)}")

    check(max_page("<html>no pager here</html>") == 1, "no pager means one page")
    check(max_page("") == 1, "empty input means one page")


def test_max_page_on_the_real_fixture():
    pages = max_page(fixture("inkdecks-list.html"))
    check(pages > 1, f"the fixture's pager spans several pages, got {pages}")


def test_total_decks():
    from lorcana_meta.sources.inkdecks import total_decks

    check(total_decks("<h1>369 decks</h1>") == 369, "a plain count")
    check(total_decks("<h1>1,234 decks</h1>") == 1234, "a thousands separator")
    check(total_decks("<h1>Lorcana Top Decks</h1>") is None, "no count is None, not 0")


def test_completeness_check_warns_on_truncation(capture_logs=None):
    """A partial field must announce itself rather than look like a small meta."""
    import logging

    records = []

    class Collect(logging.Handler):
        def emit(self, record):
            records.append(record.getMessage())

    from lorcana_meta.sources import inkdecks as module

    handler = Collect()
    module.log.addHandler(handler)
    try:
        InkdecksSource._check_completeness(20, 369, 1)
        check(any("20 of the 369" in m for m in records), f"warned: {records}")

        records.clear()
        InkdecksSource._check_completeness(369, 369, 19)
        check(not records, f"a complete fetch is silent: {records}")

        records.clear()
        InkdecksSource._check_completeness(360, 369, 19)
        check(not records, f"a 2% drift is not worth a warning: {records}")

        records.clear()
        InkdecksSource._check_completeness(20, None, 1)
        check(not records, "no reported total means nothing to compare against")
    finally:
        module.log.removeHandler(handler)


# ----------------------------------------------------------------- deck page

#: The fixture is a four-row excerpt; see tests/fixtures/README.md.
FIXTURE_DECK_ROWS = {
    "Eilonwy - Princess of Llyr": 3,
    "Luisa Madrigal - Pushing Through": 3,
    "Rafiki - Mystical Fighter": 2,
    "Grandmother Willow - Ancient Advisor": 4,
}


def test_parse_deck_page():
    cards = parse_deck_page(fixture("inkdecks-deck.html"))
    by_name = {card.name: card.count for card in cards}

    check(
        by_name == FIXTURE_DECK_ROWS,
        f"every row read exactly, with the section header skipped: {by_name}",
    )


def test_deck_page_names_are_joined_cleanly():
    """The name is split across a <b> for the character and text for the version.

    Joining those carelessly gives "Eilonwy -Princess of Llyr" or a doubled space,
    and then nothing matches the card database - which shows up as a silently
    smaller report, not an error.
    """
    for card in parse_deck_page(fixture("inkdecks-deck.html")):
        check("  " not in card.name, f"double space in {card.name!r}")
        check(card.name == card.name.strip(), f"untrimmed: {card.name!r}")
        check(not card.name.endswith("-"), f"trailing dash: {card.name!r}")
        check(" -" not in card.name or " - " in card.name, f"dash spacing: {card.name!r}")


def test_deck_page_without_a_decklist():
    check(parse_deck_page("<html><body>no table</body></html>") == [], "no table, no cards")
    check(
        parse_deck_page('<table id="decklist"></table>') == [],
        "an empty table yields nothing rather than raising",
    )


def test_implausible_quantities_are_dropped():
    html = (
        '<table id="decklist">'
        '<tr class="card-list-item" data-quantity="99">'
        '<td><a href="/cards/details-x">Bad - Card</a></td></tr>'
        '<tr class="card-list-item" data-quantity="0">'
        '<td><a href="/cards/details-y">Zero - Card</a></td></tr>'
        '<tr class="card-list-item" data-quantity="4">'
        '<td><a href="/cards/details-z">Good - Card</a></td></tr>'
        "</table>"
    )
    cards = parse_deck_page(html)
    check([c.name for c in cards] == ["Good - Card"], f"only the plausible row: {cards}")


# -------------------------------------------------------------- categories

def test_category_selects_the_listing_path():
    """Each of the site's tabs is a different path; 'all' is the bare one."""
    from lorcana_meta.sources.inkdecks import CATEGORIES

    check(CATEGORIES["all"] == "", "'all' has no path segment")
    check(CATEGORIES["core"] == "core", "core")
    check(CATEGORIES["infinity"] == "infinity", "infinity")
    check(CATEGORIES["poorcana"] == "poorcana", "poorcana")


def test_category_default_is_core():
    check(isolated().category == "core", "core unless asked otherwise")
    check(isolated().fmt == "Core Constructed", "and it labels the report accordingly")


def test_category_sets_the_report_label():
    for category, label in (
        ("core", "Core Constructed"),
        ("infinity", "Infinity Constructed"),
        ("poorcana", "Poorcana"),
        ("all", "All formats"),
    ):
        source = isolated(category=category)
        check(source.fmt == label, f"{category} -> {label!r}, got {source.fmt!r}")


def test_rows_carry_their_own_format():
    """With category 'all' the listing mixes formats, so each row must say which.

    Stamping one label on a mixed field would report Infinity decks as Core, and the
    archetype clustering would then compare lists that never meet across a table.
    """
    for stub in parse_index_page(fixture("inkdecks-list.html")):
        check(
            stub["format"] == "Core Constructed",
            f"{stub['deck_id']}: read the row's badge, got {stub['format']!r}",
        )


def test_format_badge_is_matched_by_text_not_position():
    """The set badge sits in the same cell, and must not be mistaken for a format."""
    html = (
        '<table><tbody><tr id="desktop-deck-1" data-href="/lorcana-metagame/deck-x-1">'
        '<td><strong>1st</strong><div class="text-secondary small">5-0-0</div></td>'
        '<td><a href="/lorcana-metagame/deck-x-1"><strong>N</strong></a>'
        '<div class="small text-secondary">by P</div></td>'
        '<td><span class="badge">Set 13</span>'
        '<div class="badge bg-theme-lt">Infinity</div></td>'
        '<td><div class="text-muted small">Aggro</div>'
        '<img src="/img/symbols/lorcana/ruby.svg" alt="ruby"/></td>'
        '<td>Cup <div class="text-muted">12 Players</div></td>'
        "<td>2026-08-20</td></tr></tbody></table>"
    )
    stubs = parse_index_page(html)
    check(len(stubs) == 1, f"one row, got {len(stubs)}")
    if stubs:
        check(
            stubs[0]["format"] == "Infinity Constructed",
            f"'Infinity' badge -> Infinity Constructed, got {stubs[0]['format']!r}",
        )


# ------------------------------------------------------------ event size filter

def test_small_events_are_filtered_before_any_deck_page_is_fetched():
    """The saving is the point: attendance is already on the listing row.

    Filtering after the fetch would mean making 200 requests and discarding the
    results - rude to the site and slow for no reason.
    """
    from datetime import date

    from lorcana_meta.models import DeckCard

    source = isolated(delay=0.5, min_players=32)
    source._fetch_index = lambda start, end: [
        {"deck_id": "big", "deck_name": "regional", "path": "/a", "standing": 1, "players": 128},
        {"deck_id": "small", "deck_name": "friday", "path": "/b", "standing": 1, "players": 12},
        {"deck_id": "edge", "deck_name": "exactly", "path": "/c", "standing": 2, "players": 32},
        {"deck_id": "unknown", "deck_name": "no size", "path": "/d", "standing": 3, "players": None},
    ]
    fetched = []
    source._fetch_decklist = lambda stub: fetched.append(stub["deck_id"]) or [
        DeckCard("Card", 60)
    ]
    source._to_deck = lambda stub, cards: stub["deck_id"]

    kept = source.fetch(date(2026, 8, 1), date(2026, 8, 31))
    check("small" not in fetched, f"the 12-player event was never fetched: {fetched}")
    check("big" in fetched and "edge" in fetched, f"32 and up are kept: {fetched}")
    check(
        "unknown" in fetched,
        "an event of unknown size is kept - we do not silently drop what we cannot judge",
    )
    check(sorted(kept) == ["big", "edge", "unknown"], f"three decks through: {kept}")


def test_no_min_players_fetches_everything():
    from datetime import date

    from lorcana_meta.models import DeckCard

    source = isolated(delay=0.5)
    source._fetch_index = lambda start, end: [
        {"deck_id": str(n), "deck_name": "x", "path": f"/{n}", "standing": 1, "players": n}
        for n in (4, 12, 200)
    ]
    fetched = []
    source._fetch_decklist = lambda stub: fetched.append(stub["deck_id"]) or [
        DeckCard("Card", 60)
    ]
    source._to_deck = lambda stub, cards: stub["deck_id"]

    source.fetch(date(2026, 8, 1), date(2026, 8, 31))
    check(len(fetched) == 3, f"no filter means no filtering: {fetched}")


# ------------------------------------------------------------------ transport

def test_there_is_one_client_and_it_is_read_only():
    """One transport, no switching.

    A plain-requests-first design with escalation was tried and dropped: every run
    began by earning two 403s and a minute of backoff to rediscover a standing
    block, and it needed a transport switch, a remembered-transport cache file and
    a branch in the retry loop to manage. One client that works beats two clients
    and the machinery to choose between them.
    """
    from lorcana_meta.sources.inkdecks import IMPERSONATE, _session

    check(isolated()._session.label == "curl_cffi", "the only client")
    check(IMPERSONATE, "a browser profile is pinned rather than left to the library")

    # The read-only guarantee is a property of the wrapper, not of the client.
    session = _session({"User-Agent": "x"})
    for method in ("post", "put", "patch", "delete", "request"):
        try:
            getattr(session, method)
            FAILURES.append(f"{method}() is reachable on the session")
        except SourceError:
            pass
    check(callable(session.get), "get() still works")


# ----------------------------------------------------------- read-only by design

def test_the_session_cannot_write():
    """inkdecks asked that this not disturb their site.

    Read-only is enforced rather than promised: the session wrapper exposes `get`
    and refuses everything that could change state on the far end. A future edit
    that reaches for `.post()` fails here instead of submitting something.
    """
    source = isolated()
    for method in ("post", "put", "patch", "delete", "request"):
        try:
            getattr(source._session, method)
            FAILURES.append(f"{method}() is reachable on the session")
        except SourceError as error:
            check("read-only" in str(error), f"{method}: says why - {error}")


def test_get_is_still_reachable():
    check(callable(isolated()._session.get), "get() works, or nothing does")


def test_only_allowed_paths_are_ever_requested():
    """Every path this source builds, checked against their robots.txt Disallow list.

    Their disallowed set is exactly the write-shaped and expensive endpoints
    (/decksubmissions, /suggestions/add, /image-cache/, the autocomplete JSON).
    Requesting one would be both rude and a breach of the crawl rules they publish.
    """
    from lorcana_meta.sources.inkdecks import CATEGORIES

    disallowed = (
        "/cgi-bin/", "/decks/visual", "/suggestions/add", "/decks/similar-decks",
        "/decksubmissions", "/cdn-cgi/rum", "/autocomplete/powersearch.json",
        "/image-cache/",
    )
    built = ["/lorcana-metagame/deck-example-123"]
    for segment in CATEGORIES.values():
        built.append(f"/lorcana-decks/{segment}" if segment else "/lorcana-decks")

    for path in built:
        for bad in disallowed:
            check(
                not path.startswith(bad),
                f"{path} collides with the disallowed {bad}",
            )


def test_bytes_read_is_counted():
    """So the footprint can be reported rather than guessed at."""
    check(isolated()._session.bytes_read == 0, "starts at zero and only grows on GET")


# --------------------------------------------------------- one run at a time

def test_two_builds_cannot_run_at_once():
    """Politeness held inside a process only.

    A manual build started while a scheduled one is going - or a restart that did
    not actually stop the first - doubles the request rate. The site then answers
    with 429s that read as its limit being tighter than it is. That happened here:
    an interleaved log showed two processes fetching at once, each dutifully waiting
    its own 20 seconds.
    """
    from datetime import date

    with tempfile.TemporaryDirectory() as directory:
        first = InkdecksSource(consent=True, cache_dir=directory)
        first._acquire_lock()
        try:
            second = InkdecksSource(consent=True, cache_dir=directory)
            try:
                second.fetch(date(2026, 8, 1), date(2026, 8, 2))
                FAILURES.append("a second concurrent build should be refused")
            except SourceError as error:
                check("Another build" in str(error), f"says what is wrong: {error}")
        finally:
            first._release_lock()


def test_an_abandoned_lock_is_taken_over():
    """A killed build leaves its lock behind; the next run must not be stuck."""
    import os as _os

    with tempfile.TemporaryDirectory() as directory:
        source = InkdecksSource(consent=True, cache_dir=directory)
        source._touch_lock()
        stale = time.time() - (LOCK_STALE_AFTER + 30)
        _os.utime(source._lock_path(), (stale, stale))

        try:
            InkdecksSource(consent=True, cache_dir=directory)._acquire_lock()
        except SourceError as error:
            FAILURES.append(f"a stale lock should be taken over: {error}")


def test_a_fresh_lock_from_a_dead_process_is_taken_over_at_once():
    """Waiting two minutes for a process that is demonstrably gone is pure delay.

    A build killed mid-run leaves a lock whose timestamp is seconds old. Without a
    liveness check the next run refuses to start until the lock ages out.
    """
    with tempfile.TemporaryDirectory() as directory:
        source = InkdecksSource(consent=True, cache_dir=directory)
        # A PID that cannot be running: 0 is never a normal user process.
        source._lock_path().write_text("pid 999999", encoding="utf-8")

        try:
            InkdecksSource(consent=True, cache_dir=directory)._acquire_lock()
        except SourceError as error:
            FAILURES.append(f"a dead holder should not block: {error}")


def test_a_live_holder_is_respected():
    import os as _os

    with tempfile.TemporaryDirectory() as directory:
        source = InkdecksSource(consent=True, cache_dir=directory)
        # This very process is alive, so the lock must hold.
        source._lock_path().write_text(f"pid {_os.getpid()}", encoding="utf-8")

        try:
            InkdecksSource(consent=True, cache_dir=directory)._acquire_lock()
            FAILURES.append("a live holder should block a second build")
        except SourceError as error:
            check("Another build" in str(error), f"explains itself: {error}")


def test_liveness_check_is_conservative_when_it_cannot_tell():
    """If we cannot determine whether a PID is alive, assume it is.

    Guessing 'dead' would let two builds run; guessing 'alive' costs at most a
    two-minute wait for the lock to age out.
    """
    import os as _os

    check(InkdecksSource._pid_is_alive(_os.getpid()) is True, "our own pid is alive")
    check(InkdecksSource._pid_is_alive(999999) is False, "an impossible pid is not")


def test_the_lock_is_released_even_when_the_fetch_fails():
    from datetime import date

    with tempfile.TemporaryDirectory() as directory:
        source = InkdecksSource(consent=True, cache_dir=directory)
        source._fetch_index = lambda start, end: (_ for _ in ()).throw(
            SourceError("upstream is down")
        )
        try:
            source.fetch(date(2026, 8, 1), date(2026, 8, 2))
        except SourceError:
            pass
        check(
            not source._lock_path().exists(),
            "the lock is gone, so the next run is not blocked by a failed one",
        )


# ------------------------------------------------------- bulk-fetch resilience

def test_one_refused_deck_does_not_kill_the_run():
    """A 369-deck build must survive a single stubborn page.

    This happened: one deck returned 429 on all three attempts and aborted the whole
    run at 100 of 369 - an hour of requests thrown away over one decklist that would
    have moved the percentages by 0.3%.
    """
    from datetime import date

    source = isolated(delay=0.5)
    stubs = [
        {"deck_id": str(i), "deck_name": f"deck {i}", "path": f"/p{i}"} for i in range(5)
    ]
    source._fetch_index = lambda start, end: stubs

    def flaky(stub):
        if stub["deck_id"] == "2":
            raise SourceError("inkdecks refused the request (429)")
        return [__import__("lorcana_meta.models", fromlist=["DeckCard"]).DeckCard("Card", 60)]

    source._fetch_decklist = flaky
    source._to_deck = lambda stub, cards: stub["deck_id"]

    decks = source.fetch(date(2026, 8, 1), date(2026, 8, 31))
    check(decks == ["0", "1", "3", "4"], f"the other four survived: {decks}")
    check(source.skipped == ["2"], f"the failure is recorded, not hidden: {source.skipped}")


def test_best_placed_decks_are_fetched_first():
    """A large window is realistically built over more than one sitting.

    The site's rate limit works out to a few pages a minute, so a 369-deck window
    may not finish in one run. Whatever a run does manage should therefore be the
    part that matters - the top finishes - not the tail of the listing.
    """
    from datetime import date

    from lorcana_meta.models import DeckCard

    source = isolated(delay=0.5, max_decks=3)
    source._fetch_index = lambda start, end: [
        {"deck_id": "a", "deck_name": "last", "path": "/a", "standing": 32},
        {"deck_id": "b", "deck_name": "winner", "path": "/b", "standing": 1},
        {"deck_id": "c", "deck_name": "mid", "path": "/c", "standing": 8},
        {"deck_id": "d", "deck_name": "unplaced", "path": "/d", "standing": None},
        {"deck_id": "e", "deck_name": "second", "path": "/e", "standing": 2},
    ]
    order = []
    source._fetch_decklist = lambda stub: order.append(stub["deck_id"]) or [
        DeckCard("Card", 60)
    ]
    source._to_deck = lambda stub, cards: stub["deck_id"]

    source.fetch(date(2026, 8, 1), date(2026, 8, 31))
    check(order == ["b", "e", "c"], f"best three, in order: {order}")


def test_systemic_refusal_still_stops_the_run():
    """If everything is refused, that is the site, and churning on is pointless."""
    from datetime import date

    from lorcana_meta.sources.inkdecks import MAX_CONSECUTIVE_FAILURES

    source = isolated(delay=0.5)
    stubs = [
        {"deck_id": str(i), "deck_name": f"deck {i}", "path": f"/p{i}"} for i in range(50)
    ]
    source._fetch_index = lambda start, end: stubs
    source._fetch_decklist = lambda stub: (_ for _ in ()).throw(SourceError("429"))

    try:
        source.fetch(date(2026, 8, 1), date(2026, 8, 31))
        FAILURES.append("a total refusal should raise")
    except SourceError as error:
        check("in a row" in str(error), f"the message says why: {error}")
        check(
            len(source.skipped) == MAX_CONSECUTIVE_FAILURES,
            f"stopped after {MAX_CONSECUTIVE_FAILURES}, not 50: {len(source.skipped)}",
        )


def test_a_success_resets_the_failure_streak():
    """Scattered failures across a long run must not add up to a systemic one."""
    from datetime import date

    from lorcana_meta.models import DeckCard
    from lorcana_meta.sources.inkdecks import MAX_CONSECUTIVE_FAILURES

    source = isolated(delay=0.5)
    stubs = [
        {"deck_id": str(i), "deck_name": f"deck {i}", "path": f"/p{i}"} for i in range(30)
    ]
    source._fetch_index = lambda start, end: stubs
    # Every other deck fails - far more than the cap in total, never consecutively.
    source._fetch_decklist = lambda stub: (
        (_ for _ in ()).throw(SourceError("429"))
        if int(stub["deck_id"]) % 2
        else [DeckCard("Card", 60)]
    )
    source._to_deck = lambda stub, cards: stub["deck_id"]

    decks = source.fetch(date(2026, 8, 1), date(2026, 8, 31))
    check(len(decks) == 15, f"every other deck survived: {len(decks)}")
    check(
        len(source.skipped) == 15 > MAX_CONSECUTIVE_FAILURES,
        f"more failures than the cap, but never in a row: {len(source.skipped)}",
    )


# ------------------------------------------------------------- consent gate

def test_consent_is_required():
    import os

    saved = os.environ.pop("INKDECKS_CONSENT", None)
    try:
        try:
            InkdecksSource()
            FAILURES.append("the source constructed without consent")
        except SourceError as error:
            check("permission" in str(error).lower(), f"the error explains why: {error}")
    finally:
        if saved is not None:
            os.environ["INKDECKS_CONSENT"] = saved


def test_consent_via_argument_and_env():
    import os

    source = isolated()
    check(source.publishable is False, "a private-use source is not publishable")

    saved = os.environ.pop("INKDECKS_CONSENT", None)
    os.environ["INKDECKS_CONSENT"] = "1"
    try:
        InkdecksSource()
    except SourceError as error:
        FAILURES.append(f"INKDECKS_CONSENT=1 should be enough: {error}")
    finally:
        os.environ.pop("INKDECKS_CONSENT", None)
        if saved is not None:
            os.environ["INKDECKS_CONSENT"] = saved


def test_rejects_unknown_options():
    for kwargs, what in (
        ({"category": "standard"}, "category"),
        ({"rank": "top3"}, "rank filter"),
    ):
        try:
            isolated(**kwargs)
            FAILURES.append(f"accepted a bad {what}: {kwargs}")
        except SourceError:
            pass


def isolated(**kwargs) -> InkdecksSource:
    """A source with its own cache, so tests never read the real learned throttle."""
    directory = tempfile.mkdtemp()
    kwargs.setdefault("cache_dir", directory)
    return InkdecksSource(consent=True, **kwargs)


def test_defaults_are_polite():
    source = isolated()
    check(source.delay >= 2.0, f"the default delay is {source.delay}s")
    check(source.max_decks and source.max_decks <= 2000, f"max_decks={source.max_decks}")


def test_delay_has_a_floor():
    """--inkdecks-delay 0 must not turn into a request flood."""
    check(isolated(delay=0).delay >= 0.5, "a zero delay is clamped")


def test_throttle_is_remembered_between_runs():
    """A daily rebuild must not re-earn yesterday's 429s."""
    with tempfile.TemporaryDirectory() as directory:
        source = InkdecksSource(consent=True, cache_dir=directory, delay=3.0)
        check(source.delay == 3.0, f"a fresh cache uses the configured delay: {source.delay}")

        source._slow_down()
        source._slow_down()
        learned = source.delay
        check(learned > 3.0, f"a rate limit widens the gap: {learned}")

        again = InkdecksSource(consent=True, cache_dir=directory, delay=3.0)
        check(
            3.0 < again.delay < learned,
            f"the next run starts near {learned:.1f}s but probes faster: {again.delay:.1f}s",
        )


def test_throttle_eases_after_a_clean_stretch():
    """One bad patch must not slow the whole run, nor every run after it."""
    from lorcana_meta.sources.inkdecks import EASE_AFTER

    with tempfile.TemporaryDirectory() as directory:
        source = InkdecksSource(consent=True, cache_dir=directory, delay=3.0)
        source._slow_down()
        source._slow_down()
        widened = source.delay
        check(widened > 3.0, f"widened to {widened}")

        for _ in range(EASE_AFTER - 1):
            source._speed_up()
        check(source.delay == widened, f"eases only after {EASE_AFTER} clean requests")

        source._speed_up()
        check(source.delay < widened, f"then eases: {widened:.2f} -> {source.delay:.2f}")


def test_throttle_never_goes_below_what_was_asked_for():
    with tempfile.TemporaryDirectory() as directory:
        source = InkdecksSource(consent=True, cache_dir=directory, delay=5.0)
        for _ in range(500):
            source._speed_up()
        check(source.delay >= 5.0, f"floor is the configured delay, got {source.delay}")


def test_a_rate_limit_resets_the_clean_streak():
    """Otherwise 19 clean requests plus a 429 plus one more would ease the delay."""
    from lorcana_meta.sources.inkdecks import EASE_AFTER

    with tempfile.TemporaryDirectory() as directory:
        source = InkdecksSource(consent=True, cache_dir=directory, delay=3.0)
        source._slow_down()
        widened = source.delay

        for _ in range(EASE_AFTER - 1):
            source._speed_up()
        source._slow_down()  # the streak dies here
        after = source.delay
        source._speed_up()
        check(source.delay == after, f"no easing straight after a 429: {source.delay}")


def test_throttle_never_exceeds_the_ceiling():
    from lorcana_meta.sources.inkdecks import MAX_DELAY

    with tempfile.TemporaryDirectory() as directory:
        source = InkdecksSource(consent=True, cache_dir=directory, delay=3.0)
        for _ in range(50):
            source._slow_down()
        check(source.delay <= MAX_DELAY, f"capped at {MAX_DELAY}s, got {source.delay}")


def test_a_corrupt_throttle_file_is_ignored():
    """A half-written cache file must not stop a build."""
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "throttle.json"
        for junk in ("not json", '{"delay": "soon"}', '{"delay": -5}', '{"delay": 99999}', "{}"):
            path.write_text(junk, encoding="utf-8")
            source = InkdecksSource(consent=True, cache_dir=directory, delay=3.0)
            check(source.delay == 3.0, f"{junk!r} -> fell back to 3.0, got {source.delay}")


def live_check() -> None:
    """Fetch two real pages and assert a whole deck parses. Opt-in only.

    The committed fixtures are excerpts, so they cannot prove that a full 60-card
    page adds up. This can, at the cost of touching the network - which is why it
    never runs in CI and needs INKDECKS_CONSENT plus --live.
    """
    source = InkdecksSource(consent=True, delay=4.0, max_decks=1)
    from datetime import date

    stubs = source._fetch_index(date(2026, 8, 22), date(2026, 8, 23))
    check(len(stubs) > 0, "the listing page still yields deck stubs")
    if not stubs:
        return

    cards = source._fetch_decklist(stubs[0])
    total = sum(card.count for card in cards)
    check(total == 60, f"a real constructed deck is 60 cards, got {total}")
    check(len(cards) >= 15, f"a real deck has 15+ distinct cards, got {len(cards)}")
    print(f"  live: {stubs[0]['deck_name']!r} -> {len(cards)} distinct, {total} cards")


def main() -> int:
    configure_output()
    tests = [value for name, value in sorted(globals().items()) if name.startswith("test_")]
    for test in tests:
        try:
            test()
        except Exception as error:
            FAILURES.append(f"{test.__name__} raised {error!r}")

    live = "--live" in sys.argv
    if live:
        if not os.environ.get("INKDECKS_CONSENT"):
            print("--live needs INKDECKS_CONSENT=1 (their terms require permission)")
            return 1
        print("running the live check against inkdecks.com...")
        try:
            live_check()
        except Exception as error:
            FAILURES.append(f"live_check raised {error!r}")

    if FAILURES:
        print(f"{len(FAILURES)} failure(s):")
        for failure in FAILURES:
            print(f"  - {failure}")
        return 1
    print(f"{len(tests)} tests passed" + (" (+ live check)" if live else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
