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

Hence `lorcana_meta/bundle.py`, run at the end of every build: CSS, JavaScript and data inlined into one
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

## 14. A results axis, and why the cut is the reader's choice

Everything in the report was a popularity axis: how many people played a deck. None of
it said whether the deck won. The two are routinely different, and on a real field they
disagreed sharply - the most played archetype held **19.4% of the field and 11.1% of
the top-8 finishes**, with the lowest match win rate on the board. The overview opened
with a chart that put it first and gave no hint of any of that.

The data was already there. `top8_decks` was computed and displayed as a bare count on
one page; `win_rate` existed and lived in a tooltip. What was missing was the
comparison: a share of the winners against a share of the field.

### Neither cut is neutral, so both are offered

An absolute cut ("top 8") is the same eight places at every event, so making it at a
24-player store event counts the same as at a 210-player regional. A percentage cut
("top 10%") fixes that and introduces its own problem: it interacts with `--top N`.
Where the fetched cut is deeper than the percentage, a large event contributes nearly
every deck it has to the "winners" pool while a small one contributes only its
winners.

Rather than pick one and describe the bias in prose, each cut **measures** it.
`vacuous_events` counts the events where the cut excludes nothing we hold - the events
it hands to the winners for free. Measured on a real-shaped field:

| cut | in the cut | of the field | excludes nothing at |
|---|---|---|---|
| Event wins | 2 | 3% | 0 of 4 events |
| Top 10% | 22 | 35% | 0 of 4 events |
| Top 8 | 18 | 29% | 0 of 4 events |
| Top 25% | 41 | 66% | **2 of 4 events** |

That decided the default. Top 25% holds two thirds of the field and separates nothing
at half the events, so it is offered with the warning attached rather than chosen. Top
10% is the default because it normalises event size and still excluded decks
everywhere. Event wins is honest and too thin - two winners in a 62-deck field, below
`MIN_CUT_DECKS`, so it is withheld with its arithmetic rather than charted as noise.

### A bucket is a bound, and "cannot tell" is not "no"

inkdecks mixes exact placings with buckets, and `parse_standing` already mapped "Top8"
to 8 as an upper bound. That is right for a top-8 cut and wrong for anything tighter: a
deck labelled "Top8" may have won the event, so against a top-4 cut it has no answer.
Answering "no" would move winners out of the winners' column - a wrong number that
still looks completely sane, in the one place someone might change their deck over.

So `standing_exact` now travels with the placing, `_in_cut` returns three-valued
`True` / `False` / `None`, and only a placing known to be exact can put a deck
*outside* a cut. Decks a cut cannot judge are counted and named on the page.

Everything on this axis is also conditional on having made the fetched `--top N` cut,
which is stated where the numbers are: it is which of the decks already doing well went
furthest, not a win rate against a whole tournament.

### Three things this pass found by accident

**The sample generator was producing impossible tournaments.** Placings were drawn with
`rng.randint`, so three decks could share 1st place in one event. Every cut computed
against that data would have been meaningless, and the tests would have validated it.
Placings are now dealt without replacement.

**The thin-pair filter had to move, and a guard was quietly wrong.** Moving it into
`build_meta` (§13) changed `totals.decks` from "everything that resolved" to "the field
the report describes". `check_report.py` was still subtracting the dropped decks a
second time and only said so once a real drop occurred. It now asserts the funnel
instead: resolved equals field plus dropped.

**`test_report_shape.py` was checking less than it appeared to.** Three separate
holes, each found by a mutation rather than by the test failing on its own:

* the `DATA_KEYED` flag was carried down instead of marked, so it stayed set one level
  too deep and **every field of a card payload went unchecked** - `cost`, `text`,
  `image`, all of it. Dynamic-key hops are now marked `{}` in the path and the flag
  applies to exactly one level.
* `DATA_KEYED` was keyed by field *name*, and `results` is a cut-keyed map on a pair
  but a plain block at the top level. One name, two shapes, and the rule silently
  applied the wrong one to both. It is keyed by full path now, each entry naming what
  its keys are.
