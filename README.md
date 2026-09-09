# Lorcana Meta Report

A private tournament-meta report for Disney Lorcana. Pull decklists for a date window,
group them by what is actually in them, and get one HTML file that says what the field
is playing, what is winning, and what to prepare for.

Built for one player getting ready for one tournament. Not a service, not published
anywhere.

```bash
lorcana-meta build --last 30 --top 32     # -> site/data/meta.json + report.html
```

---

## What it tells you

| View | What it answers |
|---|---|
| **The field** | Which archetypes and ink pairs are being played, and how much of the field each is. |
| **What is winning** | How often each archetype's lists reach the top finishes — the one chart ranked on results rather than popularity. |
| **What you'll face** | Every card by expected copies, with the archetypes that bring it and whether the field is picking it up. |
| **Movement** | A column beside every share: what gained or lost ground between the two halves of the window. |
| **Archetype page** | Card inclusion with copy spreads, the cost curve, the cards that identify the deck, and its best finishes. |
| **About** | How every number was made, and everything the report had to drop. |

Four things it does differently, each because the obvious version was wrong. The
reasoning is in [`docs/DECISIONS.md`](docs/DECISIONS.md).

**Archetypes come from card overlap, not deck names.** One real archetype arrived as
*Blurple*, *Brewing a Storm*, *Stormlight Archive*, *YP* and *Yeetple* — seven lists,
six names, one deck. Grouping by ink pair is no better: 56 Amber/Amethyst decks turned
out to be seven different archetypes. Lists are clustered on weighted card overlap and
named after the cards that distinguish them; submitted names are shown, never used.

**Copy counts are a mode and a spread, not a mean.** A card averaging 2.40 copies had
28 of 43 lists on exactly 2. You get the number lists actually run, plus the full
spread, plus the mean for reference.

**What is played and what wins are separate charts.** On a real field the most played
archetype held 19.4% of the field and 11.1% of the top-8 finishes. The results chart
ranks on conversion — lists reaching the cut over lists the cut could place — with a
95% interval on every rate, because 40% from 25 lists and 37.5% from 8 lists are not
the same claim. When the intervals overlap, the chart says its order is not a ranking.

**Anything dropped is counted and shown.** Unmatched card names, truncated lists,
skipped decks, thin ink pairs, decks a result cut cannot place. A quietly smaller field
is worse than a visible gap.

---

## Getting started

```bash
python -m venv .venv
.venv/Scripts/activate          # Windows;  source .venv/bin/activate  elsewhere
pip install -e .
```

The install is what puts `lorcana-meta` on PATH. There is no `PYTHONPATH=` prefix to
remember — that is POSIX syntax and PowerShell reads it as a command name.

### Try it without touching anyone's server

```bash
python tools/generate_sample_decks.py
lorcana-meta build --source local --last 40
```

Open `report.html`. No server, no hosting, nothing leaves your machine. The sample
field uses real card names but invented decks, players and events, and the report says
so on its own front page.

### Build from inkdecks

