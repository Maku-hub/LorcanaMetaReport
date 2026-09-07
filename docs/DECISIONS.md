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
report and `tests/check_report.py` fails on it, so any route that publishes has to be
told to proceed past a failing check. The Pages workflow that used to run that check
before deploying was itself deleted later (section 10) - the chain now has one fewer
link because it has one fewer way out.

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

**A 429 and a 403 get opposite answers.** The site's pushback under load is `429` — a
rate limit — and the answer is to slow down, never to switch HTTP client. A `403` is
a different problem entirely; see the next section for how that one resolved.

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
now the **only** transport.

It was briefly a fallback, with plain HTTP first and escalation on a persistent 403,
plus a remembered-transport cache file so a standing block was not rediscovered every
run. That worked and was still the wrong shape: every run began by earning two 403s
and a minute of backoff, and it cost a transport switch, a cache file and a branch in
the retry loop to manage a choice that only ever had one right answer. One client
that works beats two clients and the machinery to pick between them.

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

Two related traps, both hit for real:

- `pip install <anything>` in an un-activated shell installs into whichever Python is
  on PATH, not the `.venv` the build uses. The package was demonstrably installed and
  the build still said it was missing. The error message now names `sys.executable`,
  so the mismatch is visible rather than baffling.
- The HTTP client and the HTML parser lived in an `[inkdecks]` extra while the
  documented install was `pip install -e .`. That quietly produced an installation
  that could not read the default source. **There are no extras now** — one dependency
  list, and the documented command installs all of it.

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

## 9. The report was 868 KB, and 37% of it was working notes

The whole `meta.json` is loaded by the browser and inlined into `report.html`, so
anything in it that nothing reads is weight paid for on every open. A real 320-deck
build was 868 KB. Two things were wrong with it.

**Working fields shipped alongside the finished ones.** `avg_copies_overall` and
`total_copies` existed to compute expected copies; `edge` and `is_character` to rank
signature cards; `pair_share` to weight a threat. Every one of them is final by the
time the report is written and none has a reader in `site/assets/app.js`. `_lean()`
in `cli.py` strips them last, once every derived number exists, and prunes `cards`
down to the printings something still points at.

**Brews carried card tables that said nothing.** At the 0.60 threshold a real field
is about 15 archetypes and 60-70 one-off lists. For a single deck, "inclusion" is
100% on every card it plays and the copy spread is a single bin — that is a decklist
wearing the clothes of an analysis, and it was 320 KB of the file. Brews keep their
label, deck count, share, record, tells, player-submitted names and finishes; they
lose the card table and the cost curve, and the About page says so with a count.

Together: 868 KB → 541 KB, 38% smaller, with nothing removed that anything read.

The trap here is that both halves are silent failures in opposite directions. Drop a
field the page reads and you get a blank cell, not an error. Keep a field nothing
reads and nothing ever tells you. So `tests/test_report_shape.py` holds both lines at
once: every key in a built report must have a reader somewhere, and everything
`_lean` strips must have no reader at all. Exceptions are enumerated by name with
their consumer, because an unexplained exception is indistinguishable from a key
nobody wants. It earned its place immediately — it caught a `min_decks_per_half`
constant emitted for a page that never asked for it.

---

## 10. Movement: one window cut in half, and what that may not claim

The report shows which decks are gaining and losing share. Three choices make that
number honest rather than merely present.

**Split by calendar date, not by deck count.** Halves of equal length are what "the
back half of the window" means to a reader. Balancing on deck count instead would let
a quiet weekend move the boundary, and would present two unequal stretches of time as
if they were not.

**Cluster once, over the whole window.** Clustering each half separately would leave
the report matching archetypes across halves — which is the exact problem card
overlap exists to avoid (§3), reintroduced for no gain. The clusters are built on the
full window and their members are merely counted per side, so an archetype has one
identity and both halves refer to the same thing.

**Round before subtracting.** The delta on screen is the difference between the two
percentages printed beside it. Subtracting raw shares and rounding afterwards leaves
the displayed arithmetic off by a tenth, which reads as a bug to anyone who checks
it — and someone always checks the one number they were about to act on.

What it may not claim: it is not a comparison with a previous report, and a fortnight
has weather. One large event landing in the second half moves every share in it. So
deck counts sit next to every percentage, the section states the split in words, and
movement is withheld rather than guessed at — under 15 decks in a half, or a window
under 4 days, and there is no section, only a line saying which of those it was. A
row needs 8 decks before it gets a delta at all: a deck seen three times can swing
twenty points on one list. On a real 320-deck fortnight that leaves about nine rows
with movement and seventy without, which is the honest picture.

Withholding had to be checked as carefully as showing. `tests/check_report.py` now
fails if the halves do not account for every deck, if a row carries a delta while the
report says movement is unavailable, or if a delta is not the difference between its
own two shares. All three were verified by breaking a good report on purpose.

A side effect worth recording: writing the undated-deck test found that a single deck
with no `tournament_date` had always crashed the whole build, in `_examples`, sorting
`None` against a string. Neither real source omits the date, so nothing had hit it —
but the paste importer can, and it is a `TypeError`, not a wrong number, so it takes
the report with it.