* the fallback for list elements matched the bare word, so the literal " lore" in a
  badge label passed for `cards{}.lore`, and a helper named `edgeText` passed for the
  `edge` field that `_lean` strips. It requires a property access now.

Path coverage went from 148 to 190 fields. One limitation stays, documented: a field
under a list index cannot be chain-matched without parsing the JavaScript, so
`results.cuts[].share_of_field` is satisfied by `archetype.share_of_field`. Building a
JS parser to close that is not worth it.

**And the heredoc trap caught me again.** Writing that regex through a shell heredoc
turned `\b` into a literal backspace, so the pattern was `\.totals\x08` and never
matched anything - the test passed while checking nothing. CLAUDE.md warns about this
for Windows paths; it applies to regex escapes just as well. Use the editing tools for
anything containing a backslash.

---

## 15. What the first real report caught

The results axis was built and tested against synthetic data where every placing was
an exact number. The first build from inkdecks showed what the source actually
publishes, and two things were wrong.

### Placings are brackets, and a bracket is a range

Across 842 cached decks the only exact labels were **1st (48), 2nd (43), 3rd (45)**.
Everything else carried `Top4` (44), `Top8` (148), `Top16` (227) or `Top32` (287).

The site shows the tightest descriptor it has, so these are **disjoint**: a deck it
calls `Top8` is one it did not call 1st, 2nd, 3rd or Top4, which means it lost in the
quarter-finals and finished 5th to 8th. `TopK` is places `K // 2 + 1` through `K`.

The code read a bracket as nothing but "no worse than K", which is true and useless.
With only an upper end, a deck can be placed *inside* a cut and never *outside* one:

| top-8 cut | in | out | cannot tell |
|---|---|---|---|
| upper end only | 328 | **0** | 514 |
| bracket as a range | 328 | 514 | **0** |

Zero exclusions is why `vacuous_events` - the measure built to catch a cut that
separates nothing - reported **20 of 20 events for every cut**. The page duly printed
"at 20 of 20 events this cut excludes nothing, so the comparison is weaker than it
looks" above a chart that was in fact fine, which is the worst way to be wrong: a
correct chart under a warning telling the reader to discount it.

`standing_best` carries the other end now. Both ends decide: inside if the worst end
clears the cut, outside if the best end does not, and unknown only when the bracket
straddles the line. On the real report:

| cut | in cut | cannot tell | excludes nothing at |
|---|---|---|---|
| Event wins | 18 (unchanged) | 422 → 0 | 2/20 → 0/20 |
| Top 10% | 119 (unchanged) | 356 → 68 | 20/20 → 5/20 |
| Top 8 | 134 (unchanged) | 341 → 0 | 20/20 → 3/20 |
| Top 25% | 268 (unchanged) | 207 → 167 | 20/20 → **17/20** |

The counts that feed the shares did not move, so the rankings were right all along -
only the two fields that tell a reader how much to trust them were wrong. And Top 25%
now shows its real colour: it excludes nothing at 17 of 20 events, which is exactly
what that measure exists to say.

One consequence worth noting: a cut on a bracket boundary (top 8) places every deck,
while a percentage cut slices across brackets and leaves some unplaceable. On this
source top 8 is the better-determined cut even though a percentage is the more
principled measure.

### Unjudged is not failed

`conversion` divided by all of a group's decks, so a deck the cut could not place
counted against it. Which archetypes have decks sitting on a bracket boundary is an
artefact of how the source labels results, so that was penalising archetypes for the
labelling. The denominator is now the decks the cut could judge, with the unjudged
count published beside it.

### And two things in the checks themselves

**A tolerance copied from a smaller table.** `check_report.py` allowed archetype
shares of a cut to sum to 100% ±1 point. Every share is deliberately rounded to a
tenth so the numbers a reader adds up are the numbers on screen - which means a sum
over 72 contributing archetypes can drift 3.6 points with nothing wrong. The real
report was reported as broken three times over. `_rounding_drift(rows)` scales the
tolerance now, and the exact check that matters - deck counts - was passing all along.

