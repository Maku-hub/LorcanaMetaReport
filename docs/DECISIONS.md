# Decisions, and the traps behind them

Why this project is shaped the way it is. Most entries exist because something went
wrong first — the reasoning is recorded so it does not have to be rediscovered.

Ordered roughly by how much trouble each one caused.

---

## 1. Data sources: what is allowed, and what that costs

**inkdecks.com has the widest tournament coverage and prohibits automated access.**
Their terms of use carry a section titled *"PROHIBITION OF AUTOMATED ACCESS &
SCRAPING"* — no automated collection *"without prior written consent"* — plus a
liquidated-damages clause aimed at services built on their data. `robots.txt` also
blocks `ClaudeBot` and `anthropic-ai`.

So the project was first built on **TopDeck.gg's documented API** (free key, Lorcana
supported, standings with decklists, requires a visible credit). That adapter still
exists and is the right default for anyone without permission.

**TopDeck was removed in full once inkdecks became available.** Its coverage of Lorcana turned out to be too thin to build a meta reading on - it only sees events actually run on that platform - and maintaining a second source that nobody used meant a second parser, a second set of credentials and a second thing to keep working. `--source` is now `inkdecks` (default) or `local`.

If you ever want it back, it is in the history: the adapter, its `deckObj` parsing in `decklist.py`, and the `--api-key` / `--min-players` flags all went together. Do not re-add it half way - the `Deck` interface is the whole contract, and a source that only fills half of it produces a report that looks complete.

**Permission was then obtained**, for personal use with no commercialised public site
built on their data. That is why `InkdecksSource` exists, why it refuses to run
without `--inkdecks-consent` / `INKDECKS_CONSENT=1`, and why it sets
`publishable = False`.

The condition is enforced rather than documented: `publishable` travels into the
report, `tests/check_report.py` fails on it, and the Pages workflow runs that check
before deploying. Three links in a chain, so no single edit quietly publishes
someone else's data.

**If you have no permission**, `tools/import_pasted_decks.py` takes a file of
hand-copied lists (`### name | player | placing | event | date | attendance`) and
converts them for `--source local`. Reading a page and copying a list yourself is not
automated access. The tool fetches nothing.

---

## 2. GitHub Pages cannot host a private report

The original plan was a private repo plus Pages. That does not work:

> GitHub Pages sites are publicly available on the internet by default, even if the
> repository for the site is private or internal. […] To publish a GitHub Pages site
> privately, your organization must use GitHub Enterprise Cloud.

Access control is Enterprise Cloud only, and only for organization-owned
repositories. A personal Free or Pro account cannot make a Pages site private at all
— private repo, world-readable page, guessable URL.

Hence `tools/bundle_report.py`: CSS, JavaScript and data inlined into one
`report.html` that opens from the filesystem. Verified in headless Chrome over
`file://` **without** `--allow-file-access-from-files`, which is the difference
between self-contained and nearly.

`tests/test_bundle.py` guards it, because the regression is silent: a bundle that
stopped being self-contained still opens, and just shows "could not load
data/meta.json" — at the moment you needed it.

---

## 3. Archetypes come from card overlap, not names

Deck names are useless for grouping. Real data, one ink pair, one archetype, the
names players submitted:

> Blurple · Brewing a Storm · I was there before it was cool · Stormlight Archive ·
> YP · Yeetple

Seven lists, six names, one deck. And in the other direction, two lists sharing a
name can be completely different decks.

Grouping by ink pair alone is also wrong: 56 real Amber/Amethyst decks turned out to
be **7 different archetypes**, and averaging across them produces a field where
nothing reads as core.

So decks are clustered on the **weighted Jaccard index** over card counts:

```
similarity(a, b) = Σ min(aᵢ, bᵢ) / Σ max(aᵢ, bᵢ)
```

Copies, not just names — a list on 4 Grandmother Willow and one on 1 are making
different choices, and set overlap cannot see it. Threshold 0.60 by default; two
lists differing by four of sixty cards score ~0.87.

Clustering is leader-based, best-finish-first, with a merge pass afterwards that
removes the dependence on visit order. Deterministic: a test shuffles the input five
ways and asserts identical clusters.

Archetypes are **named after the cards that distinguish them** from the rest of their
ink pair, preferring the expensive character a player would name the deck after. An
earlier version broke ties alphabetically and produced "Agustin Madrigal" for a
control deck.

### The sample-data trap

The synthetic field originally filled ~20 of 60 slots with random cards, so two lists
of one archetype scored ~0.5 similarity and the clustering "failed" — 59 archetypes
from 60 decks. The algorithm was correct; the fixture was not. `tools/generate_sample_decks.py`
now builds a large fixed core plus a small flex pool, and deliberately plants two
different archetypes in one ink pair under several names each, so the sample exercises
the hard case.

---

## 4. Copy counts: mode and spread, not just mean