### Where the delta goes, and the chart that does not add up

Movement first shipped as its own "What is moving" section: a table of the biggest
movers, ranked by absolute delta. It was wrong next to the archetype chart. Two
tables about the same decks stood side by side with different memberships - one
ranked by share and one by movement, one mixing ink pairs in with archetypes, one
truncated to twelve rows, one filtered by the 8-deck floor - and the reader was left
to work out why they disagreed. The delta now sits in a **Movement** column beside
the share it belongs to. One row per thing, in one place.

Removing that section exposed a second problem, and a real one. The overview's three
charts are three cuts of one field, so a reader will add one up and compare it with
another. Two of them cover every deck. The archetype chart does not - brews are left
out - and on a real 320-deck field that is **15 archetypes covering 74% against 67
one-off lists holding the other 26%**. The subtitle said "67 one-off brews are left
out of this chart", which gives the count and hides the scale: nothing on the page
let you discover that the bars stopped at 74%.

The chart now states the arithmetic. The fix was not to chart the brews - a single
26% "brews" bar would rank near the top and read as though the biggest deck in the
meta were a category - but to name the missing quarter where the reader meets it.

`check_report.py` gained the reconciliation that must never drift: every deck in
exactly one archetype of its pair, archetype shares of a pair summing to 100%, each
ink's deck count equal to the pairs that ink appears in. Verified by breaking a good
report four ways.

One test lesson from the same pass: `test_report_shape.py` matched a key name
anywhere in `app.js`, so `withDefaults()` - which *writes* defaults for an older
report - made `undated_decks` look read when nothing read it. A reader-scan that
counts writers is false assurance, which is the one thing that file exists to
prevent. Its body is now excluded.

---

## 11. Deleting the publish workflow

`.github/workflows/publish.yml` was manual-dispatch only, could publish `local` data
only, and ran `check_report.py` before deploying. It was careful, and it is gone.

It was the only mechanism in the repository that could make anything public, in a
project whose requirement is a private report. Its safety rested on three guards
holding simultaneously, and it had never been used once. Three guards protecting a
capability nobody wants is not defence in depth; it is a thing that can go wrong for
no benefit. `git log -- .github/workflows/publish.yml` has it if a public page from
redistributable decklists is ever actually wanted.

`ruff check` moved into CI in the same pass, as a separate single-platform job: lint
results do not vary by OS, and a style complaint must not be able to hide a real test
failure in the matrix. The linter is pinned — an unpinned one turns someone else's
release into your red build. It had already earned its keep: it was a linter, not a
test, that found the `NameError: name 'sys' is not defined` a `git checkout` left in
two of the inkdecks error handlers (§6).

---

## 12. Testing the page, and two tests that were lying

The presentation layer was the last untested thing in the project: 1300 lines of
`site/assets/app.js`, the entire readable surface of the report, verified by opening
it and looking. Every page bug in this project was found that way - an empty "Curve
and card types" card on a brew, "A one-off lists" for two decks, an archetype chart
whose bars stopped at 74% of the field in silence, a missing movement block throwing
during render and leaving a blank page. That last one is the worst failure this
project has, because a blank page carries no clue at all.

`tests/test_render.mjs` closes it. Plain node, no npm, no packages: it evaluates
`app.js` and calls the renderers. The one change to production code was replacing the
bare `boot()` at the end with `if (typeof document !== "undefined") boot();` - a test
that has to cut a call out of the file with a regex is testing something else.

It loads the built report once and mutates copies in memory to reach states a sample
field may not contain - a brew, a report with no `trend` block, an empty field, an
unknown route. A test that quietly skips when the field lacks a brew is not a test.

Eleven deliberate breakages, eleven caught. The first version caught only ten: the
movement check looked for a `Movement` column *header* and a mutation that emptied
every cell under it passed. A column of blanks is precisely the silent failure being
guarded against, so the helper now returns the first data row too.

### Two checks that approved things by coincidence

`test_report_shape.py` matched a key name anywhere in `app.js`. Two consequences, both
found by looking rather than by the test failing:

* `withDefaults()` *writes* defaults for a report built before movement existed, so it
  mentions every field it fills. That made `undated_decks` look read when nothing read
  it. A reader-scan that counts writers is false assurance - the one thing that file
  exists to prevent. Its body is excluded now.
* `totals.variants` has no reader in the page at all, but `pair.variants` does, so the
  name matched and the field was approved by accident. It turned out to be legitimate
  - `check_report.py` reads it - but the approval was luck, not reasoning. Matching is
  now by access path, and `READ_ELSEWHERE` is keyed by full path so an exemption
  cannot silently cover a same-named field elsewhere.

Where the parent is a list element (`pairs[].variants`) the chain is broken by the
indexing and cannot be matched without parsing the JavaScript, so those still fall
back to the name. The convention that makes path matching work is already in the file:
name a local after its field, as `anomalies`, `totals` and `filters` all do.

### The report now says what built it

