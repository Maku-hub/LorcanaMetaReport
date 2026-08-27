# Lorcana Meta Report

A report that answers one question for a player getting ready for a Disney Lorcana
tournament: **what am I actually going to sit across from, and what is in those
decks?**

It pulls tournament standings with their decklists for a date window, groups the
decks by what is in them, and renders a report. No server, no database, no build
step — the pipeline writes one JSON file and the page reads it. Run it privately as a
single local file, or publish it to GitHub Pages.

---

## What it tells you

| View | What it answers |
|---|---|
| **Meta** | Which archetypes and ink pairs the field is made of, and how much of it each one is. |
| **Archetype page** | For one deck: which cards are core (80%+ of lists run them), which are flex, **how many copies most lists run and whether they agree**, the curve, the best finishes, and every name players submitted it under. |
| **What you'll face** | Every card ranked by **expected copies** — inclusion × how popular the deck playing it is. This is the list to build tech against. |
| **Your deck** | Paste your list, see your pair's share of the field and which of the field's biggest threats you also play. Stays in your browser. |

### Archetypes come from card overlap, not deck names

Deck names are useless for grouping. The same list gets submitted as "Yurple",
"A/P Midrange" and "yellow purple good stuff", while two lists sharing a name can be
completely different decks. And within one ink pair there are usually several real
archetypes, so grouping by ink alone averages them into a mush where nothing reads
as core.

So decks are clustered by the **weighted Jaccard index** over their card counts:

```
similarity(a, b) = Σ min(aᵢ, bᵢ) / Σ max(aᵢ, bᵢ)
```

Two identical lists score 1.0; two lists differing by four of sixty cards score about
0.87; two lists sharing nothing score 0.0. Counting copies rather than just names
matters — a list on 4 Grandmother Willow and one on 1 are making different choices.
Anything above `--cluster-threshold` (0.60 by default) is the same deck.

Each archetype is then named after the cards that **distinguish** it from the rest of
its ink pair, preferring the expensive character a player would actually name the
deck after. The names players used are collected and displayed for reference, and
never touch the grouping. Details and reasoning: [`src/lorcana_meta/cluster.py`](src/lorcana_meta/cluster.py).

### Copy counts are a mode, not a mean

Different builds of a deck run different numbers of the same card, so a mean is the
wrong summary for "how many will I face". From 45 real lists of one archetype:

| Card | Inclusion | Mean | Reported | What the lists actually do |
|---|---|---|---|---|
| Grandmother Willow - Ancient Advisor | 100% | 4.00 | **4×** | `4x:45` |
| Hamm - Piggy Bank | 100% | 3.78 | **4×** | `1x:1 2x:1 3x:5 4x:38` |
| Ursula - Whisper of Vanessa | 96% | 2.40 | **2×** | `1x:2 2x:28 3x:7 4x:6` |

A mean of 2.40 invites "so, 2 or 3?" when the field has already answered: 28 of the
43 lists running Ursula run exactly 2. So each card reports the **mode**, the **full
spread** of how many decks run 1/2/3/4, and the mean alongside for reference. The
spread is what tells you whether an archetype agrees with itself — one block means it
does, two blocks at opposite ends mean the mean between them is a number nobody
plays.

The bigger defence is upstream: these figures are computed **within an archetype**,
not across an ink pair. 56 decks sharing Amber/Amethyst turned out to be 7 different
decks, and averaging across them is exactly the mush this avoids.

On the threat board, `expected copies` stays a true expectation over the whole field —
fractional by design, and the right thing to rank by — with the modal count beside it
answering "and when I do meet that deck, how many is it running".

---

## Quick start

### Windows (PowerShell)

```powershell
git clone https://github.com/YOUR-USER/YOUR-REPO.git
cd YOUR-REPO
python -m pip install -e .

# Build from the synthetic sample field and open it as one local file
.\scripts\build.ps1 -Sample -Bundle
```

That writes `report.html`. Double-click it — no server, no hosting, nothing leaves
your machine.