**A prose assertion that broke on a line wrap.** Text in the page lives in template
literals and keeps their indentation, so a regex for a phrase that happens to wrap
matched nothing. `prose()` collapses whitespace before any assertion on a sentence -
a test failing for a reason unrelated to the page is the worst kind.

---

## 16. Bundling belongs to the build

The single file was a second command, and the argument for folding it in was not the
keystroke. The two-step version let `report.html` go **quietly stale**: rebuild the
data, forget the bundle, open the file - it renders perfectly and shows the previous
window. The embedded build stamp is the only clue, and it only helps someone who
thinks to look, which is exactly the class of failure this project keeps closing.

For the default source it was never optional anyway: an inkdecks report may not be
published, so the local file is the only way to read it.

The logic moved from `tools/` into `lorcana_meta/bundle.py`, because `tools/` is not on
the import path of an installed package - the first attempt at calling it from the CLI
died on `ModuleNotFoundError`. It is not a side utility; it is the product's only
private output. `tools/bundle_report.py` stays as a thin entry point for re-bundling
without refetching, and `--no-bundle` covers serving `site/` directly.

Bundling still needs `site/` from a checkout, which a wheel does not carry. A build
without it warns and writes the data rather than failing.

---

## 17. The win rate was measuring the wrong thing, and saying otherwise

inkdecks publishes a matchup matrix at `/meta/winrate/`, and looking at it to decide
whether to import it turned up a defect in this report instead.

Their matrix over **our own window**, grouped by ink pair, against our `record.win_rate`
for the same pairs:

| pair | ours | theirs (every match) | gap |
|---|---|---|---|
| Amber / Amethyst | 60.1% | 55% (1299 matches) | +5.1 pp |
| Amethyst / Steel | 61.2% | 46% (317) | +15.2 pp |
| Sapphire / Steel | 55.6% | 36% (200) | **+19.6 pp** |

**Higher in every pair without exception, by 11 points on average.** Our figures span
55.5%-63.8%, a range of 8 points; theirs span 25%-59%, a range of 34.

The cause is not a bug in the arithmetic - it is the sample. Every deck in this report
finished inside `--top 32`, and a list that made the top 32 won most of its matches by
definition. So the metric is "win rate among decks that already placed", which is
informative in relative terms and nothing like what the label "Match win rate"
promised. A reader looking at Sapphire/Steel saw 55.6% for a deck that wins 36% of its
games.

Worse, the previous session had *promoted* this number from a tooltip to a column and
called it "the sturdiest number available here" - true about its game count, wrong
about what it counts, and the 8-point spread means it barely separates decks anyway.

The fix is labelling, not arithmetic: `winRateLabel()` names the sample and
`winRateNote()` travels with it onto the results chart and the About page. The number
stays, because relative comparison between archetypes in the same sample is still
worth something.

The general lesson, which is the reason this section exists: a metric can be
arithmetically perfect, fully tested and reconciled by every check in
`check_report.py`, and still answer a different question from the one its label asks.
No amount of internal consistency catches that. It took an outside measurement of the
same field.

---

## 18. Archetype-versus-archetype: measured, and not possible

The most useful thing this report could hold is "the field is mostly these archetypes,
so play the one with the best win rate against them". inkdecks publishes a matchup
matrix and it can be grouped by archetype, so the question was whether to import it.

Measured on the largest sample that exists - the whole current set, all time, 13,072
matches:

| | cells | median matches | median published interval | >= 100 matches |
|---|---|---|---|---|
| archetype vs the field | 38 | 82 | 22 pp | 47% |
| **archetype vs archetype** | **884** | **3** | **84 pp** | **2%** |

Two cells of 884 hold 400 matches or more. A median interval of 84 points means a
typical cell says "somewhere between 10% and 94%".