Their terms require written permission for automated access, and the flag is you
stating you have it — see [Data sources](#data-sources).

```bash
$env:INKDECKS_CONSENT = "1"                                              # this window
[Environment]::SetEnvironmentVariable("INKDECKS_CONSENT", "1", "User")   # and future ones

lorcana-meta build --last 14 --top 32
```

`inkdecks` is the default source. Set the variable at user level too if you plan to run
this from a scheduled task, which inherits your user environment but not the shell you
typed in.

### How long the first build takes

Their rate limit, not politeness for its own sake — measured at roughly **4–9 deck
pages a minute**.

| Window | Decks | First build |
|---|---|---|
| 14 days, top 8 | ~80 | ~20 min |
| 14 days, top 32 | ~370 | ~1.5 h |
| 30 days, top 32 | ~800 | ~3.5 h |

**Every build after that is seconds.** Decklists never change once published, so they
are cached forever and a rebuild fetches only what is new. A long first build does not
have to happen in one sitting: decks are fetched best-placed first, so Ctrl+C and the
same command tomorrow resumes where it stopped, and a partial field says so.

### Choosing a window

| You want | Try |
|---|---|
| The current meta, enough decks to trust | `--last 30 --top 32` |
| What is winning, not just what is played | `--last 45 --top 8` |
| A quick look, few requests | `--last 7 --top 8` |
| Only serious events | add `--min-players 32` |
| A different format | add `--inkdecks-category infinity` (or `poorcana`, `all`) |

Under about 60 decks the percentages move a lot, and the report says so rather than
letting you read noise as a trend.

### On a schedule

Weekly is plenty — the meta does not move daily and it is kinder to the source. Use the
absolute path to the venv rather than trusting `PATH` inside the scheduler, and set
`INKDECKS_CONSENT` at user level so the task inherits it.

```powershell
$cmd = "cd C:\path\to\repo; .\.venv\Scripts\lorcana-meta.exe build --last 30 --top 32"
$action  = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -Command `"$cmd`""
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday -At 07:00
Register-ScheduledTask -TaskName LorcanaMetaReport -Action $action -Trigger $trigger `
  -Settings (New-ScheduledTaskSettingsSet -StartWhenAvailable -RunOnlyIfNetworkAvailable)
```

```cron
0 7 * * 1  cd /path/to/repo && .venv/bin/lorcana-meta build --last 30 --top 32
```

---

## Command line

```
lorcana-meta build [options]
```

| Option | Default | What it does |
|---|---|---|
| `--source {inkdecks,local}` | `inkdecks` | Where decklists come from. |
| `--last N` | `30` | Days back from today. |
| `--start` / `--end` | – | Explicit window, `YYYY-MM-DD`. Overrides `--last`. |
| `--top N` | `32` | Keep finishes this high or better. `0` keeps everything. |
| `--min-players N` | – | Ignore smaller events. For inkdecks it filters on the listing row, so those deck pages are never requested. Decks whose event size is unknown are kept. |
| `--min-pair-decks N` | `3` | Drop ink pairs thinner than this as noise. The count is still reported. |
| `--cluster-threshold F` | `0.60` | Card overlap that counts as the same archetype. Lower merges more, higher splits more. |
| `--out` | `site/data/meta.json` | Where the data goes. |
| `--no-bundle` | – | Skip writing `report.html`. |
| `--bundle-out` | `report.html` | Where the single file goes. |
| `--refresh-cards` | – | Re-download the card database instead of using the 24h cache. |
| `--indent N` | – | Pretty-print the JSON. |

inkdecks only:

| Option | Default | What it does |
|---|---|---|
| `--inkdecks-category` | `core` | Which tab to read: `core`, `infinity`, `poorcana`, `all`. This selects the format for this source, not `--format`. |
| `--inkdecks-consent` | – | Confirm you have their written permission. Required. |
| `--inkdecks-delay F` | `3.0` | Seconds between requests. Grows on a 429, never shrinks within a run. |
| `--inkdecks-max-decks N` | `1500` | Stop after this many decks, best-placed first. |

local only: `--local-dir` (default `data/decks`) and `--format` (default
`Core Constructed`, for decks that carry no format of their own).

```bash
lorcana-meta build --last 30 --top 32 --min-players 32
lorcana-meta build --start 2026-08-01 --end 2026-08-27
lorcana-meta build --last 60 --top 1 --cluster-threshold 0.75
```

Also here: `tools/bundle_report.py` (re-bundle without refetching),
`tools/generate_sample_decks.py`, `tools/import_pasted_decks.py`, and
`tests/check_report.py`. To preview the multi-file version, serve `site/` — a `file://`
open will not work, because the page fetches `data/meta.json`:

```bash
cd site && python -m http.server 8000
```

---

## Where the report goes

`report.html` carries the CSS, the JavaScript and the data inline. It opens from your
filesystem, works offline and needs no account or server. **If the report is for you
only, this is the right answer.** Card images still come from Ravensburger's CDN, so
the inspector needs a connection; every number works without one.

> [!WARNING]
> **A GitHub Pages site is public even when the repository is private.** From the
> [GitHub documentation](https://docs.github.com/en/enterprise-cloud@latest/pages/getting-started-with-github-pages/changing-the-visibility-of-your-github-pages-site):
> *"GitHub Pages sites are publicly available on the internet by default, even if the
> repository for the site is private or internal"*, and *"to publish a GitHub Pages
> site privately, your organization must use GitHub Enterprise Cloud."* A personal
> account cannot make a Pages site private at all — private repo, world-readable page,
> guessable URL.

There is no publish workflow in this repository, on purpose. One existed and was
deleted; it is in the git history if a public page from redistributable decklists is
ever actually wanted.

---

## Data sources

**inkdecks.com** (`--source inkdecks`, default) has by far the widest coverage of
Lorcana tournaments. Their [terms of use](https://inkdecks.com/pages/terms) prohibit
automated access:

> You may not use automated systems (e.g., bots, scrapers, spiders) to access,
> extract, copy, or collect data from the Website without prior written consent.

So the source refuses to run until you confirm you have that consent. The permission
this is written around is **personal use with no commercialised public site**, so the
source sets `publishable = False`, which travels into the report and makes
`tests/check_report.py` fail — anything that publishes has to be told to ignore a
failing check first. If your own permission differs, changing that is a deliberate
edit, not a default to drift into.

The crawl is one request at a time with an adaptive delay, deck pages cached forever,
and a session that is read-only by construction. Details and measurements:
[`docs/DECISIONS.md`](docs/DECISIONS.md).

**Card data:** [lorcana-api.com](https://lorcana-api.com/) — free, no key. One bulk
endpoint cached for 24 hours, supplying card text, cost, inks, type and images.

**Your own files** (`--source local`) read `data/decks/*.{json,txt}` — good for local
events no platform covers, and for lists copied by hand. Format:
[`data/decks/README.md`](data/decks/README.md). `tools/import_pasted_decks.py` converts
a file of pasted lists; reading a page and copying a list yourself is not automated
access, and the tool fetches nothing.

---

## Reading the numbers honestly

Every one of these is stated on the report itself, next to the number it applies to.

- **It is a sample, not a census** — only events on the source platform, and only
  standings whose player submitted a list.
- **The win rate is conditioned on the cut.** Every list in the report finished inside
  `--top N`, so these are win rates among decks that already placed: uniformly high and
  compressed. Read them against each other, never as how often a deck wins.
- **Result cuts are conditional too** — which of the decks already doing well went
  furthest, not a win rate against a whole tournament.
- **A rate with few lists behind it is wide.** Every conversion rate ships its 95%
  interval and its denominator; archetypes with fewer than 8 judged lists are not
  charted at all.
- **Movement is one window cut in half by date**, never a comparison with a previous
  report. A fortnight has weather.
- **Nothing separates the deck from the pilot.** An archetype can take more than its
  share of top finishes because strong players chose it.

---

## Tests

No dependencies, no network, no permissions:

```bash
python tests/test_pipeline.py        # parsing, inks, aggregation, movement, result cuts
python tests/test_cluster.py         # archetype detection
python tests/test_local_source.py    # decks off disk, paste importer
python tests/test_inkdecks.py        # parsers, consent, throttle, lock
python tests/test_report_shape.py    # report and page agree on their shape
python tests/test_bundle.py          # the single file stays self-contained
python tests/check_report.py         # a built report is sane (needs a build first)
node   tests/test_render.mjs         # every page renders (needs a build first)
```

CI runs all of them on Ubuntu **and** Windows, plus an end-to-end build, `ruff check`,
and one job with a legacy Windows code page. Four exist because of failures that are
silent by nature:

- `test_report_shape.py` — a field the build stops emitting renders as a blank cell,
  not an error; and nothing may ship in the JSON that nothing reads, since the whole
  file goes to the browser.
- `test_render.mjs` — the page throwing during render leaves a blank screen with no
  clue on it.
- `test_bundle.py` — a bundle that stops being self-contained still opens, and just
  shows "could not load data/meta.json".
- `check_report.py` — it reconciles the arithmetic a reader might redo, and it is the
  gate that keeps privately-licensed data from being published.

`tests/test_inkdecks.py --live` additionally hits the real site and needs consent; it
never runs in CI.

---

## Layout

| Path | What it is |
|---|---|
| `report.html` | The report. Open this. |
| `site/data/meta.json` | The data behind it. Records the version, commit and dirty flag of the build that made it. |
| `site/` | The page: one HTML file, one stylesheet, one script, no build step. |
| `src/lorcana_meta/` | `sources/` fetch decklists, `cards.py` resolves names, `cluster.py` finds archetypes, `analyze.py` does the maths, `bundle.py` writes the single file, `cli.py` wires it together. |
| `.cache/` | Cached deck pages, the learned request rate, the card database. Safe to delete. |
| `docs/DECISIONS.md` | Why it is built this way, and the traps already hit. |
| `docs/MAINTAINING.md` | Commands, hard rules, platform gotchas. |

A new source is one file in `src/lorcana_meta/sources/`: implement
`fetch(start, end) -> list[Deck]`, expose `name` / `attribution` / `attribution_url` /
`publishable`, register it. Nothing downstream changes.

---

## Licence

Personal project, no licence granted. Disney Lorcana is a trademark of Disney and
Ravensburger; this is an unofficial fan tool, not published, endorsed or approved by
either. Decklist data belongs to its sources under their own terms.
