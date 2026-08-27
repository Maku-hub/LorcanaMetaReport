# Test fixtures

Trimmed excerpts of inkdecks.com pages, saved so the parser tests run with no
network, no API key and no permission of your own.

- `inkdecks-list.html` — three rows of a tournament listing table, plus a pager.
- `inkdecks-deck.html` — a decklist table with its section header and four card rows.

## Why they are excerpts

They exist to detect a change in the site's markup, and four card rows prove that as
well as sixty. Keeping them minimal also keeps this repository from being a copy of
someone else's content — relevant because permission to read a site for your own use
is not permission to redistribute its pages.

If you need to check a whole real page parses correctly, do it live rather than by
committing one:

```bash
INKDECKS_CONSENT=1 python tests/test_inkdecks.py --live
```

That fetches two pages and asserts a full deck comes to 60 cards. It is skipped
unless you ask for it, so CI never touches the network.

## Refreshing them

When the site changes shape, replace the excerpts with new ones of the same size and
fix whatever the tests then report. Do not paste in a full page.
