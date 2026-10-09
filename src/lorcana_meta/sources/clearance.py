"""Clearing a Cloudflare challenge with a real browser, once per run.

## Why this exists

In October 2026 inkdecks put a Cloudflare managed challenge in front of
``/lorcana-metagame/deck-*``. Listing pages stayed open; deck pages began
answering ``403`` with ``cf-mitigated: challenge`` - an interstitial, not a
refusal. No HTTP client clears one, because clearing it is the point: it wants
JavaScript run and a ``cf_clearance`` cookie set.

inkdecks confirmed the change is theirs and that the existing permission stands,
and named browser-driving libraries as the way to keep working. Their own IT is
outsourced and not practically reachable for a WAF exemption, so the handling
lives here.

## The shape, and why it is this shape

A browser is needed to *mint* the cookie, not to do the crawling. Measured on
2026-10-09: Chrome clears the interstitial in about four seconds, and the
``cf_clearance`` it earns is then accepted by ``curl_cffi`` impersonating desktop
Chrome - 200, deck rows intact.

So the browser opens once, on the first challenge, and closes immediately. Every
one of the hundreds of deck pages after it goes over the ordinary transport, at
the ordinary pace, through the ordinary cache and the read-only wrapper. A run
that finds a fresh cookie in the cache never opens a browser at all.

Two measurements shaped the details:

* **Headless does not work.** Cloudflare leaves a headless Chrome sitting on the
  interstitial indefinitely - 30s of waiting, no clearance. So the window is
  visible. It is brief and it is honest about what is happening.
* **The cookie is bound to the fingerprint, the User-Agent and the address that
  earned it.** A cookie minted in mobile-emulated Chrome was refused over every
  impersonation profile. The browser's own User-Agent is therefore carried back
  and used for the rest of the run; nothing else would be honoured.

## What this does not do

It does not solve, bypass or weaken the challenge. It lets the challenge do
exactly what it is for - confirm a browser - and then gets out of the way. There
is no CAPTCHA solving here, no third-party service, no fingerprint forgery beyond
the impersonation the module docstring in ``inkdecks.py`` already accounts for.
"""

from __future__ import annotations

import json
import logging
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from .base import SourceError

log = logging.getLogger(__name__)

#: Cloudflare's default Challenge Passage is 30 minutes. A stored cookie is
#: treated as spent well before that, so a long run refreshes on its own terms
#: rather than discovering the expiry as a challenge halfway through a field.
CLEARANCE_TTL = 20 * 60.0
#: How long to let the interstitial resolve before calling it stuck.
SETTLE_TIMEOUT = 45.0
#: Polling gap while it resolves. It took ~4s when measured.
SETTLE_STEP = 1.5


@dataclass(frozen=True)
class Clearance:
    """A cleared challenge: the cookie, and the identity it is bound to."""

    cookie: str
    user_agent: str
    obtained: float

    def fresh(self, now: float | None = None) -> bool:
        return (now if now is not None else time.time()) - self.obtained < CLEARANCE_TTL

    def as_dict(self) -> dict:
        return {
            "cookie": self.cookie,
            "user_agent": self.user_agent,
            "obtained": self.obtained,
        }

    @classmethod
    def from_dict(cls, raw: dict) -> Clearance:
        return cls(
            cookie=str(raw["cookie"]),
            user_agent=str(raw["user_agent"]),
            obtained=float(raw["obtained"]),
        )


def load(path: Path) -> Clearance | None:
    """Last run's clearance, if it is still worth presenting."""
    try:
        clearance = Clearance.from_dict(json.loads(path.read_text("utf-8")))
    except (OSError, ValueError, KeyError, TypeError):
        return None
    return clearance if clearance.fresh() else None


def save(path: Path, clearance: Clearance) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(clearance.as_dict()), encoding="utf-8")
    except OSError:
        pass  # a cache we cannot write is not worth failing a build over


def _nodriver():
    try:
        import nodriver
    except ModuleNotFoundError as error:
        # Name the interpreter, for the same reason curl_cffi's loader does: a pip
        # install in an un-activated shell lands somewhere else entirely.
        raise SourceError(
            "\n".join(
                [
                    "nodriver is not installed for the interpreter running this build:",
                    f"    {sys.executable}",
                    "  It is what clears the Cloudflare challenge on deck pages.",
                    f'    "{sys.executable}" -m pip install -e .',
                    "  Or build without it: --inkdecks-no-browser, --source local.",
                ]
            )
        ) from error
    except ImportError as error:
        raise SourceError(
            f"nodriver is installed but failed to import: {error}\n"
            f'  Try: "{sys.executable}" -m pip install --force-reinstall nodriver'
        ) from error
    return nodriver


def _still_challenged(html: str) -> bool:
    """Is this still the interstitial?

    Matches on Cloudflare's own markup rather than on its text: the page is served
    in the reader's language, so "Just a moment" is "Cierpliwosci" here.
    """
    head = html[:4000].lower()
    return "challenge-platform" in head or ("cf_chl" in head and "<title>" in head)


def mint(url: str) -> Clearance:
    """Open one page in a real browser, let the challenge resolve, keep the cookie.

    Visible on purpose: a headless Chrome never gets past the interstitial, and a
    build that quietly drives a hidden browser is worse than one that shows it.
    """
    uc = _nodriver()
    # It logs the whole Chrome command line at INFO, which buries the build's own
    # output in forty lines of switches nobody asked for.
    logging.getLogger("nodriver").setLevel(logging.WARNING)
    logging.getLogger("uc").setLevel(logging.WARNING)
    log.info("inkdecks: clearing the Cloudflare challenge in a browser (one page)")

    async def run() -> Clearance:
        browser = await uc.start(headless=False)
        try:
            page = await browser.get(url)
            deadline = time.monotonic() + SETTLE_TIMEOUT
            while time.monotonic() < deadline:
                await page.sleep(SETTLE_STEP)
                if not _still_challenged(await page.get_content()):
                    break
            else:
                raise SourceError(
                    f"the Cloudflare challenge on {url} did not resolve within "
                    f"{SETTLE_TIMEOUT:.0f}s.\n"
                    "  It may want an interaction - try the same URL in your own "
                    "browser, then re-run."
                )

            cookie = next(
                (c for c in await browser.cookies.get_all() if c.name == "cf_clearance"),
                None,
            )
            if cookie is None:
                raise SourceError(
                    f"the challenge on {url} cleared but set no cf_clearance cookie, "
                    "so there is nothing to carry over to the crawl."
                )
            agent = await page.evaluate("navigator.userAgent")
            return Clearance(str(cookie.value), str(agent), time.time())
        finally:
            browser.stop()

    clearance = uc.loop().run_until_complete(run())
    log.info("inkdecks: challenge cleared, the crawl continues over the usual client")
    return clearance