What "properly" would cost: 38 archetypes make **703 distinct matchups**. At 400
matches each - enough to separate 55% from 45% - that is 281,200 matches. At a loose
100 each, 70,300. The page holds 11,920. Short by six times for the loose version and
twenty-four for a usable one, and that assumes a static metagame; in practice the data
would also have to fit inside a window short enough that the meta had not moved.

Two further blockers that survive any amount of data:

* **Their archetypes cannot be joined to ours.** Theirs are player-supplied names -
  `songs` and `song` as separate rows, `midrange` three times - and ours are clusters
  of card overlap named after signature cards. There is no key.
* **We can never compute it ourselves.** Decklists carry an aggregate W/L/D record and
  never who the opponent was. No pairing data, no matchup, at any grain.

So it is not built, and this is the measurement rather than an opinion.

The question behind it is a good one and the report answers the answerable form of it.
"Which deck beats this field" does not need 703 cells: the results axis (§14) measures
it directly, pooling all of an archetype's finishes, on our own clustering and our own
window - "22.7% of the top finishes on 11.3% of the field". What is genuinely missing
is the conditional part, "good against **these** decks", and that is exactly the part
the data cannot support.

An ink-pair matrix was also considered and rejected: over our window its cells ran to
a median of 10 matches and 58-point intervals, and averaging a card - or a win rate -
across an ink pair is the mush §3 and §13 exist to avoid.

---

## 19. Ranking the results axis on a rate, with its interval

Looking at inkdecks' matrix decided not to import it (§18) and changed what this
report ranks on instead, which turned out to be the more valuable outcome.

### The chart was ranked on the wrong number

"What is winning" sorted archetypes by their share of the top finishes. On the real
475-deck field that made the first bar **Grandmother Willow + Dumbo at 21.8%** - the
largest archetype, 108 decks, and one taking *less* of the top finishes than its share
of the field. The heading said "what is winning" and the leader was the deck that was
merely most played, which is the exact failure the results axis was built to fix. The
lift column beside it said -0.9, but bar length carries the value in this project's
charts, and the bar said "biggest".

Two independent reasons to rank on the conversion rate instead:

* Against inkdecks' win rate over the same window and the same pairs, Spearman
  correlation was **+0.79 for conversion, +0.66 for our own win rate, +0.56 for the
  lift**. n=11, so the ordering of those three is suggestive rather than settled.
* Lift barely varies. Across 23 archetypes it runs -1.7 to +3.6 points; the "Best
  converter" tile was showing `+3.6 pp`, a number indistinguishable from noise. On the
  8-archetype sample field it reached +11.4, which is why it looked fine in
  development. A hypothesis that lift systematically flattered small archetypes was
  checked and is false - size-to-lift correlation is -0.14.

Ranked on conversion, the same field reads: Darkwing Duck + Launchpad 55.6%, Taran +
Under the Sea 41.2%, David + Pocahontas 39.1%, and Grandmother Willow fifth at 28.6%.

### A rate without its interval is the same mistake again

Conversion on its own would have swapped one misleading leader for another: one
archetype held **three lists and converted all three**, which sorts to the top of
anything ranked on rate. So two guards, and both are needed:

* `MIN_RATE_DECKS` (8, the movement floor, deliberately the same number) keeps the
  thinnest rates off the chart, and what it excludes is counted with the share of the
  field the rest covers.
* every charted rate publishes a **Wilson 95% interval**. 40% from 25 lists is 23-59%;
  37.5% from 8 lists is 14-69%. Wilson rather than the normal interval because these
  samples are small and often at 0% or 100%, where the normal interval runs past the
  ends. The chart tells the reader to treat two archetypes as different only when the
  intervals miss each other.

`conversion` also divides by the lists the cut could **place**, not by all of them: a
knockout bracket straddling the cut is missing information, not a bad finish, and
charging it as one penalises whichever archetypes happen to sit on a bracket boundary.

### The guard that a real report needed

