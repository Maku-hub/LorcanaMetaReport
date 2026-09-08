# Working on this project

A Lorcana tournament-meta report: pull tournament decklists for a date window,
group decks by what is in them, render a private HTML report. See `README.md` for
what it does and `docs/DECISIONS.md` for **why** it is built this way — that file
records decisions and the traps already fallen into, and reading it will save you
from repeating them.

## Commands

Everything runs through the CLI. There are deliberately no wrapper scripts — one way
to run it, nothing to keep in step.

```powershell
python -m pip install -e .                            # once; puts lorcana-meta on PATH
lorcana-meta build --last 14 --top 32                 # -> site/data/meta.json + report.html
```

A build writes the single-file report itself (`--no-bundle` to skip). It used to be a
second command, and that let `report.html` go quietly stale behind the data - it
renders perfectly and shows the previous window. `tools/bundle_report.py` is still
there for re-bundling without refetching.

There is no `PYTHONPATH=` prefix and no extras to remember — that is POSIX syntax, it
fails on PowerShell, and the `[inkdecks]` extra was folded into the core dependencies
precisely because `pip install -e .` was producing installs that could not read the
default source.

Run the tests before calling anything done. All seven, plus the report check and the
linter — CI runs the same lines:

```powershell
.venv\Scripts\python.exe tests\test_pipeline.py       # parsing, inks, aggregation maths, movement
.venv\Scripts\python.exe tests\test_cluster.py        # archetype detection
.venv\Scripts\python.exe tests\test_local_source.py   # decks off disk, paste importer
.venv\Scripts\python.exe tests\test_inkdecks.py       # inkdecks parsers, consent, throttle, lock
.venv\Scripts\python.exe tests\test_report_shape.py   # report and page agree on their shape
.venv\Scripts\python.exe tests\test_bundle.py         # the single-file report stays self-contained
.venv\Scripts\python.exe tests\check_report.py        # the built report is publishable-sane
node tests\test_render.mjs                            # every page renders; needs a build first
.venv\Scripts\python.exe -m ruff check .              # pinned to 0.16.6 in CI
```

`tests/test_render.mjs` is the only test needing node, and it needs no npm packages —
it evaluates `site/assets/app.js` and calls the renderers directly. That file had no
test at all until every page bug in it had first been found by hand.

No test dependencies, no network, no permissions needed. `tests/test_inkdecks.py
--live` additionally hits the real site and needs `INKDECKS_CONSENT=1`; it never runs
in CI.

## Hard rules

**Never publish a report built from inkdecks data.** Permission for that source is
personal use only, no public site. The source sets `publishable = False`, which
travels into the report and makes `tests/check_report.py` fail. Do not weaken that
chain, and do not add a workflow that publishes anything — the one that existed was
deleted on purpose (`docs/DECISIONS.md` §11), so there is currently no route out of
this repo at all. A GitHub Pages site is **public even from a private repo** — access
control is Enterprise Cloud only. The private route is the `report.html` every build
writes; `lorcana_meta/bundle.py` holds the logic.

**Never remove the inkdecks consent gate.** Their terms prohibit automated access
without written consent. The flag is the user asserting they have it; nothing in the
code may assert it for them.

**Archetypes come from card overlap, never deck names.** The same list is submitted
under half a dozen names — on real data, 7 decks arrived as "Blurple", "Brewing a
Storm", "Stormlight Archive", "YP", "Yeetple" and more. Names are collected for
display only. See `src/lorcana_meta/cluster.py`.

**Copy counts report the mode and the full spread, not just the mean.** A mean of
2.40 hides that 28 of 43 lists run exactly 2.

**The page gets tested, not clicked.** `site/assets/app.js` is 1300 lines and the
report's whole readable surface. `tests/test_render.mjs` renders every page and holds
the invariants that were each broken by hand at least once: no `undefined` anywhere, a
brew with no card table or curve, the archetype chart naming how much of the field it
covers, all three charts carrying Movement together, a dash meaning "cannot tell"
rather than zero, and an older report degrading instead of blanking the page. When you
add to the page, add the invariant there. Every claim in it was verified by breaking
the code on purpose; a check that passes on a broken page is worse than none.

