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
| **What you'll face** | Every card ranked by **expected copies**, with the archetypes that bring it and whether the field is picking it up. This is the list to build tech against. |
| **Movement column** | Beside every share on all three overview charts — archetype, ink pair and single ink: what gained or lost ground between the two halves of the window. |

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

### Movement is one window cut in half, not last month

The report also shows which decks are gaining and losing ground. It does this without
fetching anything extra: the requested window is split down the middle by date, and
each pair, archetype and ink is counted on either side. The delta sits in a
**Movement** column beside the share it belongs to, on all three overview charts, not
in a table of its own — a separate "what is moving" table meant two lists of the same
decks side by side with different memberships, and the reader had to work out why they
disagreed.

Ink movement is the same measure one level up: decks playing that ink as a share of
its own half. An ink can rise while every pair it appears in falls — it only takes
players moving between that ink's pairs — which is the thing worth knowing about an
ink, so the chart carries it rather than leaving it to be derived.

Two things about that are worth being clear on, because the number looks like
something it is not:

* **It is not a comparison with a previous report.** Same build, same decks, split by
  date. `+9.4 pp` means the deck was 9.4 percentage points more of the field in the
  back half of *this* window than in the front half.
* **A fortnight has weather.** One large event landing in the second half moves every
  share in it. The deck counts are printed next to each percentage for exactly that
  reason, and a share is relative — one deck rising pushes every other down without
  anybody playing them less.

Clustering runs **once**, over the whole window, and the halves only count members of
those clusters. Clustering each half separately would leave the report matching
archetypes across halves — the problem card overlap exists to avoid in the first
place.

Movement is withheld rather than guessed at. A half with fewer than 15 decks, or a
window under 4 days, gets no movement section at all — just a line saying which of
those it was. Individual pairs and archetypes need 8 decks across the window before
they get a delta, because a deck seen three times can swing twenty points on one list.
On a real 320-deck fortnight about nine rows clear that bar and seventy do not, which
is the honest picture rather than a page of noise.

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

### The threat board names decks, not ink pairs

Every card is ranked by **expected copies** — how many sit in a deck drawn at random
from the field — and each row says which archetypes bring it.

Archetypes, not ink pairs, and that distinction is the whole point. On real data the
pair-level version of this line read *"Maleficent - Vengeful Sorceress, played by
Amber/Amethyst 63.2%"*, where one archetype ran it in **every** list and another ran
it in **none**. 63.2% invites preparing for a coin flip when the truth is "one deck
always has it, the other never does" — and which one is across the table is exactly
what the signature cards tell you. Averaging a card across an ink pair is the mush
that clustering by card overlap exists to avoid, and the threat board was the last
place still doing it.

One-off lists are pooled per ink pair rather than listed. Each is a single deck, so a
row per brew would read 100% inclusion on everything it plays and bury the decks worth
preparing for. Pooling keeps the arithmetic whole: every deck running a card belongs to
exactly one contributing group, brews included.

Cards carry **movement** too, on the same window split and the same floor. This is the
most directly useful line in the report: an archetype rising tells you which deck to
prepare for, a card rising tells you what to prepare for regardless of which deck
brings it — and that can happen with no archetype moving at all. The board can be
sorted by it.

Clicking any card anywhere opens its position in this meta: how much of the field runs
it, how many copies, which decks, and which way it is moving.

### The three overview charts are three cuts of one field

The ink-pair and single-ink charts account for every deck. The archetype chart does
not: one-off brews are left out of it, and on a real 320-deck field that is a quarter
of the picture — 15 archetypes covering 74%, with 67 one-off lists holding the other
26%. So the chart states that arithmetic in words. Add the bars up, get 74%, and the
missing 26% is named right there rather than left to be worked out.

Single-ink presence sums to about 200% rather than 100%, because a two-ink deck counts
towards both of its inks. That is labelled on the chart.