Rendering the user's existing report against the new chart produced **"Best converter
100.0% — Lantern + Demona, 3 of – lists"**. With `judged` absent from an older payload
the floor read as zero and let the three-list archetype through - the precise output
the floor exists to prevent, on the first report it met. `withDefaults` now marks such
a report `rankable: false` and the chart withholds itself with the reason. A default
that silently reads as "no floor" is worse than no default.

### And the order itself was a claim the data could not back

The first real report built on the new axis showed 14 archetypes in a neat descending
list, with a 9-list archetype at 44.4% sitting above a 141-list one at 41.1%. Checking
every interval against the leader's lower bound: **all 13 others overlapped it, and
none was measurably worse.** The order was an artefact of point estimates on a few
dozen lists each.

Sorting by the interval's lower bound would fix the order and break the chart - bar
length carries the value here, so a chart ordered by one number and drawn by another
looks wrong. Making the bar carry the lower bound would headline "at least 33.7%" for
a deck converting 45.8%, which is honest and much harder to read.

So the chart keeps the rate and disowns its own order in words: "the order here is not
a ranking… read it as a shortlist, not a league table." Where a real gap exists it
counts how many archetypes are clearly behind instead. The comparison that matters is
`other.high >= leader.low`, and the mutation using the wrong end survived every test
built on identical or disjoint intervals - only a partial overlap distinguishes them.

`liftText` lost its last caller in the same pass and was deleted. The rule about
nothing shipping that nothing reads applies to the page as much as to the payload.

---

## 20. The caveats had eaten the charts

Each of the last several passes added a sentence to a chart subtitle, and each was
earned: what the cut covers, why the interval is there, which events it fails to
separate, why some decks cannot be judged, what the win rate's sample is, what the
order does and does not claim. Measured together, the results chart's subtitle was
**331 words** and the overview carried **637 words** of subtitle prose above five
charts.

That is not a tidiness complaint. When everything is qualified at the same weight, the
qualifications that change how you read the chart are indistinguishable from the ones
that do not, and the reader skips all of them. The project spent this whole session
making numbers honest; a wall of text in front of them undoes that.

`barChart` gained a `notes` option, rendered as a disclosure titled "How to read this,
and what it leaves out". Subtitles dropped to 166 words across the overview and 507
words moved behind the disclosures - **nothing deleted**, which matters, because the
tempting way to shorten a wall of text is to delete it and every one of those
sentences is load-bearing. `test_render.mjs` caps each subtitle at 120 words and
separately checks that each note is still reachable.

Two details worth keeping:

* the check is **per chart**, not per page. A first version asserted a phrase appeared
  somewhere in the HTML, and passed when the ink chart lost its movement note because
  the pair chart still carried the same sentence.
* the print stylesheet forces every disclosure open and hides the summary. Paper cannot
  be clicked, and a caveat that only exists behind a toggle is worse on paper than one
  in the subtitle.

### A flag that looked like it did something

`--format` defaulted to "Core Constructed" and was then overridden by
`getattr(source, "fmt", ...)` for any source naming its own format - which the
default source does. Passing it with inkdecks changed nothing and said nothing. It now
defaults to `None`, so the CLI can tell "the user said nothing" from "the user asked
for this", and warns when it is ignored.

That default immediately produced a second bug: a `None` reaching `LocalSource`
intact became the literal string "None" as a format name on any deck file without a
`format` key - the sample data all carries one, so nothing caught it. Coerced at the
source now, with a test over `None`, `""` and a real value.

---

## 21. Things deliberately not done

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
- **No weighting by event size.** `tournament_players` is available and a multiplier
  like "a win at 300 players is worth five at 12" would be invented. The result cuts
  expose event size instead (§14) and leave the judgement to the reader.
- **No matchup table.** Archetype versus archetype needs roughly twenty-four times
  the data that exists, and their archetype labels cannot be joined to our clusters
  (§18). We hold no pairing data of our own at all.
- **No separating the deck from the pilot.** An archetype can be over-represented in
  the top finishes because strong players chose it, and nothing in this data can tell
  the difference. The About page says so rather than the report implying otherwise.
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
