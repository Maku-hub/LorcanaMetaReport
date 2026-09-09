# Maintaining this project

Commands, the rules that must not be broken, and the platform traps that already cost
time. The *why* behind each rule is in [`DECISIONS.md`](DECISIONS.md).

## Commands

```powershell
python -m pip install -e .                 # once; puts lorcana-meta on PATH
lorcana-meta build --last 14 --top 32      # -> site/data/meta.json + report.html
```

A build writes the single file itself; `--no-bundle` skips it.
`tools/bundle_report.py` re-bundles without refetching.

Run everything before calling anything done — CI runs the same lines:

```powershell
.venv\Scripts\python.exe tests\test_pipeline.py
.venv\Scripts\python.exe tests\test_cluster.py
.venv\Scripts\python.exe tests\test_local_source.py
.venv\Scripts\python.exe tests\test_inkdecks.py
.venv\Scripts\python.exe tests\test_report_shape.py
.venv\Scripts\python.exe tests\test_bundle.py
.venv\Scripts\python.exe tests\check_report.py
node tests\test_render.mjs
.venv\Scripts\python.exe -m ruff check .
```

No test dependencies and no network. `test_render.mjs` is the only one needing node and
needs no npm packages. `test_inkdecks.py --live` hits the real site and needs
`INKDECKS_CONSENT=1`; it never runs in CI.

## Hard rules

**Never publish a report built from inkdecks data.** Permission is personal use only.
The source sets `publishable = False`, which travels into the report and makes
`check_report.py` fail. Do not weaken that chain, and do not add a workflow that
publishes anything. A Pages site is public even from a private repo. The private route
is the `report.html` every build writes.

**Never remove the inkdecks consent gate.** The flag is the user asserting they have
written permission; nothing in the code may assert it for them.

**curl_cffi rests on permission, not convenience.** Do not carry the pattern into
another project and do not widen it here. The session stays read-only by construction —
`ReadOnlySession` allows `get` and raises on anything that could write.

**A 429 is not a 403.** A rate limit means slow down. A 403 from this site means the
client is refused. Never answer a 429 by switching transport.

**Archetypes come from card overlap, never deck names.** Names are collected for
display only.

**Copy counts report the mode and the full spread, not just the mean.**

**A placing is a range.** inkdecks publishes knockout brackets, so `Top8` is 5th–8th.
`standing` is the worst end, `standing_best` the best, and both decide a cut: `None`
means "cannot tell", never "no". Decks a cut cannot place are counted, shown, and left
out of `conversion`'s denominator.

**The win rate is conditioned on the cut.** It is computed over decks that all made
`--top N`, so it runs high and compressed. `winRateLabel()` names the sample and
`winRateNote()` travels with it. Never label it "match win rate".

**Card figures are attributed to archetypes, never to ink pairs.** Brews are pooled per
pair so every deck running a card belongs to exactly one group.

**Movement is one window cut in half by date**, never a comparison with a previous run.
Clustering happens once over the whole window. Shares are rounded before subtracting so
the delta equals the two numbers printed beside it. Withheld below the floors, with the
reason in words — silence reads as "nothing moved".

**A rate ships with its interval and its denominator.** `MIN_RATE_DECKS` keeps the
thinnest off the chart. A report whose rates lack `judged` is marked
`rankable: false` and the chart withholds itself.

**A sorted chart claims a ranking, so it says when there is not one.**
`separationNote()` compares each interval with the leader's lower bound; the comparison
is `other.high >= leader.low`.

**Anything dropped is counted and shown** — unmatched names, truncated lists, skipped
decks, thin pairs, unjudgeable placings. The About page carries every count.

**Statistics a single deck cannot support are not shown for it.** A brew keeps label,
size, share, record, tells, names and finishes, and carries no card table or curve.

**A chart that does not cover the whole field says so with arithmetic**, not just a
count.

**A caveat nobody reads is not a caveat.** Long-form notes go in `barChart`'s `notes`
option, behind a disclosure — never appended to a subtitle. Nothing is deleted to
shorten one: the tests cap each subtitle at 120 words and check every note is still
present, per chart.

**Nothing ships in the report that nothing reads, and nothing the page reads may stop
shipping.** `_lean()` strips working fields last; `test_report_shape.py` holds both
lines. Give a new field a reader or list it in `READ_ELSEWHERE` by full path. Readers
are matched by access path, so name a local after its field.

**The page gets tested, not clicked.** Add page invariants to `test_render.mjs`, and
verify each by breaking the code on purpose — a check that passes on a broken page is
worse than none. Force the condition an assertion depends on rather than relying on
what the last build happened to produce.

## Platform traps

- Check `$LASTEXITCODE`, not `$?`, after a native command — stderr becomes a
  `NativeCommandError`, so a pip notice aborts a script that succeeded.
- Never `pip install --upgrade pip` inside a fresh venv; it leaves a broken pip.
- `console.configure_output()` must run before anything prints a card name, or a legacy
  code page raises `UnicodeEncodeError`.
- The CLI logs to stdout on purpose. Failure is the exit code.
- `pkill` from Git Bash does not kill Windows processes — it reports success while the
  processes keep running. Use `Get-CimInstance Win32_Process | ... | Stop-Process`.
- A moved `.venv` still imports from its original path. Delete and re-create it.
- Shell heredocs eat escapes: `\b` becomes a backspace, a backtick is executed. Use the
  editing tools for anything containing a backslash or a backtick.

## Conventions

**Scraped HTML is parsed by content, never by column position.** A positional parser
reacts to a layout change by reading the wrong column: wrong numbers, no error.
Fixtures are trimmed excerpts — enough markup to detect a change, not a copy of
someone's pages. Never build a fixture with the code under test.

**Charts use one hue; length carries the value.** Ink colours are a fixed semantic
palette and always ship with a 3-letter code or name. Every chart has a table twin.

**A new source is one file** in `src/lorcana_meta/sources/`: implement
`fetch(start, end) -> list[Deck]`, expose `name` / `attribution` / `attribution_url` /
`publishable`, register it in `sources/__init__.py`.
