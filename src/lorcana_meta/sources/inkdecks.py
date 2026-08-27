"""inkDecks.com tournament source.

## Permission is required, and it is not implied by this file existing

inkdecks.com's terms of use prohibit automated access "without prior written
consent". This source therefore refuses to run until you confirm you have that
consent, either with ``--inkdecks-consent`` or by setting
``INKDECKS_CONSENT=1``. Getting it is a matter of asking them; it is not
something this code can grant you.

Consent usually comes with conditions. The one this module is written around -
personal use, no public site built on their data - is enforced rather than
documented: the source sets ``publishable = False``, which propagates into the
report and makes ``tests/check_report.py`` fail, which stops the GitHub Pages
workflow from deploying it. Build the private single-file report instead
(``tools/bundle_report.py``). If your own permission differs, that is a
deliberate change to make, not a default to drift into.

## Being a good guest

* One request at a time, with a delay between them (``--inkdecks-delay``, 3s
  default). No concurrency anywhere.
* The delay tunes itself upward on a 429 and never comes back down within a run,
  so a build settles onto a rate the site tolerates instead of hammering it. What
  it learned is remembered in the cache, so tomorrow's run does not re-earn the
  same 429s - it starts near the rate that worked and probes slightly faster.
  After a long clean stretch it eases back down, so one bad patch early on does
  not slow the rest of the run and every run after it.
* Deck pages never change once published, so they are cached on disk forever.
  A second build over the same window costs almost no requests.
* Only ``/lorcana-decks`` and ``/lorcana-metagame/deck-*`` are touched. Every
  path their ``robots.txt`` disallows is left alone.
* ``--max-decks`` is there so a mistyped date range cannot turn into thousands
  of requests.

## About the User-Agent

Cloudflare in front of the site rejects unrecognised User-Agent strings: a plain
browser string returns 200, and the same string with ``lorcana-meta/0.1``
appended returns 403. So the default is a bare browser string - not to disguise
anything from the site's owner, who gave you permission, but because a generic
filter leaves no other way through. Override it with ``INKDECKS_USER_AGENT`` if
they ask you to identify the tool a particular way; that is the better outcome
and worth asking for.

## Stateless requests

Keeping a session makes the second request onwards return 403, at any delay. The
cookie responsible is the site's own ``PHPSESSID``: their rate limiting appears to
be counted per session, so re-presenting one looks like a single visitor hammering
the site. Each request is therefore sent without cookies - which is simply what a
plain HTTP client does by default - and slowly.

## If the plain path stops working

inkdecks said they cannot easily allow-list an address and that cloudscraper is
acceptable if it turns out to be needed. So there is a fallback, and it is off by
default, because the plain path works: what the site actually pushes back with is
429 (a rate limit), not 403, and the answer to a rate limit is to slow down. A real
20-deck run saw six 429s at a 2s delay and none once the adaptive throttle had
stretched it; cloudscraper would not have helped with any of them.

``--inkdecks-scraper``:

* ``auto`` (default) - plain ``requests``; switch to cloudscraper only after the
  backoff has failed, and only if it is installed.
* ``plain`` - never switch. Fails loudly instead, which is what you want if you
  would rather know the site changed.
* ``cloudscraper`` - use it from the first request.

Installing it is opt-in: ``python -m pip install -e ".[cloudscraper]"``.
Keeping it out of the default install matters - it is a heavy dependency that
solves a problem you probably do not have, and reaching for it first would hide
the far more likely explanation that a parser or a filter broke.

This fallback rests on the site owner's say-so. Without that it would be
circumventing a security control, which is not something to do on your own
judgement.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from datetime import date
from pathlib import Path

import requests

from ..models import INKS, Deck, DeckCard
from .base import SourceError

log = logging.getLogger(__name__)

BASE = "https://inkdecks.com"
#: The site's own tabs, and the path segment each one lists under. These are a
#: different axis from a TopDeck format name: "Poorcana" is an inkdecks budget
#: category, and "all" has no equivalent elsewhere.
CATEGORIES = {
    "all": "",
    "core": "core",
    "infinity": "infinity",
    "poorcana": "poorcana",
}
#: What to record as the format when the category names one.
CATEGORY_FORMATS = {
    "core": "Core Constructed",
    "infinity": "Infinity Constructed",
    "poorcana": "Poorcana",
}
#: Placing filters the site offers.
RANKS = ("", "winners", "top2", "top4", "top8", "top16", "top32")

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
#: 6 of 20 requests hit a 429 at 2.0s, so that is above what the site tolerates.
#: The adaptive throttle stretches this further whenever it is still too fast.
DEFAULT_DELAY = 3.0
#: Ceiling for the adaptive throttle, so a bad afternoon cannot stall forever.
MAX_DELAY = 20.0
#: Successful requests in a row before easing the delay back down.
EASE_AFTER = 10
#: How much a single 429 widens the gap, and how much a clean stretch narrows it.
#:
#: Measured, not guessed. A real 369-deck run met exactly one rate limit, but it hit
#: the same page twice, and at 1.5x that took the delay from 8.6s to 19.3s - the rest
#: of the run then crawled because of one blip, and the remembered rate carried it
#: into the next run too. Meanwhile the steady-state gaps showed 8.6s being accepted
#: without complaint. 1.25 keeps the reaction proportionate: two consecutive failures
#: widen by ~1.6x rather than 2.25x.
WIDEN_BY = 1.25
NARROW_BY = 0.9
#: However wide the delay grows, one refused page never waits longer than this.
MAX_BACKOFF = 60.0
#: Decks refused in a row before treating it as the site rather than one bad page.
MAX_CONSECUTIVE_FAILURES = 8
#: A lock older than this is treated as abandoned - a killed build leaves one behind.
LOCK_STALE_AFTER = 120.0
LIST_CACHE_TTL = 3600  # list pages change as events are added; deck pages never do
#: How the HTTP requests are made. See the module docstring.
TRANSPORTS = ("auto", "plain", "cloudscraper")

_ORDINAL = re.compile(r"^(\d+)(?:st|nd|rd|th)$", re.IGNORECASE)
_BUCKET = re.compile(r"^top\s*(\d+)$", re.IGNORECASE)
_RECORD = re.compile(r"\b(\d{1,2})-(\d{1,2})-(\d{1,2})\b")
_PLAYERS = re.compile(r"\b(\d+)\s+Players\b", re.IGNORECASE)
_DATE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")
_DECK_HREF = re.compile(r"/lorcana-metagame/deck-[\w-]*?(\d+)$")
_INK_SYMBOL = re.compile(r"/img/symbols/lorcana/(\w+)\.svg")
_CARD_HREF = re.compile(r"^/cards/details-")


def _soup(html: str):
    try:
        from bs4 import BeautifulSoup
    except ImportError as error:  # pragma: no cover - depends on the environment
        raise SourceError(
            "The inkdecks source needs beautifulsoup4 for HTML parsing.\n"
            '  Install it with:  python -m pip install -e ".[inkdecks]"'
        ) from error
    return BeautifulSoup(html, "html.parser")


def parse_standing(text: str) -> tuple[int | None, str]:
    """Turn a placing label into a number plus the label as shown.

    The site mixes exact placings ("1st", "20th") with buckets ("Top8"). A bucket
    becomes its upper bound - "Top8" means "finished no worse than 8th" - so it
    stays comparable with an exact placing without ever overstating a result. The
    original label is kept so the report can show what the source actually said.
    """
    label = (text or "").strip()
    if not label:
        return None, ""

    exact = _ORDINAL.match(label)
    if exact:
        return int(exact.group(1)), label

    bucket = _BUCKET.match(label)
    if bucket:
        return int(bucket.group(1)), label

    if label.isdigit():
        return int(label), label
    return None, label


def _plain_session(headers: dict) -> requests.Session:
    session = requests.Session()
    session.headers.update(headers)
    return session


def _cloudscraper_session(headers: dict):
    """A cloudscraper session, which quacks like requests.Session.

    Only reachable once the plain path has demonstrably failed, or when asked for
    explicitly - see the module docstring on why it is not the default.
    """
    try:
        import cloudscraper
    except ImportError as error:
        raise SourceError(
            "\n".join(
                [
                    "inkdecks blocked the plain requests path, and cloudscraper is not "
                    "installed.",
                    '  Install it:  python -m pip install -e ".[cloudscraper]"',
                    "  Then re-run - nothing already cached is refetched.",
                    "  inkdecks confirmed this is acceptable; it is not a workaround you "
                    "should reach for without that.",
                ]
            )
        ) from error

    session = cloudscraper.create_scraper()
    session.headers.update(headers)
    return session


class InkdecksSource:
    name = "inkdecks.com"
    attribution = "Deck data from inkDecks.com, used with permission"
    attribution_url = "https://inkdecks.com/"
    #: Consent for this source is for private use, so the report must not be published.
    publishable = False

    def __init__(
        self,
        *,
        category: str = "core",
        rank: str = "top32",
        consent: bool = False,
        delay: float = DEFAULT_DELAY,
        cache_dir: Path | str = ".cache/inkdecks",
        max_decks: int | None = 1500,
        user_agent: str | None = None,
        transport: str = "auto",
        timeout: int = 45,
    ) -> None:
        if not (consent or os.environ.get("INKDECKS_CONSENT")):
            raise SourceError(
                "\n".join(
                    [
                        "The inkdecks source is off until you confirm you have their "
                        "written permission for automated access - their terms require "
                        "it, and this flag is you stating that you have it.",
                        "  Have it?   --inkdecks-consent, or INKDECKS_CONSENT=1",
                        "  Not yet?   ask them, or copy lists by hand:",
                        "             python tools/import_pasted_decks.py my-notes.txt",
                    ]
                )
            )
        if category not in CATEGORIES:
            raise SourceError(
                f"Unknown category {category!r}; expected one of {sorted(CATEGORIES)}"
            )
        if rank not in RANKS:
            raise SourceError(f"Unknown rank filter {rank!r}; expected one of {RANKS}")
        if transport not in TRANSPORTS:
            raise SourceError(f"Unknown transport {transport!r}; expected one of {TRANSPORTS}")

        self.category = category
        #: Label for the report. With "all" it is per-deck, read off each row.
        self.fmt = CATEGORY_FORMATS.get(category, "All formats")
        self.rank = rank
        self.cache_dir = Path(cache_dir)
        #: Never go below what the caller asked for, however well things are going.
        self.min_delay = max(float(delay), 0.5)
        self.delay = self._load_throttle(self.min_delay)
        self._clean_streak = 0
        #: Decks the site refused. Reported rather than silently missing from the field.
        self.skipped: list[str] = []
        self.max_decks = max_decks
        self.timeout = timeout
        self.transport = transport
        self._last_request = 0.0
        self._headers = {
            "User-Agent": user_agent
            or os.environ.get("INKDECKS_USER_AGENT")
            or DEFAULT_USER_AGENT,
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "en-US,en;q=0.9",
        }

        self._using_cloudscraper = transport == "cloudscraper"
        self._session = (
            _cloudscraper_session(self._headers)
            if self._using_cloudscraper
            else _plain_session(self._headers)
        )

    # -- fetching --------------------------------------------------------------

    def fetch(self, start: date, end: date) -> list[Deck]:
        self._acquire_lock()
        try:
            return self._fetch(start, end)
        finally:
            self._release_lock()

    def _fetch(self, start: date, end: date) -> list[Deck]:
        stubs = self._fetch_index(start, end)
        log.info("inkdecks: %d decks listed for %s .. %s", len(stubs), start, end)

        # Always best-placed first, not only when trimming. The site's rate limit is
        # tight enough that a large window is realistically built over more than one
        # sitting, so whatever a run manages to fetch should be the part that matters
        # most - and with the cache, the next run continues where this one stopped.
        stubs.sort(key=lambda s: (s.get("standing") or 999, s.get("deck_id", "")))

        if self.max_decks and len(stubs) > self.max_decks:
            log.warning(
                "inkdecks: %d decks listed, keeping the best-placed %d "
                "(raise --inkdecks-max-decks to widen)",
                len(stubs),
                self.max_decks,
            )
            stubs = stubs[: self.max_decks]

        decks = []
        consecutive_failures = 0

        for position, stub in enumerate(stubs, start=1):
            try:
                cards = self._fetch_decklist(stub)
            except SourceError as error:
                # One stubborn page must not cost the whole run. Losing 1 decklist of
                # 369 barely moves a percentage; losing the run costs an hour and
                # every request it already made. The count is reported either way, so
                # the report never quietly stands on a thinner field than it claims.
                self.skipped.append(stub["deck_id"])
                consecutive_failures += 1
                log.warning(
                    "inkdecks: skipping deck %s (%s) - %s",
                    stub["deck_id"],
                    stub["deck_name"],
                    str(error).splitlines()[0],
                )
                if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                    raise SourceError(
                        f"inkdecks refused {consecutive_failures} decks in a row, so "
                        "this is the site rather than one bad page.\n"
                        f"  {len(decks)} decklists were read and cached; a re-run "
                        "resumes from there.\n"
                        "  Try again later, or raise --inkdecks-delay."
                    ) from error
                continue

            consecutive_failures = 0
            if not cards:
                continue
            decks.append(self._to_deck(stub, cards))
            if position % 25 == 0 or position == len(stubs):
                log.info("inkdecks: %d/%d decklists read", position, len(stubs))

        if self.skipped:
            log.warning(
                "inkdecks: %d of %d decks could not be fetched and are missing from "
                "the report: %s",
                len(self.skipped),
                len(stubs),
                ", ".join(self.skipped[:10]) + (" ..." if len(self.skipped) > 10 else ""),
            )
        return decks

    def _fetch_index(self, start: date, end: date) -> list[dict]:
        segment = CATEGORIES[self.category]
        path = f"/lorcana-decks/{segment}" if segment else "/lorcana-decks"
        stubs: list[dict] = []
        seen: set[str] = set()
        reported: int | None = None
        page = 1

        while True:
            params = {
                "deck_type": "tournament",
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
            }
            if self.rank:
                params["rank"] = self.rank
            if page > 1:
                params["page"] = str(page)

            html = self._get(path, params=params, cache_ttl=LIST_CACHE_TTL, cache_key=f"list-{self.rank or 'all'}-{start}-{end}-p{page}")
            if reported is None:
                reported = total_decks(html)

            found = parse_index_page(html)
            fresh = [s for s in found if s["deck_id"] not in seen]
            for stub in fresh:
                seen.add(stub["deck_id"])
            stubs.extend(fresh)

            # The site clamps an out-of-range page to the last one, so a page that
            # adds nothing new is the end - checking the pager markup is not enough.
            if not fresh or page >= max_page(html):
                break
            page += 1

        self._check_completeness(len(stubs), reported, page)
        return stubs

    @staticmethod
    def _check_completeness(collected: int, reported: int | None, pages: int) -> None:
        """Say so if the pager gave up before the listing did.

        This exists because it already happened: pager links are HTML-escaped, the
        regex looking for them matched nothing, and every build quietly stopped after
        the first 20 of 369 decks. Nothing failed - the report was simply wrong, and
        looked entirely plausible. Comparing against the count the site prints itself
        is the check that does not depend on the pagination code being right.
        """
        if not reported or collected >= reported:
            return
        if collected >= reported * 0.9:
            return  # decks can be added or withdrawn between page loads

        log.warning(
            "inkdecks: collected %d of the %d decks the listing reports, after %d "
            "page(s). The report will be built from a partial field - if this looks "
            "like truncation rather than a moving target, the pagination parsing has "
            "broken.",
            collected,
            reported,
            pages,
        )

    def _fetch_decklist(self, stub: dict) -> list[DeckCard]:
        html = self._get(
            stub["path"],
            cache_ttl=None,  # a published decklist is immutable
            cache_key=f"deck-{stub['deck_id']}",
        )
        cards = parse_deck_page(html)
        if not cards:
            log.warning("inkdecks: no cards parsed out of %s", stub["path"])
        return cards

    def _to_deck(self, stub: dict, cards: list[DeckCard]) -> Deck:
        return Deck(
            source=self.name,
            deck_id=stub["deck_id"],
            player=stub["player"],
            deck_name=stub["deck_name"],
            cards=cards,
            standing=stub["standing"],
            standing_label=stub["standing_label"],
            wins=stub["wins"],
            losses=stub["losses"],
            draws=stub["draws"],
            tournament_id=stub["tournament_name"],
            tournament_name=stub["tournament_name"],
            tournament_date=stub["date"],
            tournament_players=stub["players"],
            # With category "all" the listing mixes formats, so take each row's own
            # badge rather than stamping every deck with one label.
            fmt=stub.get("format") or self.fmt,
            url=f"{BASE}{stub['path']}",
        )

    # -- transport -------------------------------------------------------------

    def _get(self, path: str, *, params: dict | None = None, cache_ttl: int | None, cache_key: str) -> str:
        cached = self._read_cache(cache_key, cache_ttl)
        if cached is not None:
            return cached

        url = f"{BASE}{path}"

        for attempt in range(3):
            self._wait()
            response = self._session.get(url, params=params, timeout=self.timeout)
            # Their rate limiting is counted per session, so carrying the site's own
            # PHPSESSID across requests gets the next one refused. Browse statelessly,
            # which is what a plain HTTP client does anyway.
            self._session.cookies.clear()

            # 429 and 403 mean different things and want opposite responses.
            #
            # 429 is "you are going too fast". The answer is to go slower - for the
            # rest of the run, not just this request - and never to change client:
            # pushing the same rate through a different HTTP stack is precisely the
            # abuse the limit exists to stop.
            if response.status_code == 429:
                if attempt < 2:
                    self._slow_down()
                    backoff = min(self.delay * (attempt + 1) * 2, MAX_BACKOFF)
                    log.warning(
                        "inkdecks: rate limited on %s - waiting %.0fs, "
                        "delay now %.1fs",
                        path,
                        backoff,
                        self.delay,
                    )
                    time.sleep(backoff)
                    continue
                raise SourceError(self._refused_message(429, url))

            # 403 is "we do not like your client". That is what the fallback is for.
            if response.status_code == 403:
                if attempt < 2:
                    backoff = self.delay * (attempt + 1) * 4
                    log.warning("inkdecks: 403 on %s - backing off %.0fs", path, backoff)
                    time.sleep(backoff)
                    continue

                if self.transport == "auto" and not self._using_cloudscraper:
                    log.warning(
                        "inkdecks: still blocked after backing off - switching to "
                        "cloudscraper for the rest of this run"
                    )
                    self._session = _cloudscraper_session(self._headers)
                    self._using_cloudscraper = True
                    return self._get(
                        path, params=params, cache_ttl=cache_ttl, cache_key=cache_key
                    )

                raise SourceError(self._refused_message(403, url))

            response.raise_for_status()
            self._speed_up()
            self._write_cache(cache_key, response.text)
            return response.text

        raise SourceError(f"inkdecks: giving up on {url}")  # kept explicit

    def _slow_down(self) -> None:
        """Widen the gap between requests after a rate limit, and keep it widened.

        Their sustainable rate is not documented, so it is discovered: each 429
        stretches the delay, and it never shrinks again during the run. Guessing a
        fixed delay either wastes an hour or trips the limit repeatedly.
        """
        self.delay = min(self.delay * WIDEN_BY, MAX_DELAY)
        self._clean_streak = 0
        self._save_throttle()

    def _speed_up(self) -> None:
        """Ease the delay back down after a long clean stretch.

        Without this the delay only ever climbs: one bad patch early on slows the
        whole run, and because the rate is remembered, every future run too. Easing
        off slowly after `EASE_AFTER` clean requests lets it settle near the real
        sustainable rate instead of the worst it ever saw.
        """
        self._clean_streak += 1
        if self._clean_streak < EASE_AFTER or self.delay <= self.min_delay:
            return

        self._clean_streak = 0
        self.delay = max(self.delay * NARROW_BY, self.min_delay)
        log.debug("inkdecks: %d clean requests, easing to %.1fs", EASE_AFTER, self.delay)
        self._save_throttle()

    # -- remembering the rate --------------------------------------------------
    #
    # Without this, every run starts at the configured delay and re-earns the same
    # 429s before settling. A daily rebuild would collect them every morning.

    def _throttle_path(self) -> Path:
        return self.cache_dir / "throttle.json"

    def _load_throttle(self, configured: float) -> float:
        """Start from what the last run learned, probing slightly faster each time.

        The 0.85 nudge means a limit that has since been relaxed is rediscovered
        over a few runs, instead of the delay ratcheting up forever.
        """
        try:
            learned = float(json.loads(self._throttle_path().read_text("utf-8"))["delay"])
        except (OSError, ValueError, KeyError, TypeError):
            return configured

        if not 0 < learned <= MAX_DELAY:
            return configured
        remembered = max(configured, learned * 0.85)
        if remembered > configured:
            log.info(
                "inkdecks: starting at %.1fs, from what the last run learned", remembered
            )
        return remembered

    def _save_throttle(self) -> None:
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            self._throttle_path().write_text(
                json.dumps({"delay": round(self.delay, 2)}), encoding="utf-8"
            )
        except OSError:
            pass  # a cache we cannot write is not worth failing a build over

    def _refused_message(self, status: int, url: str) -> str:
        lines = [f"inkdecks refused the request ({status}) for {url}, and waiting did not help."]

        if status == 429:
            lines += [
                f"  This is a rate limit. The delay had already grown to {self.delay:.1f}s.",
                "  Try again later, or start from --inkdecks-delay "
                f"{min(self.delay * 2, MAX_DELAY):.0f} and narrow the date range.",
                "  Nothing already cached is refetched, so a re-run picks up where this "
                "one stopped.",
            ]
            return "\n".join(lines)

        lines.append(
            "  Nothing already cached is refetched, so a re-run resumes where this stopped."
        )
        if self._using_cloudscraper:
            lines.append(
                "  cloudscraper did not get through either, so this looks like a real "
                "change on their side rather than a rate problem. Worth asking them."
            )
        elif self.transport == "plain":
            lines.append(
                "  --inkdecks-scraper plain is set, so no fallback was tried. Drop that "
                "flag to let it escalate to cloudscraper."
            )
        return "\n".join(lines)

    # -- one run at a time -----------------------------------------------------
    #
    # "One request at a time" only ever held inside a single process. Two builds -
    # a manual one started while a scheduled one is going, or a restart that did not
    # actually stop the first - double the request rate, and the site answers with
    # 429s that look like its limit being tighter than it is. Measured the hard way:
    # an interleaved log showed two processes fetching at once, each politely waiting
    # its own 20 seconds.

    def _lock_path(self) -> Path:
        return self.cache_dir / "run.lock"

    @staticmethod
    def _pid_is_alive(pid: int) -> bool:
        """Is that process still there?

        A killed build leaves its lock behind, and waiting out LOCK_STALE_AFTER for
        a process that is demonstrably gone is pure delay. Checking liveness turns a
        two-minute wait into an instant take-over.
        """
        if os.name == "nt":
            import subprocess

            try:
                output = subprocess.run(
                    ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                ).stdout
            except (OSError, subprocess.SubprocessError):
                return True  # cannot tell, so assume it is running and stay safe
            return str(pid) in output

        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True  # someone else's process, but a live one
        except OSError:
            return True
        return True

    def _acquire_lock(self) -> None:
        path = self._lock_path()
        try:
            age = time.time() - path.stat().st_mtime
        except OSError:
            age = None

        if age is not None and age < LOCK_STALE_AFTER:
            try:
                holder = path.read_text(encoding="utf-8").strip()
            except OSError:
                holder = "unknown"

            match = re.search(r"pid (\d+)", holder)
            if match and not self._pid_is_alive(int(match.group(1))):
                log.info(
                    "inkdecks: taking over a lock left behind by %s, which is gone",
                    holder,
                )
                self._touch_lock()
                return
            raise SourceError(
                "\n".join(
                    [
                        f"Another build is already reading inkdecks ({holder}, active "
                        f"{age:.0f}s ago).",
                        "  Two builds at once double the request rate and earn 429s "
                        "that look like the site's limit being tighter than it is.",
                        "  Wait for it to finish - it is caching pages this run would "
                        "reuse anyway - or stop it first.",
                    ]
                )
            )

        self._touch_lock()

    def _touch_lock(self) -> None:
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            self._lock_path().write_text(f"pid {os.getpid()}", encoding="utf-8")
        except OSError:
            pass  # a cache we cannot write is not worth failing a build over

    def _release_lock(self) -> None:
        try:
            self._lock_path().unlink()
        except OSError:
            pass

    def _wait(self) -> None:
        elapsed = time.monotonic() - self._last_request
        if elapsed < self.delay:
            time.sleep(self.delay - elapsed)
        self._last_request = time.monotonic()
        self._touch_lock()  # a slow run must not look abandoned

    def _cache_path(self, key: str) -> Path:
        safe = re.sub(r"[^A-Za-z0-9._-]", "_", key)
        return self.cache_dir / f"{safe}.html"

    def _read_cache(self, key: str, ttl: int | None) -> str | None:
        path = self._cache_path(key)
        if not path.exists():
            return None
        if ttl is not None and (time.time() - path.stat().st_mtime) > ttl:
            return None
        return path.read_text(encoding="utf-8")

    def _write_cache(self, key: str, html: str) -> None:
        path = self._cache_path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(html, encoding="utf-8")


# -- parsing -------------------------------------------------------------------
#
# Fields are located by what they contain, not by which column they sit in. The
# site's table has changed shape before, and a positional parser reacts to that by
# reading the price column as a placing - wrong numbers, no error. Content-based
# extraction either finds a date-shaped string or reports that it did not.


#: Pager links arrive HTML-escaped, so the character before "page=" is ";" in
#: "&amp;page=2", not "&". Matching only [?&] found nothing, max_page() returned 1,
#: and every build silently stopped after the first 20 decks.
_PAGE_LINK = re.compile(r"(?:[?&]|&amp;)page=(\d+)")
#: "369 decks" in the listing header - what the site says the window holds.
_TOTAL_DECKS = re.compile(r"([\d,.]+)\s*decks", re.IGNORECASE)


def max_page(html: str) -> int:
    return max((int(n) for n in _PAGE_LINK.findall(html)), default=1)


def total_decks(html: str) -> int | None:
    """How many decks the listing claims to hold, for a completeness check."""
    match = _TOTAL_DECKS.search(html)
    if not match:
        return None
    try:
        return int(match.group(1).replace(",", "").replace(".", ""))
    except ValueError:
        return None


def parse_index_page(html: str) -> list[dict]:
    """Pull deck stubs - everything except the card list - out of a listing page."""
    soup = _soup(html)
    stubs = []

    for row in soup.select('tr[id^="desktop-deck-"]'):
        deck_id = row.get("id", "").removeprefix("desktop-deck-")
        link = row.find("a", href=_DECK_HREF)
        if not deck_id or link is None:
            continue

        path = re.sub(r"^https?://[^/]+", "", link["href"])
        text = row.get_text(" ", strip=True)

        strong = row.find("strong")
        standing, standing_label = parse_standing(strong.get_text(strip=True) if strong else "")

        record = _RECORD.search(text)
        players = _PLAYERS.search(text)
        day = _DATE.search(text)

        inks = []
        for image in row.find_all("img", src=_INK_SYMBOL):
            ink = (image.get("alt") or "").strip().lower()
            if ink in INKS and ink not in inks:
                inks.append(ink)

        player = ""
        for node in row.select("div.small, div.text-secondary"):
            value = node.get_text(" ", strip=True)
            if value.lower().startswith("by "):
                player = value[3:].strip()
                break

        archetype = ""
        muted = row.select_one("div.text-muted.small")
        if muted:
            archetype = muted.get_text(" ", strip=True)

        # The format badge sits beside the set badge. Matched by its text rather than
        # its position, since "all" is the only case that needs it and a wrong guess
        # there would mislabel every deck.
        deck_format = ""
        for badge in row.select("div.badge"):
            value = badge.get_text(" ", strip=True)
            if value in CATEGORY_FORMATS.values() or value.lower() in CATEGORY_FORMATS:
                deck_format = CATEGORY_FORMATS.get(value.lower(), value)
                break

        stubs.append(
            {
                "deck_id": deck_id,
                "path": path,
                "deck_name": link.get_text(" ", strip=True),
                "player": player or "Unknown",
                "standing": standing,
                "standing_label": standing_label,
                "wins": int(record.group(1)) if record else None,
                "losses": int(record.group(2)) if record else None,
                "draws": int(record.group(3)) if record else None,
                "tournament_name": _event_name(row),
                "players": int(players.group(1)) if players else None,
                "date": day.group(1) if day else "",
                "inks": inks,
                "archetype": archetype,
                "format": deck_format,
            }
        )

    return stubs


def _event_name(row) -> str:
    """The event cell holds the name, then the organiser and attendance below it."""
    for cell in row.find_all("td"):
        text = cell.get_text(" ", strip=True)
        if _PLAYERS.search(text):
            truncated = cell.select_one("div.text-truncate")
            if truncated:
                # Drop the "@organiser" and "N Players" lines, keep the event name.
                for child in truncated.select("div"):
                    child.extract()
                name = truncated.get_text(" ", strip=True)
                if name:
                    return name
            return _PLAYERS.sub("", text).strip() or "Unknown event"
    return "Unknown event"


def parse_deck_page(html: str) -> list[DeckCard]:
    """Read the decklist table off a deck page.

    Rows carry the quantity in ``data-quantity`` and the card in a link to its
    details page, which is far steadier than the rendered text: the name is split
    across a ``<b>`` for the character and plain text for the version.
    """
    soup = _soup(html)
    table = soup.find(id="decklist")
    if table is None:
        return []

    cards: dict[str, int] = {}
    for row in table.select("tr.card-list-item"):
        try:
            quantity = int(row.get("data-quantity", ""))
        except (TypeError, ValueError):
            continue
        if not 1 <= quantity <= 20:
            continue

        link = row.find("a", href=_CARD_HREF)
        if link is None:
            continue
        name = " ".join(link.get_text(" ", strip=True).split())
        # "Eilonwy - Princess of Llyr" arrives as "Eilonwy - Princess of Llyr" once
        # the <b> and the tail are joined; collapse any spacing around the dash.
        name = re.sub(r"\s*-\s*", " - ", name).strip(" -")
        if len(name) < 3:
            continue
        cards[name] = cards.get(name, 0) + quantity

    return [DeckCard(name=name, count=count) for name, count in cards.items()]
