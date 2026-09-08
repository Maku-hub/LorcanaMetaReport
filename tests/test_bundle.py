"""Tests for the single-file bundle.

This is the path that matters for a private report: GitHub Pages cannot host one
(a Pages site from a private personal repo is public), so the offline bundle is the
answer, and it only works if the file is genuinely self-contained.

A regression here is silent. The bundle keeps opening; it just shows "Could not load
data/meta.json" because a page on file:// may not fetch its siblings - and you would
only find out when you actually needed the report.
"""

from __future__ import annotations

import json
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lorcana_meta.bundle import _inline_safe, build  # noqa: E402
from lorcana_meta.console import configure_output  # noqa: E402

FAILURES: list[str] = []

REPORT = ROOT / "site" / "data" / "meta.json"
INDEX = ROOT / "site" / "index.html"


def check(condition, message):
    if not condition:
        FAILURES.append(message)


def _bundle() -> str:
    with tempfile.TemporaryDirectory() as directory:
        out = Path(directory) / "report.html"
        code = build(INDEX, REPORT, out)
        check(code == 0, f"build returned {code}")
        return out.read_text(encoding="utf-8")


def test_bundle_is_self_contained():
    html = _bundle()

    # Any local file still referenced would be missing once the bundle is moved.
    for match in re.finditer(r'(?:src|href)="([^"]+)"', html):
        target = match.group(1)
        if target.startswith(("#", "data:", "http://", "https://", "${")):
            continue
        FAILURES.append(f"bundle still points at a local file: {target}")

    check("<style>" in html, "the stylesheet was inlined")
    check("function renderOverview" in html, "the script was inlined")
    check('id="meta-data"' in html, "the report data was inlined")


def test_inlined_data_parses_and_matches():
    html = _bundle()
    match = re.search(
        r'<script type="application/json" id="meta-data">(.*?)</script>', html, re.S
    )
    check(match is not None, "the data tag is present and closed")
    if not match:
        return

    # The browser reads textContent, which does not resolve the \\u escapes the
    # bundler writes - JSON.parse does. json.loads behaves the same way.
    embedded = json.loads(match.group(1))
    original = json.loads(REPORT.read_text(encoding="utf-8"))
    check(embedded == original, "the embedded report is identical to the source")


def test_script_cannot_be_closed_from_inside_the_data():
    """A `</script>` in a card's rules text must not end the block early."""
    hostile = '{"text": "</script><img src=x onerror=alert(1)>"}'
    safe = _inline_safe(hostile)

    check("</script>" not in safe, f"the closing tag is escaped: {safe}")
    check("<" not in safe, f"no raw angle brackets survive: {safe}")
    check(json.loads(safe) == json.loads(hostile), "escaping does not change the value")


def test_line_separators_are_escaped():
    """U+2028 and U+2029 are valid in JSON strings but break JavaScript source."""
    separators = chr(0x2028) + chr(0x2029)
    value = {"text": "a" + separators + "b"}
    safe = _inline_safe(json.dumps(value, ensure_ascii=False))

    check(all(sep not in safe for sep in separators), "both separators escaped")
    check(json.loads(safe) == value, "value preserved")


def test_a_build_writes_the_single_file_by_default():
    """The bundle is part of a build, not a step you have to remember.

    Left as a second command it went quietly stale: rebuild the data, forget the
    bundle, open the file - it renders perfectly and shows the previous window. The
    embedded build stamp is the only clue and it only helps someone who looks.
    """
    from lorcana_meta.cli import main as cli_main

    with tempfile.TemporaryDirectory() as directory:
        data = Path(directory) / "meta.json"
        out = Path(directory) / "report.html"
        code = cli_main(
            [
                "build",
                "--source",
                "local",
                "--local-dir",
                str(ROOT / "data" / "decks"),
                "--last",
                "400",
                "--out",
                str(data),
                "--bundle-out",
                str(out),
            ]
        )
        check(code == 0, f"the build succeeded, got {code}")
        check(data.exists(), "it wrote the data")
        check(out.exists(), "and the single file, with no second command")
        if out.exists():
            html = out.read_text(encoding="utf-8")
            check('id="meta-data"' in html, "the data is inlined in it")
            embedded = json.loads(
                re.search(r'id="meta-data"[^>]*>(.*?)</script>', html, re.S).group(1)
                .replace("\u003c", "<")
                .replace("\u003e", ">")
            )
            live = json.loads(data.read_text(encoding="utf-8"))
            check(
                embedded["generated_at"] == live["generated_at"],
                "and it is the data this build just wrote, not an older one",
            )


def test_a_build_can_be_told_not_to_bundle():
    """Serving `site/` directly needs the data and nothing else."""
    from lorcana_meta.cli import main as cli_main

    with tempfile.TemporaryDirectory() as directory:
        data = Path(directory) / "meta.json"
        out = Path(directory) / "report.html"
        code = cli_main(
            [
                "build",
                "--source",
                "local",
                "--local-dir",
                str(ROOT / "data" / "decks"),
                "--last",
                "400",
                "--out",
                str(data),
                "--bundle-out",
                str(out),
                "--no-bundle",
            ]
        )
        check(code == 0, f"the build succeeded, got {code}")
        check(data.exists(), "it wrote the data")
        check(not out.exists(), "and left the single file alone")


def main() -> int:
    configure_output()
    if not REPORT.exists():
        print(f"{REPORT} is missing - run a build first", file=sys.stderr)
        return 1

    tests = [value for name, value in sorted(globals().items()) if name.startswith("test_")]
    for test in tests:
        try:
            test()
        except Exception as error:
            FAILURES.append(f"{test.__name__} raised {error!r}")

    if FAILURES:
        print(f"{len(FAILURES)} failure(s):")
        for failure in FAILURES:
            print(f"  - {failure}")
        return 1
    print(f"{len(tests)} tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
