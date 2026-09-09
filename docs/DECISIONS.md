# Decisions, and the traps behind them

Why the project is shaped this way. Most entries exist because something went wrong
first; the reasoning is recorded so it does not have to be rediscovered.

---

## 1. Sources and permission

**inkdecks.com has the widest tournament coverage and prohibits automated access.**
From their [terms of use](https://inkdecks.com/pages/terms), section *"PROHIBITION OF
AUTOMATED ACCESS & SCRAPING"*:

> You may not use automated systems (e.g., bots, scrapers, spiders) to access,
> extract, copy, or collect data from the Website without prior written consent. This
> includes using data for AI model training or machine learning algorithms.
>
> Exceptions: This restriction does not apply to publicly recognized search engines
> (e.g., Google, Bing) that comply with our robots.txt file.

The same page reserves *"technical measures such as IP blocking, rate limiting,
CAPTCHAs, and fingerprinting"*, and adds a liquidated-damages clause aimed at services
built on their data that compete with theirs.

**Permission was obtained** — personal use, no commercialised public site. Hence
`InkdecksSource` refusing to run without `INKDECKS_CONSENT=1`, and setting
`publishable = False`.

The condition is enforced, not just documented: `publishable` travels into the report
and `tests/check_report.py` fails on it, so any route that publishes must first be
told to ignore a failing check.

**Without permission**, `tools/import_pasted_decks.py` converts hand-copied lists
(`### name | player | placing | event | date | attendance`) for `--source local`.
Reading a page and copying a list yourself is not automated access; the tool fetches
nothing.

`robots.txt` disallows the site's write-shaped paths for everyone — `/decksubmissions`,
`/suggestions/add`, `/decks/similar-decks`, `/decks/visual`,
`/autocomplete/powersearch.json` — and a test asserts every path this source can build
stays clear of them.

An earlier version used TopDeck.gg's documented API. It was removed: coverage of
Lorcana was too thin to build a meta reading on, and a second source nobody used meant
a second parser and a second thing to keep working. It is in the git history. Do not
re-add it half way — `Deck` is the whole contract, and a source that fills half of it
produces a report that looks complete.

## 2. GitHub Pages cannot host a private report

> GitHub Pages sites are publicly available on the internet by default, even if the
> repository for the site is private or internal. […] To publish a GitHub Pages site
> privately, your organization must use GitHub Enterprise Cloud.

Access control is Enterprise Cloud only, and only for organization-owned repositories.
A personal account cannot make a Pages site private at all: private repo,
world-readable page, guessable URL.

Hence `lorcana_meta/bundle.py`, run at the end of every build: CSS, JavaScript and
data inlined into one `report.html` that opens from the filesystem. Verified in
headless Chrome over `file://` **without** `--allow-file-access-from-files`, which is
the difference between self-contained and nearly.

Bundling belongs to the build rather than a second command, because the two-step
version let `report.html` go quietly stale behind the data — it renders perfectly and
shows the previous window. `--no-bundle` skips it.

**There is no publish workflow.** One existed: manual-dispatch only, `local` data
only, running `check_report.py` before deploying. It was careful, unused, and the only
thing here that could make anything public. Three guards protecting a capability
nobody wants is not defence in depth. `git log -- .github/workflows/publish.yml`.

## 3. Archetypes come from card overlap, not names

Deck names are useless for grouping. One real archetype, one ink pair, the names
players submitted:

> Blurple · Brewing a Storm · I was there before it was cool · Stormlight Archive ·
> YP · Yeetple

Seven lists, six names, one deck — and two lists sharing a name can be different
decks. Grouping by ink pair alone is also wrong: 56 real Amber/Amethyst decks were
**7 archetypes**, and averaging across them leaves nothing reading as core.

So decks cluster on the **weighted Jaccard index** over card counts:

```text
similarity(a, b) = Σ min(aᵢ, bᵢ) / Σ max(aᵢ, bᵢ)
```

Copies, not just names — a list on 4 of a card and one on 1 are making different
choices, and set overlap cannot see it. Threshold 0.60; two lists differing by four of
sixty cards score ~0.87. Clustering is leader-based, best-finish-first, with a merge
pass that removes any dependence on visit order. A test shuffles the input five ways
and asserts identical clusters.

Archetypes are **named after the cards that distinguish them** from the rest of their
pair, preferring the expensive character a player would name the deck after.

Confirmed from outside: inkdecks' own matrix can group by archetype, and its groups are
`songs` and `song` as separate rows, `evasive` and `evasives`, `midrange` three times.
That is name-based grouping, and it is what this clustering exists to avoid.

## 4. Copy counts: mode and spread, not just mean

Different builds run different counts of the same card, so a mean answers the wrong
question. From 45 real lists of one archetype:

| Card | Inclusion | Mean | Reported | What the lists do |
|---|---|---|---|---|
| Grandmother Willow - Ancient Advisor | 100% | 4.00 | **4×** | `4x:45` |
| Hamm - Piggy Bank | 100% | 3.78 | **4×** | `1x:1 2x:1 3x:5 4x:38` |
| Ursula - Whisper of Vanessa | 96% | 2.40 | **2×** | `1x:2 2x:28 3x:7 4x:6` |

2.40 invites "so, 2 or 3?" when 28 of the 43 lists have answered: exactly 2. Each card
reports the mode, the full spread, and the mean for reference. Ties in the mode go to
the higher count — when preparing, the assumption that hurts more is the useful one.

`expected_copies` stays a true expectation over the whole field, deliberately
fractional: a four-of in a 5% deck matters less than a two-of in a 25% deck.

**Trap:** the distribution was first counted per decklist *line*. One card split
across two lines — a paste divided by section, two printings of a name — landed in two
bins and counted as two decks for inclusion. Counts are totalled per deck first.

## 5. Movement is one window cut in half

**Split by calendar date, not deck count.** Equal lengths are what "the back half of
the window" means. Balancing on deck count would let a quiet weekend move the boundary.

**Cluster once, over the whole window.** Clustering per half would mean matching
archetypes across halves — §3's problem, reintroduced for no gain. Halves only count
members of clusters built on the full window.

**Round before subtracting**, so the delta equals the two percentages printed beside
it. Someone always checks the one number they were about to act on.

What it may not claim: it is not a comparison with a previous report, and a fortnight
has weather. Deck counts sit beside every percentage. Under 15 decks in a half, or a
window under 4 days, movement is withheld with the reason in words — silence reads as
"nothing moved". A row needs 8 decks before it gets a delta; a deck seen three times
can swing twenty points on one list. A dash means "cannot tell", never zero.

The delta lives in a **Movement** column beside the share it belongs to, on all three
overview charts. It was once its own "What is moving" table, which put two lists of the
same decks side by side with different memberships — one ranked by share, one by
movement, one mixing ink pairs with archetypes, one truncated — and left the reader to
work out why they disagreed.

## 6. The results axis: what wins, not what is played

Everything else here is a popularity axis. On a real field the two disagree sharply:
the most played archetype held **19.4% of the field and 11.1% of the top-8 finishes**.

**Ranked on conversion** — lists reaching the cut over lists the cut could place — not
on a share of the winners, which puts the largest archetype first for being largest
under a heading saying "what is winning". Against inkdecks' win rate over the same
window, Spearman correlation was **+0.79 for conversion against +0.56 for the
share-gap**; and the gap spans only −1.7 to +3.6 points across 23 archetypes, so it
reads as noise. The gap stays as a column.

**The cut is the reader's choice**, because none is neutral. An absolute cut ("top 8")
is the same eight places at a 24-player store event and a 210-player regional. A
percentage cut normalises event size but interacts with `--top N`: where the fetched
cut is deeper than the percentage, a large event contributes nearly every deck it has.
So each cut **measures** its own bias: `vacuous_events` counts events the cut excludes
nothing from. On one real build, top 25% excluded nothing at 17 of 20 events.

**Every rate ships its denominator and a Wilson 95% interval.** 40% from 25 lists is
23–59%; 37.5% from 8 lists is 14–69%. Wilson rather than the normal interval because
these samples are small and often at 0% or 100%, where the normal interval runs past
the ends. `MIN_RATE_DECKS` (8, the movement floor) keeps the thinnest off the chart —
one real archetype had 3 lists and converted all 3, which tops anything ranked on rate.

**A sorted chart claims a ranking, so it says when there is not one.** On an
837-deck field every charted archetype's interval overlapped the leader's and none was
measurably worse, so the chart disowns its order in words. The comparison is
`other.high >= leader.low`; the wrong end passes every test built on identical or
disjoint intervals.

A report whose rates lack `judged` cannot be ranked at all — `withDefaults` marks it
`rankable: false` and the chart withholds itself. With the denominator missing the
floor reads as zero and the three-list archetype becomes "best converter".

## 7. A placing is a range, because inkdecks publishes brackets

Across 842 real decks the only exact labels were **1st (48), 2nd (43), 3rd (45)**.
Everything else carried `Top4` (44), `Top8` (148), `Top16` (227), `Top32` (287).

The site shows the tightest descriptor it has, so brackets are **disjoint**: a `Top8`
deck was not called 1st, 2nd, 3rd or Top4, so it went out in the quarter-finals and
finished 5th–8th. `TopK` is places `K // 2 + 1` through `K`. `standing` is the worst
end, `standing_best` the best.

Reading only the worst end is true and useless — a deck could be placed *inside* a cut
and never *outside* one:

| top-8 cut | in | out | cannot tell |
|---|---|---|---|
| upper end only | 328 | **0** | 514 |
| bracket as a range | 328 | 514 | **0** |

Zero exclusions is why `vacuous_events` reported 20 of 20 events for every cut, and the
page printed a warning telling the reader to discount a chart that was fine. Both ends
decide now: inside if the worst end clears the cut, outside if the best end does not,
`None` only when the bracket straddles it. Counts unchanged; the diagnostics were the
whole error.

Decks a cut cannot place are counted, shown, and left out of `conversion`'s denominator
rather than charged as failures — which archetypes sit on a bracket boundary is an
artefact of the labelling.

## 8. The win rate is conditioned on the cut, and says so

`record.win_rate` is computed over decks that all finished inside `--top N`, so a list
that made the cut won most of its matches by definition. Checked against inkdecks'
matrix over the same window, ours ran **11 points high in every ink pair**, turning 34
points of real spread into 8 — Sapphire/Steel wins 36% of its games and the report
said 55.6%.

`winRateLabel()` names the sample (`Win rate, top-32 lists`) and `winRateNote()`
travels with it. Never label it "match win rate".

The general lesson: a metric can be arithmetically perfect, fully tested and reconciled
by every internal check, and still answer a different question from the one its label
asks. No amount of internal consistency catches that; it took an outside measurement
of the same field.

## 9. Card figures are attributed to archetypes, never to ink pairs

The threat board read **"Maleficent - Vengeful Sorceress, played by Amber/Amethyst
63.2%"**. Inside that pair one archetype ran it in every list and the other in none —
the average of "always" and "never", which is §3's mush in the one view whose job is
"what should I prepare for".

Brews are pooled per pair (each is one deck, so every card in it reads 100%), and the
pool is what keeps every deck running a card attributed to exactly one group.
`expected_copies` and `field_presence` come straight off the field, not summed over
groups. The contributor list is capped for size, so the "+N more" badge reads from
`contributor_count`; computing it from the shipped list advertised "+3" for a staple
played by fifteen archetypes.

## 10. The report was 868 KB, and 37% was working notes

The whole `meta.json` reaches the browser and is inlined into `report.html`, so
anything nothing reads is weight paid on every open.

**Working fields shipped beside finished ones** — `avg_copies_overall`, `total_copies`,
`edge`, `is_character`, `pair_share`. All final by the time the report is written, none
read by the page. `_lean()` strips them last and prunes `cards` to the printings
something still points at.

**Brews carried card tables that said nothing.** For one deck every card is 100%
inclusion and the spread is one bin — a decklist wearing the clothes of an analysis,
320 KB of the file. Brews keep label, size, share, record, tells, names and finishes.

868 KB → 541 KB, with nothing removed that anything read.

Both halves fail silently in opposite directions: drop a field the page reads and you
get a blank cell, keep a field nothing reads and nothing ever tells you. So
`tests/test_report_shape.py` holds both lines, with exceptions enumerated by path and
consumer.

## 11. Charts, and caveats that fit

Charts compare magnitude, so **every mark is one hue and length carries the value**.
Ink colours are a fixed semantic palette; six domain-locked hues cannot clear
colourblind-separation gates (Sapphire vs Amethyst measures ΔE 4.1 under deuteranopia,
Steel is grey by definition), so an ink chip always carries a 3-letter code and the
name in text. Every chart has a table twin, values sit at bar tips, and the copy
spread uses one hue at stepped opacity.

**A chart that does not cover the whole field says so with arithmetic.** The archetype
chart leaves out brews — on a real field 15 archetypes at 74% against 67 brews at 26%.
"67 brews are left out" gave the count and hid the scale, so nothing let the reader
discover the bars stopped at 74%.

**A caveat nobody reads is not a caveat.** Long-form notes live behind a disclosure,
not in the subtitle, which is how they reached **331 words above one chart and 637
across the overview**. Nothing is deleted to shorten a subtitle: the tests cap each at
120 words *and* check every note is still present, per chart. Print forces the
disclosures open, because paper cannot be clicked.

`@media print` once hid the toolbar and stopped there, so printing produced empty
rectangles — bars are divs with backgrounds and browsers drop those. The marks force
`print-color-adjust`, cards avoid page breaks, headers repeat, the palette is forced
light. The block must sit last in the stylesheet: a media query carries no extra
specificity, so ordinary rules after it win.

## 12. Being a good guest

Every number measured, not guessed.

| Behaviour | Why |
|---|---|
| Browser-shaped User-Agent | A plain browser string returns 200; the same string with `lorcana-meta/0.1` appended returns 403. |
| No cookies kept | With a session, request 2 onwards returned 403 at any delay — their own `PHPSESSID` makes rate limiting per-session. Stateless: 6/6 succeeded. |
| One request at a time, 3s default | 6 of 20 requests hit a 429 at 2s. |
| Delay ×1.25 on a 429, ×0.9 after 10 clean, remembered | At ×1.5 one 429 hitting a page twice took the delay 8.6s → 19.3s and the rest of the run crawled. |
| A refused deck is skipped, not fatal | One page returning 429 three times killed a 369-deck run at deck 100. One decklist moves a percentage by 0.3%. Eight refusals in a row still stops it — by then it is the site. |
| Best-placed first | A large window is realistically built across sittings; whatever a run manages should be the part that matters. |
| Deck pages cached forever | A published decklist never changes. |
| `--top` maps onto their filter | A top-8 report fetches 8 listing pages instead of 41. |
| One build at a time (lock file) | See below. |

**A 429 is not a 403.** A rate limit means slow down. A 403 from this site means the
*client* is refused: since 2026-08-28 their WAF blocks by TLS fingerprint, so every
Python client gets 403 on every path while a browser on the same connection is fine.
Never answer a 429 by switching transport.

**curl_cffi is the only transport**, because it presents a real browser TLS
fingerprint. cloudscraper does not help — it solves the older JavaScript challenge and
still speaks Python's TLS. It was briefly a fallback with escalation on a persistent
403, which worked and was the wrong shape: every run began by earning two 403s and a
minute of backoff to manage a choice with one right answer.

The grounds, recorded because they are what makes this legitimate rather than a
technique to reuse:

1. inkdecks gave written permission for automated access, personal use.
2. They said they cannot practically allow-list an address.
3. They approved a bypass tool if one proved necessary.
4. The maintainer made the call knowingly, and it was theirs to make.

Remove any one and this is circumventing a security control — one the terms in §1
explicitly reserve the right to use. **Do not carry the pattern into another project**,
and do not widen it here. It changes the handshake, not the crawl.

The session is **structurally read-only**: `ReadOnlySession` exposes `get` and raises
on `post`, `put`, `patch`, `delete`, `request`. Bytes read are counted and logged.
"It only reads" should not be a promise you verify by reading code.

**Concurrency:** "one request at a time" only held inside one process. An interleaved
log revealed two builds fetching simultaneously, each waiting its own 20 seconds — and
`pkill` from Git Bash does not kill Windows processes, so it reported success while
eight builds kept running. A lock file refuses a second build, with a liveness check so
a lock left by a killed process is taken over at once.

Measured throughput, single process: **~4–9 deck pages per minute**. Trust a real run's
log over any number written here.

## 13. Windows is a first-class target

- `PYTHONPATH=src python -m lorcana_meta` is POSIX syntax; PowerShell reads it as a
  command name. Fixed by a console script — one command everywhere.
- Card names are not ASCII. On a legacy code page `print` raises `UnicodeEncodeError`
  and logging degrades to `アリ...`, exactly in the line reporting unmatched names.
  Hence `console.configure_output()`.
- Native stderr becomes a `NativeCommandError`, so a pip notice aborts a script that
  succeeded. Check `$LASTEXITCODE`, not `$?`.
- `pip install --upgrade pip` in a fresh venv left a broken pip. The venv ships one.
- The CLI logs to stdout, so a normal build is not a red error block.
- A moved `.venv` still imports from its original path (`__editable__*.pth` holds an
  absolute path). Delete and re-create it.
- CI runs the suites on Ubuntu **and** Windows, plus one job with
  `PYTHONIOENCODING=cp1250`.

## 14. Tests, including the ones that lied

`tests/test_render.mjs` covers the presentation layer — 1900 lines that were previously
verified by opening the page and looking. Every page bug in this project was found that
way: an empty curve card on a brew, "A one-off lists" for two decks, bars stopping at
74% in silence, and a missing movement block throwing during render and leaving a blank
page. A blank page is the worst failure here, because it carries no clue at all.

Plain node, no npm. The one production change was `if (typeof document !== "undefined")
boot();` — a test that cuts a call out of the file with a regex is testing something
else. It mutates copies of a built report in memory to reach states a sample field may
not contain; a test that quietly skips is not a test.

Four checks passed against deliberately broken code before being tightened, and all
four failed the same way — asserting that a word appears rather than that the thing
works:

- `html.includes("Movement")` passed with the column deleted, because the legend below
  also says "Movement". Assert the `<th>`.
- A Movement column full of empty cells passed a header check. Assert a data row.
- The inspector check called the lookup directly and passed with the inspector
  rendering none of what it returned. Hence `inspectCard` split from `showCard`.
- A phrase asserted page-wide passed when the ink chart lost its note, because the
  pair chart carried the same sentence. Assert per chart.

And two in `test_report_shape.py` approved fields by coincidence:

- `withDefaults()` *writes* defaults, so it mentions every field it fills — which made
  `undated_decks` look read when nothing read it. A reader-scan that counts writers is
  false assurance. Its body is excluded.
- `totals.variants` has no reader in the page, but `pair.variants` does, so the name
  matched. Matching is by access path now, and exemptions are keyed by full path.
  A `DATA_KEYED` flag also stayed set one level too deep, leaving **every field of a
  card payload unchecked**. Path coverage went 148 → 190.

Where a parent is a list index or a computed key the chain cannot be matched without
parsing the JavaScript, so those fall back to a property access on the name. The
convention that makes path matching work: name a local after its field.

Conditional assertions must force their condition. A caveat check asserted notes
against whatever the last build produced, passed on a real report where brews and
vacuous cuts exist, and broke CI on the sample field where they do not.

`check_report.py` reconciles the arithmetic a reader might redo: every deck in exactly
one archetype of its pair, shares summing to 100%, each ink's count equal to the pairs
it appears in, every threat's contributors accounting for every deck running the card,
and every rate inside its own interval. Tolerances scale with row count — each share
is rounded to a tenth, so 72 archetypes can drift 3.6 points with nothing wrong, and a
flat ±1 point reported a correct 475-deck report as broken three times over.

`built_by` records version, short commit and whether the tree was dirty. `dirty` is the
point: a report built from uncommitted changes cannot be reproduced from the commit it
names, and a stamp that hides that looks trustworthy.

## 15. The traps that cost the most

**Pagination, silently.** Pager links arrive HTML-escaped, so the character before
`page=` is `;`:

```html
<a href="/lorcana-decks/core?deck_type=tournament&amp;page=2">
```

`[?&]page=(\d+)` matched nothing, `max_page()` returned 1, and a window the site
reports as **369 decks** produced a report of **20** — with no error and entirely
plausible output. Two failures compounded it: the test asserted `max_page(...) >= 1`,
which passes when the function finds nothing; and the fixture was built with the same
broken regex, so it contained no pager links and could never have caught it. **A
fixture derived from the code under test is not a test.** `total_decks()` now reads the
count the site prints itself and warns below 90%.

**Sample data that could not exercise the code.** The synthetic field first filled ~20
of 60 slots randomly, so two lists of one archetype scored ~0.5 similarity and
clustering "failed" — 59 archetypes from 60 decks. The algorithm was right, the fixture
was not. Later, placings were drawn with `rng.randint`, so three decks shared 1st place
in one event; every result cut computed against that was meaningless and the tests would
have validated it. Placings are dealt without replacement now.

**Shell heredocs eat escapes.** Writing a regex through one turned `\b` into a literal
backspace, so the pattern was `\.totals\x08` and the test passed while checking
nothing. The same happened to Windows paths (`\b` → backspace, `\a` → bell) and to a
backtick, which the shell executed as a command and substituted with nothing. Use the
editing tools for anything containing a backslash or a backtick.

**A flag that looked like it did something.** `--format` was overridden by
`getattr(source, "fmt", ...)` for any source naming its own format — which the default
source does. It defaults to `None` now, so the CLI can tell "said nothing" from "asked
for this", and warns when ignored. That default immediately produced a second bug: a
`None` reaching `LocalSource` intact became the literal string `"None"` as a format
name on any deck file without a `format` key.

**An undated deck crashed the whole build**, in `_examples`, sorting `None` against a
string. Neither real source omits the date, so nothing had hit it — but the paste
importer can, and a `TypeError` takes the report with it.

## 16. Deliberately not done

- **No matchup table.** Archetype versus archetype needs roughly twenty-four times the
  data that exists. On the largest sample available — a whole set, all time, 13,072
  matches — the 884 matchup cells had a median of **3 matches** and a median published
  interval of **84 points**. 703 distinct matchups at 400 matches each would need
  281,200. Their archetype labels also cannot be joined to our clusters (§3), and we
  hold no pairing data of our own at any grain.
- **No card prices.** Cardmarket's terms prohibit automated collection and their
  official API needs registered credentials; scraping it would be exactly the widening
  §12 forbids. lorcana-api.com carries no prices. A deck price is also not a sum of
  trend prices — multiple printings, languages and conditions per card.
- **No importing inkdecks' win rates.** It would put a second win rate, at a coarser
  grain, from a different source, beside ours — two definitions of one name. Its
  diagnostic value is already banked in §8.
- **No separating deck from pilot.** An archetype can be over-represented because
  strong players chose it, and nothing here can tell the difference. The About page
  says so.
- **No weighting by event size.** `tournament_players` exists, but a multiplier like "a
  win at 300 players is worth five at 12" would be invented. Event size is shown; the
  judgement is the reader's.
- **No month-over-month comparison.** Movement is one window split in two (§5).
- **No npm, no test framework.** A dependency that must be installed before a test runs
  is a dependency that stops the test being run.