Different builds run different counts of the same card, so a mean answers the wrong
question. From 45 real lists of one archetype:

| Card | Inclusion | Mean | Reported | What the lists do |
|---|---|---|---|---|
| Grandmother Willow - Ancient Advisor | 100% | 4.00 | **4×** | `4x:45` |
| Hamm - Piggy Bank | 100% | 3.78 | **4×** | `1x:1 2x:1 3x:5 4x:38` |
| Ursula - Whisper of Vanessa | 96% | 2.40 | **2×** | `1x:2 2x:28 3x:7 4x:6` |

2.40 invites "so, 2 or 3?" when 28 of the 43 lists have already answered: exactly 2.

Each card therefore reports the mode (`typical_copies`), the full spread
(`copies_spread`), and the mean for reference. Ties in the mode go to the higher
count — when preparing, the assumption that hurts more is the useful one.

`expected_copies` on the threat board stays a true expectation over the whole field
(inclusion × pair share), deliberately fractional, because that is the correct thing
to rank tech against: a four-of in a 5% deck matters less than a two-of in a 25% deck.

**Bug caught while writing this:** the distribution was first counted per decklist
*line*. One card split across two lines — a paste divided by section, or two
printings of a name — landed in two bins and counted as two decks for inclusion,
inflating both. Counts are now totalled per deck first.

---

## 5. The pagination bug that would have made every report wrong

Pager links arrive HTML-escaped, so the character before `page=` is `;`:

```html
<a href="/lorcana-decks/core?deck_type=tournament&amp;page=2">
```

The regex `[?&]page=(\d+)` matched **nothing**. `max_page()` returned 1, pagination
stopped after the first page, and a window the site reports as **369 decks** produced
a report of **20** — eighteen times under, with no error and entirely plausible
output.

Two failures compounded it:

1. The test asserted `max_page(...) >= 1`, which passes when the function finds
   nothing at all. Assert the number, not that a number exists.
2. The **fixture was built with the same broken regex**, so it contained no pager
   links and could never have caught the bug. A fixture derived from the code under
   test is not a test.

The fix added a safety net that does not depend on the pagination code at all:
`total_decks()` reads the count the site prints itself ("369 decks"), and a build that
collects less than 90% of it warns loudly.

---

## 6. Being a good guest, and what the site actually pushes back with

Every number here was measured, not guessed.

| Behaviour | Why |
|---|---|
| Browser-shaped User-Agent | Cloudflare rejects unrecognised ones: a plain browser string returns 200, the same string with `lorcana-meta/0.1` appended returns 403. Override via `INKDECKS_USER_AGENT` if they ever ask for something specific. |
| No cookies kept | With a session, request 2 onwards returned 403 **at any delay**. The culprit is the site's own `PHPSESSID` — their rate limiting counts per session. Stateless requests: 6/6 succeeded. |
| One request at a time, 3s default | 6 of 20 requests hit a 429 at 2s. |
| Delay widens ×1.25 on a 429, eases ×0.9 after 10 clean, remembered between runs | At ×1.5 a single 429 hitting one page twice took the delay 8.6s → 19.3s and the whole rest of the run crawled — and the remembered rate carried it into the next run. Meanwhile steady-state gaps showed 8.6s accepted without complaint. |
| A refused deck is skipped, not fatal | One page returning 429 three times killed a 369-deck run at deck 100. One decklist moves a percentage by 0.3%; the run cost an hour. Eight refusals in a row still stops it — at that point it is the site. |
| Decks fetched best-placed first | The limit means a large window is realistically built across sittings. Whatever a run manages should be the part that matters. |
| Deck pages cached forever | A published decklist never changes. |
| `--top` maps onto their own filter | A top-8 report fetches 8 listing pages instead of 41. |
| One build at a time (lock file) | See below. |

**cloudscraper is a fallback, not the default path.** The site's pushback under
load is `429` — a rate limit — and the answer to a rate limit is to slow down, never
to switch HTTP client. It escalates only on a persistent `403`, and only if
installed. inkdecks confirmed it is acceptable if needed; without that it would be
circumventing a security control.

It is installed by default all the same, as part of the `inkdecks` extra. It started life behind its own extra, and that split cost more than it saved: the fallback fires mid-run, hours into a build, and "install this and start over" is a bad thing to discover then. Installed-but-idle is the cheaper failure.

### 2026-08-28: Cloudflare started blocking by client fingerprint

Every Python client on the machine began getting 403 on every path, the site root
included, while a browser on the same connection was served normally. No
`Retry-After`, no 429 - a WAF block keyed on *what the client is*, not on address or
rate. The Ray ID and IP were captured; the block page's own advice is to send them
to the site owner.

**cloudscraper did not help**, which corrects the earlier note in this file. It
solves the older JavaScript challenge and still speaks Python's TLS, so it presents
the fingerprint being refused. Tested against the live block: 403, same as plain
`requests`.