**Nothing ships in the report that nothing reads, and nothing the page reads may stop
shipping.** The whole `meta.json` goes to the browser and into `report.html`; working
fields nothing read were 37% of a real build. `_lean()` in `cli.py` strips them last,
once every derived number is final, and `tests/test_report_shape.py` holds both lines
— add a field, give it a reader or list it in `READ_ELSEWHERE` with its consumer,
keyed by full path. Readers are matched by access path, so name a local after its
field (`const anomalies = meta.anomalies`); aliasing it to a shorter name hides the
read from the check.
Both failures are silent: a dropped field renders as a blank cell, a dead field
announces nothing ever.

**Statistics a single deck cannot support are not shown for a single deck.** A brew
(1–2 lists) keeps its label, size, share, record, tells, player names and finishes,
and carries no card table or cost curve — for one deck every card reads 100%
inclusion. The site must handle the empty lists; the About page carries the count.

**A chart that does not cover the whole field says so with the arithmetic, not just a
count.** The archetype chart leaves out one-off brews — a quarter of a real field, 15
archetypes at 74% against 67 brews at 26%. "67 brews are left out" gave the count and
not the scale, so the three overview charts looked like they disagreed with no way to
reconcile them. Movement lives in a column beside the share it belongs to — on all
three overview charts, archetype, ink pair and single ink — never in a second table of
the same decks with a different membership.
`tests/check_report.py` holds the reconciliation: every deck in exactly one archetype
of its pair, archetype shares of a pair summing to 100%, each ink's count equal to the
pairs it appears in, and every threat's contributors accounting for every deck that
runs the card.

**A caveat nobody reads is not a caveat.** Long-form notes go in `barChart`'s `notes`
option, behind a disclosure - not appended to the subtitle, which is how they reached
**331 words above one chart and 637 across the overview**. Nothing is deleted to
shorten a subtitle: `tests/test_render.mjs` caps every subtitle at 120 words *and*
checks each note is still on the page, per chart rather than page-wide (an ink chart
once lost its movement note while a sibling still carried the same sentence, and the
check passed). Print forces the disclosures open.

**A sorted chart claims a ranking, so it has to say when there is not one.**
`separationNote()` compares every charted rate's interval with the leader's lower
bound: on a real 837-deck field all 13 others overlapped it and none was measurably
worse, so the chart disowns its order in words rather than implying a first place. The
comparison is `other.high >= leader.low` - the wrong end passes every test built on
identical or disjoint intervals, so the test for it uses a partial overlap.

**A rate is ranked on, and it ships with its interval and its denominator.** The
results chart ranks archetypes by conversion - lists reaching the cut over lists the
cut could place - because a share of the winners puts the biggest archetype first for
being biggest, and because conversion correlated better with an outside win rate
(+0.79 against +0.56). Every rate carries `judged`, `conversion_low` and
`conversion_high` (Wilson 95%), and `MIN_RATE_DECKS` keeps the thinnest off the chart:
a real archetype with 3 lists converted all 3. A report whose rates lack `judged`
cannot be ranked at all - `withDefaults` marks it `rankable: false` and the chart
withholds itself, because with the denominator missing the floor reads as zero and
that three-list archetype becomes "best converter". Found exactly that way.

**Share of the field is not a result, and the two get separate charts.** The most
played archetype in a real field took 19.4% of the field and 11.1% of the top 8s.
Result cuts live in `RESULT_CUTS`; the reader picks one because an absolute cut
over-credits small events and a percentage cut over-credits large ones, and each cut
reports `vacuous_events` — the events it excludes nothing from — so the bias is
measured on the page rather than described in a footnote. A cut under
`MIN_CUT_DECKS` is withheld with its arithmetic.

**A placing is a range, and inkdecks publishes knockout brackets.** On a real
842-deck field the only exact labels were 1st, 2nd and 3rd; every other deck carried
`Top4`/`Top8`/`Top16`/`Top32`. Those are **disjoint** — the site shows the tightest
descriptor it has, so a `Top8` deck went out in the quarter-finals and finished 5th
to 8th. `standing` is the worst end, `standing_best` the best (`K // 2 + 1`).

Both ends decide a cut: inside if the worst end clears it, outside if the best end
does not, `None` only when the bracket straddles the line. Reading the worst end
alone meant **no deck could ever be excluded** — 514 of 842 unjudgeable for a top-8
cut, and every event reported as one the cut excluded nothing from. Decks a cut cannot
judge are counted, shown, and left out of `conversion`'s denominator rather than
charged as failures: which archetypes sit on a bracket boundary is an artefact of the
labelling. Conversion is always labelled conditional on having made the fetched
`--top N` cut.