With real data, once you have a [free TopDeck key](https://topdeck.gg/developers):

```powershell
$env:TOPDECK_API_KEY = "your-key"                                        # this session
[Environment]::SetEnvironmentVariable("TOPDECK_API_KEY", "your-key", "User")  # permanently

.\scripts\build.ps1 -Days 30 -Top 32 -Bundle
```

`.\scripts\serve.ps1` previews the multi-file version in a browser instead.

### macOS / Linux

```bash
git clone https://github.com/YOUR-USER/YOUR-REPO.git
cd YOUR-REPO
python -m pip install -e .

python tools/generate_sample_decks.py
lorcana-meta build --source local --last 40
python tools/bundle_report.py          # -> report.html, open it directly
```

There are no shell wrappers for these platforms, because `lorcana-meta` plus `cron`
covers the same ground:

```cron
0 7 * * 1  cd /path/to/repo && .venv/bin/lorcana-meta build --source inkdecks --last 30 --top 32 && .venv/bin/python tools/bundle_report.py
```

Installing the project is what puts `lorcana-meta` on PATH, so the same command
works on every platform. There is no `PYTHONPATH=...` prefix to remember — that is
POSIX shell syntax and PowerShell reads it as a command name.

The sample field uses real card names but invented decks, players and events. It is
built to exercise the hard part: two ink pairs carry two different archetypes each,
and every archetype is submitted under several names. The report flags on its own
front page that the data is not real.

---

## Running it for real (Windows)

The setup this is built for: private, on one machine, refreshed on a schedule, read
by double-clicking a file. No hosting, no account, nothing published.

### Once

```powershell
git clone https://github.com/YOUR-USER/YOUR-REPO.git
cd YOUR-REPO
.\scripts\setup.ps1
```

That makes a `.venv`, installs the project into it, and pre-fetches the card
database so a scheduled run at 6am is not the first thing to discover a proxy
problem. `build.ps1` and `serve.ps1` find `.venv` on their own afterwards — there is
no environment to activate.

If you are using inkdecks, record your permission. The flag is you stating you have
it, so nothing sets it for you:

```powershell
$env:INKDECKS_CONSENT = "1"                                                   # this window
[Environment]::SetEnvironmentVariable("INKDECKS_CONSENT", "1", "User")        # from now on
```

Both, because they do different things. The first affects the PowerShell window you
are in; the second affects every future one, including scheduled runs, which inherit
your user environment — but **not** the window you type it in. Set only the second and
your current session still refuses.

### Whenever you want a fresh report

```powershell
# Top 32 of the last two weeks, Core Constructed
.\scriptsuild.ps1 -Source inkdecks -Days 14 -Top 32 -Bundle
```

`-Category` picks which of the site's tabs to read — `core` (the default),
`infinity`, `poorcana`, or `all`. With `all` the field is mixed and each deck keeps
its own format label, so an Infinity list never gets counted as a Core one.

Then open `report.html`. Make a shortcut to it somewhere convenient — that file is
the application as far as daily use is concerned.

The first build of a fresh window is slow, and the reason is their rate limit rather
than politeness for its own sake. Measured against the live site: the delay settles
near its 20s ceiling and throughput works out to roughly **4 deck pages a minute**.

| Window | Decks | First build |
|---|---|---|
| 14 days, top 8 | ~80 | ~20 min |
| 14 days, top 32 | ~370 | ~1.5 h |
| 30 days, top 32 | ~800 | ~3.5 h |

**Every build after that is seconds.** Decklists never change once published, so they
are cached forever and a rebuild only fetches what is new.

A long first build does not have to happen in one sitting. Decks are fetched
best-placed first and everything fetched is cached, so you can stop it with Ctrl+C
and run the same command again tomorrow — it resumes where it left off, and a report
built from a partial field says so on its own front page rather than passing it off
as the whole meta.

If you want a usable report today, `-Top 8` is the better trade: a fifth of the
requests, and what wins is arguably a sharper signal than what merely gets played.

### On a schedule

```powershell
.\scripts\schedule.ps1 -Source inkdecks -Weekly Monday -At 07:00 -Days 30
```

Registers a Windows scheduled task. It runs as you, only when you are logged on,
never wakes the machine, and picks up a missed run once you are back. Weekly is
usually the right cadence: the meta does not move daily, and it is kinder to the
source.

```powershell
Start-ScheduledTask -TaskName LorcanaMetaReport    # run it now
Get-ScheduledTaskInfo -TaskName LorcanaMetaReport  # last result
.\scripts\schedule.ps1 -Remove                     # undo
```

### Choosing a window

| You want | Try |
|---|---|
| The current meta, enough decks to trust | `-Days 30 -Top 32` |
| What is winning, not just what is played | `-Days 45 -Top 8` |
| A quick look, few requests | `-Days 7 -Top 8` |
| Only serious events | add `-MinPlayers 32` |
| A different format | add `-Category infinity` (or `poorcana`, or `all`) |

Under about 60 decks the percentages move a lot, and the report says so on its own
front page rather than letting you read noise as a trend.

### Where things live

| Path | What it is |
|---|---|
| `report.html` | The report. Open this. |
| `site\data\meta.json` | The data behind it, if you want to script against it. |
| `.cache\inkdecks\` | Cached deck pages and the learned request rate. Safe to delete; it just costs a slow rebuild. |
| `.cache\cards.json` | The card database, refreshed daily. |
| `.venv\` | The Python environment. Delete and re-run `setup.ps1` to reset. |

---

## Where to put the report

### One local file — private, and the simplest thing that works

```bash
lorcana-meta build --last 30 --top 32
python tools/bundle_report.py
```

`report.html` carries the CSS, the JavaScript and the data inline. It opens straight
from your filesystem, works offline, and needs no account or server. **If the report
is for you only, this is the right answer.** Card images still come from
Ravensburger's CDN, so the card inspector needs a connection; every number works
without one.

### GitHub Pages — public, whatever your repo's visibility

> [!WARNING]
> **A GitHub Pages site is public even when the repository is private.** From the
> [GitHub documentation](https://docs.github.com/en/enterprise-cloud@latest/pages/getting-started-with-github-pages/changing-the-visibility-of-your-github-pages-site):
> *"GitHub Pages sites are publicly available on the internet by default, even if the
> repository for the site is private or internal"*, and *"to publish a GitHub Pages
> site privately, your organization must use GitHub Enterprise Cloud."* Access
> control is Enterprise Cloud only, and only for organization-owned repositories —
> a personal Free or Pro account cannot make a Pages site private at all.
>
> So "private repo + Pages" gives you a private repo and a **world-readable page** at
> a guessable URL. If the report should stay yours, use the single local file above.

If a public report is what you want:

1. **Settings → Pages → Build and deployment → Source: GitHub Actions.**
2. **Settings → Secrets and variables → Actions → New repository secret**, named
   `TOPDECK_API_KEY`.

[`.github/workflows/publish.yml`](.github/workflows/publish.yml) then rebuilds daily
at 05:20 UTC and deploys `site/`. You can also run it by hand from the Actions tab
and set the window, the placing cut, the format and a minimum event size. Without the
secret it still publishes — from the synthetic sample field, so you can see the whole
thing working before committing to a key.

### Private and automated

If you want a scheduled rebuild without a public page, run the workflow on a private
repo and drop the `deploy` job — keep the `upload-pages-artifact` step off and add an
`actions/upload-artifact` step instead. You download `report.html` from the run.
Private, but you fetch it by hand; a local scheduled task is usually less friction.

---

## Command line

```
lorcana-meta build [options]
```

| Option | Default | What it does |
|---|---|---|
| `--source {topdeck,inkdecks,local}` | `topdeck` | Where decklists come from. |
| `--format` | `Core Constructed` | Lorcana format, exactly as TopDeck spells it. |
| `--last N` | `30` | Days back from today. |
| `--start` / `--end` | – | Explicit window, `YYYY-MM-DD`. Overrides `--last`. |
| `--top N` | `32` | Keep finishes this high or better. `0` keeps everything. |
| `--min-players N` | – | Ignore events smaller than this. |
| `--min-pair-decks N` | `3` | Drop ink pairs thinner than this as noise. The report still says how many decks that removed. |
| `--cluster-threshold F` | `0.60` | Card overlap that counts as the same archetype. Lower merges more, higher splits more. |
| `--local-dir` | `data/decks` | Where `--source local` reads from. |
| `--out` | `site/data/meta.json` | Where the report goes. |
| `--api-key` | `$TOPDECK_API_KEY` | TopDeck credentials. |
| `--refresh-cards` | – | Re-download the card database instead of using the 24h cache. |
| `--indent N` | – | Pretty-print the JSON. |

inkdecks-only options (they do nothing for the other sources):

| Option | Default | What it does |
|---|---|---|
| `--inkdecks-category` | `core` | Which of the site's tabs to read: `core`, `infinity`, `poorcana`, `all`. This selects the format for this source — `--format` does not apply. `all` mixes them and labels each deck with its own. |
| `--inkdecks-consent` | – | Confirm you have their written permission. Required. |
| `--inkdecks-delay F` | `3.0` | Seconds between requests. Grows on a 429, never shrinks within a run. |
| `--inkdecks-max-decks N` | `1500` | Stop after this many decks, best-placed first. |
| `--inkdecks-scraper` | `auto` | `auto` escalates to cloudscraper only on a persistent 403; `plain` never does; `cloudscraper` starts there. |

Examples:

```bash
# The last month of Core Constructed, top 32, events of 32+ players
lorcana-meta build --last 30 --top 32 --min-players 32

# One specific set season
lorcana-meta build --start 2026-08-01 --end 2026-08-27

# Winners only, and split archetypes more aggressively
lorcana-meta build --last 60 --top 1 --cluster-threshold 0.75
```

Helper scripts: `tools/bundle_report.py` (single-file report),
`tools/generate_sample_decks.py` (synthetic field),
`tools/import_pasted_decks.py` (see below), `tests/check_report.py` (sanity-check a
built report). On Windows, `scripts/build.ps1` and `scripts/serve.ps1` wrap the
common cases.

---

## Data sources

- **Tournament data:** [TopDeck.gg API v2](https://topdeck.gg/docs/tournaments-v2) —
  free key, documented, supports Disney Lorcana (Core Constructed, Infinity
  Constructed, Sealed, Pack Rush), returns standings with decklists filtered by date
  range. Rate limit ~100 req/min; this project makes one request per month of the
  window. **Using the API requires a visible credit and link back to TopDeck.gg** —
  the report renders it in the footer. Don't remove it.
- **Card data:** [lorcana-api.com](https://lorcana-api.com/) — free, open source, no
  key. One bulk endpoint, cached locally for 24 hours. Supplies card text, cost,
  ink(s), type and the official card images.
- **inkdecks.com:** `--source inkdecks`, and only with their written permission —
  see below. The widest tournament coverage there is, and the reason the archetype
  clustering earns its keep.
- **Your own files:** `--source local` reads `data/decks/*.{json,txt}`. Good for local
  events no platform covers, and for anything you copied by hand. Format:
  [`data/decks/README.md`](data/decks/README.md).

### inkdecks.com — permission required

[inkdecks.com](https://inkdecks.com/) has by far the widest coverage of Lorcana
tournaments, and their terms of use prohibit automated access *"without prior written
consent"*, with a liquidated-damages clause aimed at services built on their data.
So the source exists, and it refuses to run until you confirm you have that consent:

```bash
export INKDECKS_CONSENT=1        # PowerShell: $env:INKDECKS_CONSENT = "1"
python -m pip install -e ".[inkdecks]"
lorcana-meta build --source inkdecks --last 14 --top 32
python tools/bundle_report.py
```

`--inkdecks-category` mirrors the tabs on their listing page — `core` (default),
`infinity`, `poorcana` or `all`.

**Asking works.** The permission this source is written around is personal use with
no commercialised public site built on their data — so it sets `publishable = False`,
which travels into the report and makes `tests/check_report.py` fail, which stops the
Pages workflow from deploying it. If your own permission differs, changing that is a
deliberate edit, not a default to drift into.

It is built to be a good guest, and each of these came out of watching it run:

| Behaviour | Why |
|---|---|
| One request at a time, 3s apart | 6 of 20 requests hit a 429 at 2s. |
| The delay grows on a 429, eases after 10 clean requests, and is remembered between runs | Their sustainable rate is not documented, so it gets discovered rather than guessed. Widening by 1.5x turned one blip into a run-long crawl, so it widens by 1.25x. |
| A refused deck is skipped, not fatal | One page returning 429 three times killed a 369-deck run at deck 100. Losing one decklist moves a percentage by 0.3%; losing the run costs an hour. The skip count is reported. |
| Eight refusals in a row does stop it | At that point it is the site, not one page. |
| Only one build at a time | "One request at a time" only held inside a process. A manual build started while a scheduled one runs doubles the rate; an interleaved log proved it. A lock in the cache directory refuses the second, and a stale one is taken over. |
| Deck pages cached forever | A published decklist never changes. A second build over the same window costs almost no requests. |
| No cookies kept | Their rate limiting counts per session, so re-presenting a `PHPSESSID` gets the next request refused. |
| `--top` maps onto their own filter | A top-8 report fetches 8 listing pages instead of 41. |
| `--inkdecks-max-decks` (1500) | A mistyped date range cannot become thousands of requests. |
| Only `/lorcana-decks` and `/lorcana-metagame/deck-*` | Every path their `robots.txt` disallows is left alone. |

Their limit works out to about 4 deck pages a minute, so a month of Core Constructed
top-32 (~800 decks) is a few hours the first time. Runs resume from the cache and
fetch best-placed first, so stopping and continuing later is a supported way to work
rather than a lost run.

**On Cloudflare and cloudscraper.** Their bot filter rejects any unrecognised
User-Agent, so the source sends a plain browser string — set `INKDECKS_USER_AGENT` if
they ask you to identify differently. What the site actually pushes back with under
load is `429`, a rate limit, and the answer to a rate limit is to slow down, never to
switch HTTP client. `--inkdecks-scraper` therefore defaults to `auto`: plain requests,
escalating to [cloudscraper](https://pypi.org/project/cloudscraper/) only on a
persistent `403` and only if you installed it (`pip install -e ".[cloudscraper]"`).
inkdecks confirmed cloudscraper is acceptable if needed; without that it would be
circumventing a security control, which is not a call to make on your own judgement.

### Copying lists by hand

For a site you have no permission for, reading a page and copying a list off it
yourself is not automated access. `tools/import_pasted_decks.py` makes that bearable
in bulk:

```
### Yurple | Tom G. | 20 | The Dice Cellar Quest | 2026-08-22 | 57
4 Eilonwy - Princess of Llyr
3 Rafiki - Mystical Fighter
...

### Samber |  | 3 | Store Championship | 2026-08-19 |
4 Beast - Selfless Protector
...
```

```bash
python tools/import_pasted_decks.py my-notes.txt --dry-run   # check first
python tools/import_pasted_decks.py my-notes.txt             # -> data/decks/imported.json
lorcana-meta build --source local --last 60
```

Everything after the deck name is optional, card lines take any of the usual shapes,
and section headers are skipped, so a whole-page paste usually works unedited. Lists
that come out under 40 cards are reported and skipped rather than averaged in. Keep
the notes file **outside** `data/decks/` — though if you forget, the local source
recognises it as importer input and refuses to read it as one giant deck.

**The tool fetches nothing.** It only reformats text you already have.

---

## How it is put together

```
src/lorcana_meta/
  cli.py          argument parsing, the build command
  sources/
    topdeck.py    TopDeck.gg API adapter (rate limiting, retries, attribution)
    inkdecks.py   inkdecks.com scraper: consent gate, adaptive throttle, caching
    local.py      decklists from data/decks/*.{json,txt}
    base.py       the one interface a new source has to satisfy
  cards.py        card database + the name folding that makes lists match
  decklist.py     parsing pasted lists and TopDeck's structured deckObj
  cluster.py      archetype detection by card overlap
  analyze.py      shares, inclusion rates, expected copies
  console.py      UTF-8 output on a legacy Windows code page
  models.py       the domain types

site/             index.html + one CSS + one JS file, no dependencies
scripts/          Windows wrappers: setup.ps1, build.ps1, serve.ps1, schedule.ps1
tools/            sample data, the paste importer, the single-file bundler
tests/            dependency-free test suites, fixtures included
```

**Adding a data source** is one file in `src/lorcana_meta/sources/`: implement
`fetch(start, end) -> list[Deck]`, expose `name` / `attribution` /
`attribution_url`, and register it in `sources/__init__.py`. Nothing downstream
changes — the analysis only ever sees `Deck` objects.

---

## Reading the numbers honestly

The report is a **sample of the meta, not a census**, and it says so on its About
page. What to keep in mind:

- Only events on the source platform are counted.
- A standing with no submitted decklist contributes nothing, which biases the field
  towards players who share lists.
- **Inclusion rates say what people played, not what won.** Win rate per archetype is
  a small-sample number; treat it as a hint, not a ranking.
- Percentages move a lot under about 60 decks. Widen the window before concluding
  anything.
- Cards that could not be matched to a printing, truncated lists, and lists with
  unreadable inks are dropped and **counted** — the counts are on the About page, not
  swept under the rug.

## Tests

```bash
python tests/test_pipeline.py       # parsing, ink derivation, the aggregation maths
python tests/test_cluster.py        # archetype detection
python tests/test_local_source.py   # reading decks off disk, the paste importer
python tests/test_inkdecks.py       # inkdecks parsers and the consent gate
python tests/test_bundle.py         # the single-file report stays self-contained
node  tests/test_site_parsing.mjs   # the browser parser still matches the Python one
```

No test dependencies — each file runs on its own, against saved HTML rather than the
network. CI runs all six on Ubuntu **and Windows**, plus an end-to-end build, plus one job that builds with a `cp1250` console
to keep non-ASCII card names printable on a legacy Windows code page.

Two of those exist because of bugs that don't announce themselves:

- `test_site_parsing.mjs` — the report parses pasted decklists in the browser while
  the pipeline parses them in Python. When those drift, a player's list silently
  stops matching the meta and nothing visibly breaks.
- `test_bundle.py` — a bundle that stopped being self-contained still opens. It just
  shows "could not load data/meta.json", and only when you needed it.
- `test_inkdecks.py` — when a scraped site changes its markup, a positional parser
  reads the price column as a placing. Wrong numbers, no error.

`tests/test_inkdecks.py --live` (needs `INKDECKS_CONSENT=1`) additionally fetches two
real pages and checks a full deck comes to 60 cards, which the trimmed fixtures
cannot prove. It never runs in CI.

## Working on it

- [`CLAUDE.md`](CLAUDE.md) — commands, hard rules, and the platform gotchas that have
  already caused bugs. Loaded automatically by Claude Code at every session start.
- [`docs/DECISIONS.md`](docs/DECISIONS.md) — why the project is shaped this way, with
  the traps behind each decision. Most entries exist because something went wrong
  first.

## Licence

MIT — see [LICENSE](LICENSE).

Disney Lorcana is a trademark of Disney and Ravensburger. This is an unofficial fan
project, not published, endorsed or approved by either.
