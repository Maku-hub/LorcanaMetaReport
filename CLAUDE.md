# Working on this project

A Lorcana tournament-meta report: pull tournament decklists for a date window,
group decks by what is in them, render a private HTML report. See `README.md` for
what it does and `docs/DECISIONS.md` for **why** it is built this way — that file
records decisions and the traps already fallen into, and reading it will save you
from repeating them.

## Commands

```powershell
.\scripts\setup.ps1                                  # once: creates .venv, installs, caches card data
.\scripts\build.ps1 -Source inkdecks -Days 14 -Top 32 -Bundle
.\scripts\serve.ps1                                  # preview the multi-file site
.\scripts\schedule.ps1 -Source inkdecks -Weekly Monday -At 07:00
```

The project must be installed (`pip install -e ".[inkdecks]"`) so `lorcana-meta` is
on PATH. There is no `PYTHONPATH=` prefix — that is POSIX syntax and fails on
PowerShell.

Run the tests before calling anything done. All six, plus the report check:

```powershell
.venv\Scripts\python.exe tests\test_pipeline.py       # parsing, inks, aggregation maths
.venv\Scripts\python.exe tests\test_cluster.py        # archetype detection
.venv\Scripts\python.exe tests\test_local_source.py   # decks off disk, paste importer
.venv\Scripts\python.exe tests\test_inkdecks.py       # inkdecks parsers, consent, throttle, lock
.venv\Scripts\python.exe tests\test_bundle.py         # the single-file report stays self-contained
node tests\test_site_parsing.mjs                      # browser parser matches the Python one
```

No test dependencies, no network, no permissions needed. `tests/test_inkdecks.py
--live` additionally hits the real site and needs `INKDECKS_CONSENT=1`; it never runs
in CI.

## Hard rules

**Never publish a report built from inkdecks data.** Permission for that source is
personal use only, no public site. The source sets `publishable = False`, which
travels into the report and makes `tests/check_report.py` fail, which stops the Pages
workflow. Do not weaken that chain. A GitHub Pages site is **public even from a
private repo** — access control is Enterprise Cloud only. The private route is
`tools/bundle_report.py` → `report.html`.

**Never remove the inkdecks consent gate.** Their terms prohibit automated access
without written consent. The flag is the user asserting they have it; nothing in the
code may assert it for them.

**Archetypes come from card overlap, never deck names.** The same list is submitted
under half a dozen names — on real data, 7 decks arrived as "Blurple", "Brewing a
Storm", "Stormlight Archive", "YP", "Yeetple" and more. Names are collected for
display only. See `src/lorcana_meta/cluster.py`.

**Copy counts report the mode and the full spread, not just the mean.** A mean of
2.40 hides that 28 of 43 lists run exactly 2.

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
  absolute path). After moving the project, run `.\scripts\setup.ps1 -Recreate`.

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