**curl_cffi does help** - it presents a real browser TLS fingerprint, and returned
200 with the deck rows intact. After a deliberate decision by the maintainer it is
the escalation path: `auto` tries plain HTTP, and switches only once the client has
been refused and backing off has not helped. Which transport worked is remembered in
the cache, so a standing block is not rediscovered at the cost of two refusals and a
minute of backoff on every build.

The grounds, recorded because they are what makes this legitimate rather than a
technique to reuse:

1. inkdecks gave written permission for automated access, personal use.
2. They said they cannot practically allow-list an address - their side is not
   especially technical and the work appears to be outsourced.
3. They approved a bypass tool if one turned out to be necessary.
4. The maintainer made the call knowingly, and it was theirs to make.

Remove any one and this is circumventing a security control. **Do not carry the
pattern into another project**, and do not widen it here.

It changes the handshake, not the crawl: same two paths, same one-at-a-time pacing,
same cache, same read-only wrapper.

Which brings us to the part that was worth doing regardless. inkdecks asked that the
crawl not disturb the site, and "it only reads" should not be a promise you verify by
reading code. The session is now **structurally read-only**: `ReadOnlySession`
exposes `get` and raises on `post`, `put`, `patch`, `delete` and `request`, whichever
transport is underneath. Bytes read are counted and logged. Tests assert all of it,
plus that every path this source can build stays clear of the `robots.txt` Disallow
list - which is precisely their write-shaped endpoints.

A related trap, hit for real: `pip install cloudscraper` in an un-activated shell installs into whichever Python is on PATH, which is not the `.venv` the build uses. The package was demonstrably installed and the build still said it was missing. The error message now names `sys.executable`, so the mismatch is visible rather than baffling.

### The concurrency mess

"One request at a time" only ever held **inside one process**. An interleaved log
revealed two builds fetching simultaneously, each dutifully waiting its own 20
seconds. Worse: `pkill` from Git Bash does not kill Windows processes — it reported
success while **eight** builds kept running, which is what pushed the throttle to its
ceiling and made the first published timing estimates roughly twice too pessimistic.

Fixes: a lock file in the cache directory refuses a second build, with a liveness
check so a lock left by a killed process is taken over at once rather than after a
two-minute timeout. And on Windows, kill processes with PowerShell, never `pkill`.

**Measured throughput, single process: ~4–9 deck pages per minute**, settling around
6–7s between requests. A 14-day top-32 window is ~370 decks. Trust a real run's log
over any number written here.

---

## 7. Windows was a first-class target, and it bit repeatedly

- `PYTHONPATH=src python -m lorcana_meta` is POSIX shell syntax; PowerShell reads it
  as a command name. Fixed by `pyproject.toml` + a console script, so one command
  works everywhere.
- Card names are not ASCII. On a legacy code page `print` raises
  `UnicodeEncodeError` and `logging` degrades to `アリ...` — unreadable
  exactly in the line reporting unmatched names. Hence `console.configure_output()`.
- In Windows PowerShell, native stderr becomes a `NativeCommandError`, so
  `$ErrorActionPreference = "Stop"` plus a pip notice aborts a script that succeeded.
  Scripts check `$LASTEXITCODE`.
- `pip install --upgrade pip` in a fresh venv left a broken pip
  (`No module named 'pip._internal.cli'`). Removed; the venv ships a working one.
- The CLI logs to stdout, not stderr, so a normal build does not render as a red
  error block.
- CI runs the suites on Ubuntu **and** Windows, plus one job with `PYTHONIOENCODING=cp1250`.

---

## 8. Visualisation choices

Charts compare magnitude, so **every mark is one hue and length carries the value** —
colouring bars by category would spend the only free channel on information the bar
already shows.

Ink colours are a **fixed semantic palette**, like status colours: Amber is Amber.
Six domain-locked hues cannot clear colourblind-separation gates (Sapphire vs
Amethyst measures ΔE 4.1 under deuteranopia; Steel is grey by definition), so an ink
chip always carries a 3-letter code and the ink's name in text. All twelve steps
clear 3:1 against their surface.

Every chart has a table twin, values sit at bar tips, and the copy-count spread uses
one hue at stepped opacity — an ordered scale, never hue carrying the order.

---

## 9. Things deliberately not done

- **No scraping of any site whose terms forbid it without permission.** Ask, or copy
  by hand.
- **No Cloudflare bypass by default.** See §6.
- **No `beautifulsoup4` in the core install.** It is an `[inkdecks]` extra, so
  someone using only local decklists carries nothing they do not use.
- **No regex parsing of the site's HTML structure.** bs4, matched by content.
- **No committing of full pages from inkdecks.** Fixtures are trimmed excerpts;
  permission to read a site is not permission to redistribute it.
- **No git operations.** The user runs those.