It recorded the window, the placing cut and the clustering threshold - everything
about the *question* - and nothing about the code that answered it. A `report.html`
gets opened weeks later, and "which build produced this" was the first thing you would
want and the one thing it could not tell you. `built_by` carries the package version,
the short commit, and whether the tree was dirty.

`dirty` is the point of it. A report built from a working tree with uncommitted
changes cannot be reproduced from the commit it names, and a stamp that hides that is
worse than no stamp because it looks trustworthy. Git being absent is not an error - an
install from a wheel has no repository - and the stamp reads "unknown" rather than
inventing one.

---

## 13. The threat board was averaging the thing this project exists not to average

Section 3 is about why archetypes come from card overlap: 56 decks sharing
Amber/Amethyst were 7 different decks, and averaging a card across them produces a
number nobody plays. The threat board was doing exactly that, in the one view whose
whole job is "what should I prepare for".

On real data it read **"Maleficent - Vengeful Sorceress, played by Amber/Amethyst
63.2%"**. Inside that pair, one archetype ran it in every list and the other ran it in
none. 63.2% invites preparing for a coin flip when the truth is "one deck always has
it, the other never does" - and which one is across the table is precisely what the
signature cards tell you. The README already claimed card figures were computed within
an archetype; for this view that was not true.

Three things came out of fixing it.

**The attribution moved to archetypes, and brews had to be pooled.** Brews carry no
card table in the report (§9), so an attribution assembled from the report alone would
have lost a quarter of a real field, invisibly. They are pooled per ink pair instead:
one contributor row saying "One-off lists (Amber/Amethyst)". Listing them individually
would be worse than useless - each is a single deck, so every card in it reads 100%
inclusion, and thirty such rows would bury the decks worth preparing for.

**`expected_copies` and `field_presence` now come straight off the field.** They were
weighted sums over ink pairs, which was *exact* - pairs partition the field, so the
weights collapse to "copies in the field over decks in the field" - but it made the
numbers look grouping-dependent when they are not. The existing test's assertions did
not change by a digit, which is the proof the identity held.

**The thin-pair filter moved into `build_meta`.** It used to run afterwards in
`cli.py`, walking back over a finished report re-deriving every share and rebuilding
the threat board against a new denominator: two chances to leave a number quoted
against a field that no longer existed. Dropping first and computing once removed the
function entirely.

### Cards carry movement, and one bug the tests found on the way

An archetype rising tells you which deck to prepare for. A card rising tells you what
to prepare for regardless of which deck brings it, and that can happen with no
archetype moving at all - so cards get the same window split and the same row floor.

`test_report_shape.py` then flagged `archetype_count` as having no reader, which
turned out to be a display bug rather than dead weight. The contributor list is capped
at six for size, and the page computed its "+N more" badge from the shipped list - so
a staple played by fifteen archetypes advertised "+3". The field is now
`contributor_count`, the badge reads from it, and a synthetic 15-archetype field
confirmed +12 where the old code said +3.

Two of the new page tests passed against deliberately broken code before being
tightened, and both failures were the same shape: asserting that a word appears
somewhere rather than that the thing works. `html.includes("Movement")` passed with
the column deleted, because the legend below the table also says "Movement"; the
inspector test called the lookup function directly and passed with the inspector
rendering none of what it returned. The fixes were to assert the `<th>` specifically,
and to split `inspectCard` out of `showCard` so the markup can be checked without a
DOM.

### Printing

`@media print` hid the toolbar and stopped there, so printing produced a page of empty
rectangles: every bar is a div with a background, and browsers drop backgrounds when
printing. The marks now force `print-color-adjust`, cards and chart rows avoid page
breaks, table headers repeat across pages, the palette is forced light so a dark-theme
report does not print white on white, and external links print their destination.
The block also had to move to the end of the stylesheet - a media query carries no
extra specificity, so the ordinary rules that followed it were quietly winning.

---

## 14. Things deliberately not done

- **No scraping of any site whose terms forbid it without permission.** Ask, or copy
  by hand.
- **No Cloudflare bypass anywhere else.** See §6 for the four conditions that make it
  legitimate here and nowhere else.
- **No optional-dependency extras.** One list. An extra that the documented install
  command did not include is worse than a slightly larger install.
- **No wrapper scripts.** There were four PowerShell ones; they duplicated the CLI,
  drifted from it, and doubled the surface to keep working. One way to run it.
- **No publish workflow.** See §11.
- **No card tables for one-off brews.** See §9. They keep everything that identifies
  them; they lose statistics that a single deck cannot support.
- **No npm, and no test framework.** `test_render.mjs` is plain node calling plain
  functions (§12). A dependency that has to be installed before a test runs is a
  dependency that stops the test being run.
- **No month-over-month comparison.** Movement is one window split in two (§10).
  Comparing with a previous run would mean storing past reports and reconciling
  archetype identity across them - two new problems for a number the split already
  answers.
- **No regex parsing of the site's HTML structure.** bs4, matched by content.
- **No committing of full pages from inkdecks.** Fixtures are trimmed excerpts;
  permission to read a site is not permission to redistribute it.
- **No git operations.** The user runs those.