**The win rate in this report is conditioned on the cut, and the label has to say
so.** `record.win_rate` is computed over decks that all finished inside `--top N`, so
every figure is high and the spread is compressed. Checked against inkdecks' own
winrate matrix over the same window: ours ran **11 points high in every ink pair**,
turning 34 points of real spread into 8 - Sapphire/Steel wins 36% of its games and the
report said 55.6%. `winRateLabel()` names the sample (`Win rate, top-32 lists`) and
`winRateNote()` travels with it. Never label it "match win rate" again.

**Card figures are attributed to archetypes, never to ink pairs.** The threat board
said "played by Amber/Amethyst 63.2%" where one archetype ran the card in every list
and another in none — the average of "always" and "never", which is the mush
clustering exists to avoid. Brews are pooled per pair (each is one deck, so every card
in it reads 100%), and the pool is what keeps every deck running a card attributed to
exactly one group. `expected_copies` and `field_presence` come straight off the field,
not summed over groups. `tests/check_report.py` reconciles all of it.

**Movement is one window cut in half by date — never a comparison with a previous
run.** Clustering happens once over the whole window and the halves only count its
members; clustering per half would mean matching archetypes across halves, the
problem card overlap exists to avoid. Shares are rounded before subtracting so the
delta equals the two numbers printed beside it. Under 15 decks in a half, or a window
under 4 days, and no movement is shown at all — with the reason in words, because
silence reads as "nothing moved". See `docs/DECISIONS.md` §10.

**A 429 is not a 403, and they get opposite answers.** A rate limit means slow down —
the delay widens, eases after a clean stretch, and is remembered. A 403 from this
site means the *client* is refused: since 2026-08-28 their Cloudflare blocks by TLS
fingerprint, so every Python client gets 403 on every path while a browser on the
same connection is fine. `auto` escalates to curl_cffi for that case only, and
remembers it. Never answer a 429 by switching transport.

**curl_cffi is impersonation, and it rests on permission, not on convenience.**
inkdecks gave written consent for automated access, said they cannot practically
allow-list an address, and approved a bypass tool if needed. Do not carry this
pattern into another project, and do not widen it here. See `docs/DECISIONS.md`.

**The inkdecks session is read-only by construction.** `ReadOnlySession` allows
`get` and raises on anything that could write. Do not unwrap it.

## Windows specifics that have already caused bugs

- Check `$LASTEXITCODE`, not `$?`, after a native command. In Windows PowerShell
  anything on stderr becomes a `NativeCommandError`, so a pip notice aborts a script
  that succeeded.
- Never `pip install --upgrade pip` inside a fresh venv — it leaves a broken pip.
- The CLI logs to **stdout** on purpose, so a normal build does not render as a red
  error block in PowerShell. Failure is signalled by the exit code.
- Console encoding: `lorcana_meta.console.configure_output()` must be called before
  anything prints a card name, or a legacy code page raises `UnicodeEncodeError`.
- `pkill` from Git Bash does **not** kill Windows processes. It silently reports
  success while eight builds keep running. Use
  `Get-CimInstance Win32_Process | Where-Object CommandLine -like ... | Stop-Process`.
- A moved `.venv` still imports from its original path (`__editable__*.pth` holds an
  absolute path). After moving the project, delete `.venv` and re-create it:
  `python -m venv .venv` then `pip install -e .`.

## Conventions

**Scraped HTML is parsed by content, never by column position.** A positional parser
reacts to a layout change by reading the price column as a placing: wrong numbers, no
error. Fixtures in `tests/fixtures/` are trimmed excerpts — enough markup to detect a
change, not a copy of someone's pages.

**Charts use one hue; length carries the value.** Ink colours are a fixed semantic
palette and always ship with a text label or 3-letter code, because six domain-locked
hues cannot clear colourblind-separation gates. Every chart has a table twin.

**Anything dropped is counted and shown.** Unmatched card names, truncated lists,
skipped decks, thin ink pairs — the report surfaces each count on its About page. A
quietly smaller field is worse than a visible gap.

**A new data source is one file** in `src/lorcana_meta/sources/`: implement
`fetch(start, end) -> list[Deck]`, expose `name` / `attribution` / `attribution_url` /
`publishable`, register it in `sources/__init__.py`. Nothing downstream changes.

## Git

The user runs all git operations themselves. Do not commit, push, or create
branches unless explicitly asked.