`tests/check_report.py` holds the parts that must never drift: every deck belongs to
exactly one archetype of its pair, archetype shares of a pair sum to 100%, and each
ink's deck count equals the pairs that ink appears in. A reader comparing two charts
is doing the obvious thing, and the numbers have to survive it.

---

## Getting started

Everything runs through one command line tool. There are no wrapper scripts to learn
or keep in step with it.

```bash
git clone https://github.com/YOUR-USER/YOUR-REPO.git
cd YOUR-REPO

python -m venv .venv
.venv/Scripts/activate                    # Windows;  source .venv/bin/activate  elsewhere
pip install -e .
```

A virtual environment because this pulls in an HTML parser and a browser-fingerprint
HTTP client, and a personal tool has no business changing what your other Python
projects see. Installing the project is also what puts `lorcana-meta` on PATH — there
is no `PYTHONPATH=` prefix to remember, which matters because that is POSIX shell
syntax and PowerShell reads it as a command name.

### Try it without touching anyone's server

```bash
python tools/generate_sample_decks.py
lorcana-meta build --source local --last 40
python tools/bundle_report.py
```

That writes `report.html`. Open it — no server, no hosting, nothing leaves your
machine. The sample field uses real card names but invented decks, players and
events, and the report says so on its own front page.

### Build from inkdecks

Their terms require written permission for automated access, and the flag below is
you stating you have it — see [inkdecks.com](#inkdecksfrom--permission-required) below.

```bash
export INKDECKS_CONSENT=1                       # bash
$env:INKDECKS_CONSENT = "1"                     # PowerShell, this window
[Environment]::SetEnvironmentVariable("INKDECKS_CONSENT", "1", "User")   # and future ones

lorcana-meta build --last 14 --top 32
python tools/bundle_report.py
```

`inkdecks` is the default source, so `--source` is optional. Set the environment
variable permanently as well as for the current window if you plan to run this from a
scheduled task, which inherits your user environment but not the shell you typed in.

Then open `report.html`. Make a shortcut to it somewhere convenient — that file is the
application as far as daily use is concerned.

### How long the first build takes

Their rate limit, not politeness for its own sake. Measured against the live site:
the delay settles near its 20s ceiling and throughput works out to roughly **4 deck
pages a minute**.

| Window | Decks | First build |
|---|---|---|
| 14 days, top 8 | ~80 | ~20 min |
| 14 days, top 32 | ~370 | ~1.5 h |
| 30 days, top 32 | ~800 | ~3.5 h |

**Every build after that is seconds.** Decklists never change once published, so they
are cached forever and a rebuild only fetches what is new.

A long first build does not have to happen in one sitting. Decks are fetched
best-placed first and everything fetched is cached, so you can stop it with Ctrl+C and
run the same command tomorrow — it resumes where it left off, and a report built from
a partial field says so rather than passing itself off as the whole meta.

### Choosing a window

| You want | Try |
|---|---|
| The current meta, enough decks to trust | `--last 30 --top 32` |
| What is winning, not just what is played | `--last 45 --top 8` |
| A quick look, few requests | `--last 7 --top 8` |
| Only serious events | add `--min-players 32` — on a real window this cut 128 of 258 decks, and skipped those requests entirely |
| A different format | add `--inkdecks-category infinity` (or `poorcana`, or `all`) |

Under about 60 decks the percentages move a lot, and the report says so on its own
front page rather than letting you read noise as a trend.

### On a schedule

Nothing project-specific here — point your scheduler at the same two commands.

Windows, weekly. The meta does not move daily and a weekly cadence is kinder to the
source:

```powershell
$cmd = "cd C:\path\to\repo; .\.venv\Scripts\lorcana-meta.exe build --last 30 --top 32; " +
       ".\.venv\Scripts\python.exe tools\bundle_report.py"
$action  = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -Command `"$cmd`""
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday -At 07:00
Register-ScheduledTask -TaskName LorcanaMetaReport -Action $action -Trigger $trigger `
  -Settings (New-ScheduledTaskSettingsSet -StartWhenAvailable -RunOnlyIfNetworkAvailable)
```

cron:

```cron
0 7 * * 1  cd /path/to/repo && .venv/bin/lorcana-meta build --last 30 --top 32 && .venv/bin/python tools/bundle_report.py
```

Use the absolute path to the venv rather than trusting `PATH` inside the scheduler's
environment. Set `INKDECKS_CONSENT` at user level so the task inherits it.

### Where things live

| Path | What it is |
|---|---|
| `report.html` | The report. Open this. |
| `site/data/meta.json` | The data behind it, if you want to script against it. It records the code that built it — version, commit, and whether the tree was dirty — so a report found on disk months later can say where it came from. |
| `.cache/inkdecks/` | Cached deck pages and the learned request rate. Safe to delete; it just costs a slow rebuild. |
| `.cache/cards.json` | The card database, refreshed daily. |
| `.venv/` | The Python environment. Delete and re-create to reset. |

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

**There is no publish workflow in this repository.** There was one — manual-dispatch
only, and unable to publish inkdecks data — and it was deleted. It was the only thing
here that could make anything public, guarded by three separate checks, for a report
whose whole point is being private. Three guards protecting a capability nobody used
is still a way to lose.

If you do want a public page from decklists you are allowed to redistribute, it is in
the git history (`git log -- .github/workflows/publish.yml`) and it worked: **Settings
→ Pages → Build and deployment → Source: GitHub Actions**, then restore the file. It
runs only when you ask it to, publishes `--source local` only, and runs
`tests/check_report.py` before deploying, which is what stops a private-use licence
reaching a public URL.

### Private and automated

Use Windows Task Scheduler and the single-file bundle. A scheduled task running
`lorcana-meta build` then `python tools/bundle_report.py` leaves `report.html` on your
disk with nothing published anywhere — see [On a schedule](#on-a-schedule).

---

## Command line

```
lorcana-meta build [options]
```

| Option | Default | What it does |
|---|---|---|
| `--source {inkdecks,local}` | `inkdecks` | Where decklists come from. |
| `--format` | `Core Constructed` | Format label for decks that do not carry one — in practice `--source local`. |
| `--last N` | `30` | Days back from today. |
| `--start` / `--end` | – | Explicit window, `YYYY-MM-DD`. Overrides `--last`. |
| `--top N` | `32` | Keep finishes this high or better. `0` keeps everything. |
| `--min-players N` | – | Ignore events smaller than this. For inkdecks it filters on the listing row, so it skips those deck-page requests rather than making and discarding them. Decks whose event size is unknown are kept. |
| `--min-pair-decks N` | `3` | Drop ink pairs thinner than this as noise. The report still says how many decks that removed. |
| `--cluster-threshold F` | `0.60` | Card overlap that counts as the same archetype. Lower merges more, higher splits more. |
| `--local-dir` | `data/decks` | Where `--source local` reads from. |
| `--out` | `site/data/meta.json` | Where the report goes. |
| `--refresh-cards` | – | Re-download the card database instead of using the 24h cache. |
| `--indent N` | – | Pretty-print the JSON. |

inkdecks-only options (they do nothing for the other sources):

| Option | Default | What it does |
|---|---|---|
| `--inkdecks-category` | `core` | Which of the site's tabs to read: `core`, `infinity`, `poorcana`, `all`. This selects the format for this source — `--format` does not apply. `all` mixes them and labels each deck with its own. |
| `--inkdecks-consent` | – | Confirm you have their written permission. Required. |
| `--inkdecks-delay F` | `3.0` | Seconds between requests. Grows on a 429, never shrinks within a run. |
| `--inkdecks-max-decks N` | `1500` | Stop after this many decks, best-placed first. |
| `--inkdecks-scraper` | `auto` | `auto` escalates to curl_cffi only once the client is refused; `plain` never does; `curl_cffi` starts there. Whichever worked is remembered. |

Examples:

```bash
# The last month of Core Constructed, top 32, events of 32+ players
lorcana-meta build --last 30 --top 32 --min-players 32

# One specific set season
lorcana-meta build --start 2026-08-01 --end 2026-08-27

# Winners only, and split archetypes more aggressively
lorcana-meta build --last 60 --top 1 --cluster-threshold 0.75
```

The rest of the tooling: `tools/bundle_report.py` (single-file report),
`tools/generate_sample_decks.py` (synthetic field), `tools/import_pasted_decks.py`
(see below), and `tests/check_report.py` (sanity-check a built report).

To preview the multi-file version instead of the bundle, serve `site/` — a `file://`
open will not work, because the page fetches `data/meta.json` and browsers block that
on the file protocol:

```bash
cd site && python -m http.server 8000
```

---

## Data sources

- **inkdecks.com** (`--source inkdecks`, the default) — the widest tournament coverage
  there is, and the reason the archetype clustering earns its keep. Needs their
  written permission; see below.
- **Card data:** [lorcana-api.com](https://lorcana-api.com/) — free, open source, no
  key. One bulk endpoint, cached locally for 24 hours. Supplies card text, cost,
  ink(s), type and the official card images.
- **Your own files** (`--source local`) reads `data/decks/*.{json,txt}`. Good for local
  events no platform covers, and for anything you copied by hand. Format:
  [`data/decks/README.md`](data/decks/README.md).

### inkdecks.com — permission required

[inkdecks.com](https://inkdecks.com/) has by far the widest coverage of Lorcana
tournaments, and their terms of use prohibit automated access *"without prior written
consent"*, with a liquidated-damages clause aimed at services built on their data.
So the source exists, and it refuses to run until you confirm you have that consent:

```bash
export INKDECKS_CONSENT=1        # PowerShell: $env:INKDECKS_CONSENT = "1"
lorcana-meta build --last 14 --top 32
python tools/bundle_report.py
```

`--inkdecks-category` mirrors the tabs on their listing page — `core` (default),
`infinity`, `poorcana` or `all`.

**Asking works.** The permission this source is written around is personal use with
no commercialised public site built on their data — so it sets `publishable = False`,
which travels into the report and makes `tests/check_report.py` fail — so anything
that publishes has to be told to ignore a failing check first. If your own permission
differs, changing that is a deliberate edit, not a default to drift into.

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

**On Cloudflare.** The site sits behind rules that treat `429` and `403` as two
different problems, and so does this:

`429` is a rate limit. The answer is to slow down — the delay widens, eases after a
clean stretch, and is remembered between runs. Never to switch client.

`403` is a block on *what the client is*. Measured directly: a browser on this
machine is served normally while every Python client on the same connection is
refused on every path, the site root included — no `Retry-After`, no `429`. That is
a WAF rule keyed on TLS fingerprint, not on address or rate.
[cloudscraper](https://pypi.org/project/cloudscraper/) does not solve it and was
removed: it handles the older JavaScript challenge but still speaks Python's TLS, so
it presents the fingerprint being refused (tested against the live block: `403`).
[curl_cffi](https://pypi.org/project/curl-cffi/) does solve it, by presenting a real
browser's TLS fingerprint.

`--inkdecks-scraper` therefore defaults to `auto`: plain HTTP first, escalating to
curl_cffi only once the plain path has been refused and backing off has not helped.
Whichever worked is remembered, so the next run does not re-earn the same refusals.

Using it is impersonation, so the grounds are worth stating: inkdecks gave written
permission for automated access, said they cannot practically allow-list an address,
and approved a bypass tool if one proved necessary. Remove any of those and this
would be circumventing a security control rather than exercising an agreement — not
a pattern to copy elsewhere.

It changes the handshake, not the crawl: same two paths, same one-at-a-time pacing,
same read-only wrapper.

### How the reading actually works

Two request shapes, and nothing else.

```
1. listing page        /lorcana-decks/core?deck_type=tournament&rank=top32
                        &start_date=...&end_date=...&page=N
   -> one row per deck: placing, W-L-D, player, deck name, inks, archetype label,
      event, attendance, date, and the link to the deck
   -> repeated for each page, until the pager runs out

2. deck page           /lorcana-metagame/deck-<slug>-<id>
   -> <table id="decklist">, one <tr class="card-list-item"> per card,
      quantity in data-quantity, the card in a link to its details page
```

Everything else follows from those two:

- **Parsed by content, not position.** Fields are found by what they contain — a
  date-shaped string, an `N Players` match, an ink symbol's `alt` — never by column
  index. A positional parser reacts to a layout change by reading the price column
  as a placing: wrong numbers, no error.
- **Cached by immutability.** A published decklist never changes, so deck pages are
  cached forever and a rebuild only fetches what is new. Listing pages get an hour,
  since events keep being added.
- **One request at a time**, with a gap that widens on a 429 and eases back after a
  clean stretch. A lock file stops two builds running at once, because "one at a
  time" only ever held inside a single process.
- **Read-only by construction.** The session wrapper exposes `get` and raises on
  `post`, `put`, `patch`, `delete` and `request`. No forms, no logins, no images, no
  assets — HTML in, parsed, cached, done. Bytes read are counted and logged.
- **Only paths their `robots.txt` allows.** The write-shaped endpoints it disallows
  (`/decksubmissions`, `/suggestions/add`) are unreachable from here, and a test
  checks every path the source can build against that list.

Roughly 130 KB per deck page and 245 KB per listing page, so a full two-week top-32
window is around 50 MB — once. After that the cache carries it and a refresh costs
a handful of requests.


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
    inkdecks.py   inkdecks.com scraper: consent gate, adaptive throttle, caching
    local.py      decklists from data/decks/*.{json,txt}
    base.py       the one interface a new source has to satisfy
  cards.py        card database + the name folding that makes lists match
  decklist.py     parsing pasted decklists, forgivingly
  cluster.py      archetype detection by card overlap
  analyze.py      shares, inclusion rates, expected copies, movement in the window
  console.py      UTF-8 output on a legacy Windows code page
  models.py       the domain types

site/             index.html + one CSS + one JS file, no dependencies
tools/            sample data, the paste importer, the single-file bundler
tests/            dependency-free test suites, fixtures included
```

**Adding a data source** is one file in `src/lorcana_meta/sources/`: implement
`fetch(start, end) -> list[Deck]`, expose `name` / `attribution` /
`attribution_url` / `publishable`, and register it in `sources/__init__.py`. Nothing
downstream changes — the analysis only ever sees `Deck` objects.

**Adding a field to the report** means giving it a reader in `site/assets/app.js`.
`tests/test_report_shape.py` fails on a field nothing reads, because the whole JSON
is shipped to the browser and inlined into `report.html`, and on a field the page
reads that the build stopped emitting, because that renders as a blank cell rather
than an error.

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
python tests/test_report_shape.py   # the report and the page agree on their shape
python tests/test_bundle.py         # the single-file report stays self-contained
python tests/check_report.py        # a built report is sane (needs a build first)
node   tests/test_render.mjs        # every page renders (needs a build first)
```

No test dependencies — each file runs on its own, against saved HTML rather than the
network. CI runs all seven on Ubuntu **and Windows**, plus an end-to-end build, plus
`ruff check`, plus one job that builds with a `cp1250` console to keep non-ASCII card
names printable on a legacy Windows code page.

Four exist because of bugs that don't announce themselves:

- `test_bundle.py` — a bundle that stopped being self-contained still opens. It just
  shows "could not load data/meta.json", and only when you needed it.
- `test_inkdecks.py` — when a scraped site changes its markup, a positional parser
  reads the price column as a placing. Wrong numbers, no error.
- `test_report_shape.py` — a field the build stops emitting renders as a blank cell,
  not an error. It also holds the opposite line: nothing may ship in the JSON that
  nothing reads, since the whole file goes to the browser and into `report.html`.
- `test_render.mjs` — the page throwing during render leaves a blank screen with no
  clue on it. This renders every page and checks each one says what it should. It is
  the only test needing node, and needs no npm packages.

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
