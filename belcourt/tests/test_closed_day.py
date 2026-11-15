"""Tests for issue #1: produce an image even when the Belcourt has no showtimes.

Covers both halves of the pipeline:

  * the spider (belcourt/spiders/showtimes.py) parsing small HTML snippets that
    mirror the real site's markup, including the shapes seen on closed days
  * the image generator (belcourt_generate_image.py), run as a script in a temp
    directory against the JSON the spider would produce, so we check it exits
    cleanly and writes result.jpg

The real saved pages in belcourt/test_data/ are gitignored, so they are only
exercised when present on your machine (see RealSavedPagesTest).

Run from the repo root (uv installs Scrapy + Pillow from uv.lock on first run):
    uv run python -m unittest discover -s belcourt/tests -v
"""
import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from unittest import mock
from zoneinfo import ZoneInfo

from scrapy.http import HtmlResponse

BELCOURT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BELCOURT_DIR)

from belcourt.spiders import showtimes as showtimes_module  # noqa: E402
from belcourt.spiders.showtimes import ShowtimesSpider, clean_text  # noqa: E402

CENTRAL = ZoneInfo("America/Chicago")

TEST_DATA_DIR = os.path.join(BELCOURT_DIR, "test_data")


def today_block(inner, date="Sunday, Mar 10"):
    """Wrap event-list markup in the site's 'today' container."""
    return (
        '<html><body><div class="day today">'
        f'<h4 class="widget-subtitle">{date}</h4>'
        f'<ul class="day-event-list">{inner}</ul>'
        '</div></body></html>'
    )


# Same shape as test_data/belcourt - no film.html: an event with no showtimes,
# only a description, and a title whose <a> and <span> both carry the class.
CLOSED_FOR_EVENT_HTML = today_block(
    '<li>\n'
    '<a class="day-event-list__title" href="https://www.belcourt.org/redcarpet/">\n'
    '<span class="day-event-list__title">A Red Carpet Evening</span>\n'
    '</a>\n'
    '<p class="day-event-list__description">No films are screening today as '
    'we prepare for <em>tonight’s</em>  SOLD OUT Red Carpet Evening</p>\n'
    '</li>'
)

NORMAL_DAY_HTML = today_block(
    '<li><a class="day-event-list__title">ANORA (<em>35mm</em>)</a>'
    '<ul class="day-event-list__time-list">'
    '<li><a>1:25pm</a></li><li><a> </a></li><li><a>6:35pm</a></li>'
    '</ul></li>'
)

EMPTY_LIST_HTML = today_block("", date="Thursday, Dec 25")

NO_TODAY_BLOCK_HTML = "<html><body><p>We are closed.</p></body></html>"


def parse(html):
    """Run the spider's parse() on an HTML string and return a plain dict."""
    response = HtmlResponse(url="https://belcourt.org/", body=html.encode("utf-8"), encoding="utf-8")
    with contextlib.redirect_stdout(io.StringIO()):  # spider prints debug output
        return dict(ShowtimesSpider().parse(response))


class CleanTextTest(unittest.TestCase):
    def test_strips_and_collapses_whitespace(self):
        self.assertEqual(clean_text(["\n", "A Red Carpet Evening", "\n"]), "A Red Carpet Evening")
        self.assertEqual(clean_text(["a  b\n\tc"]), "a b c")

    def test_does_not_add_spaces_between_tag_fragments(self):
        self.assertEqual(clean_text(["ANORA (", "35mm", ")"]), "ANORA (35mm)")

    def test_empty(self):
        self.assertEqual(clean_text([]), "")
        self.assertEqual(clean_text(["\n", " "]), "")


class SpiderTest(unittest.TestCase):
    def test_normal_day(self):
        item = parse(NORMAL_DAY_HTML)
        self.assertEqual(item["date"], ["Sunday, Mar 10"])
        self.assertEqual(item["shows"][0]["show"], ["ANORA (35mm)"])
        self.assertEqual(item["shows"][0]["showtimes"], ["1:25pm", "6:35pm"])

    def test_normal_day_has_no_description(self):
        self.assertEqual(parse(NORMAL_DAY_HTML)["shows"][0]["description"], "")

    def test_closed_for_event_uses_one_clean_description(self):
        show = parse(CLOSED_FOR_EVENT_HTML)["shows"][0]
        self.assertEqual(show["show"], ["A Red Carpet Evening"])
        # description goes in its own field so the generator can format it
        self.assertEqual(show["showtimes"], [])
        self.assertEqual(
            show["description"],
            "No films are screening today as we prepare for tonight’s SOLD OUT Red Carpet Evening",
        )

    def test_currenttime_is_central_not_machine_time(self):
        # 01:30 UTC on Nov 16 is still 7:30pm on Nov 15 in Nashville (CST,
        # UTC-6). A naive datetime.now() on a UTC runner would say Nov 16.
        instant = datetime(2026, 11, 16, 1, 30, tzinfo=timezone.utc)

        class FrozenDatetime(datetime):
            @classmethod
            def now(cls, tz=None):
                return instant.astimezone(tz) if tz else instant.replace(tzinfo=None)

        with mock.patch.object(showtimes_module, "datetime", FrozenDatetime):
            item = parse(NO_TODAY_BLOCK_HTML)
        self.assertEqual(item["currenttime"], "2026-11-15 19:30:00")

    def test_empty_event_list(self):
        item = parse(EMPTY_LIST_HTML)
        self.assertEqual(item["date"], ["Thursday, Dec 25"])
        self.assertEqual(item["shows"], {})

    def test_no_today_block(self):
        item = parse(NO_TODAY_BLOCK_HTML)
        self.assertEqual(item["date"], [])
        self.assertEqual(item["shows"], {})


class GeneratorRunner:
    """Mixin: runs belcourt_generate_image.py as the GitHub Action does (cwd = belcourt)."""

    def run_generator(self, payload, env=None):
        with tempfile.TemporaryDirectory() as tmp:
            for name in ("belcourt_generate_image.py", "Montserrat-Bold.ttf", "belcourt-logo.png"):
                shutil.copy(os.path.join(BELCOURT_DIR, name), tmp)
            with open(os.path.join(tmp, "output_showtimes.json"), "w") as f:
                # round-trip through JSON so int keys become strings, as on disk
                json.dump(payload, f)
            result = subprocess.run(
                [sys.executable, "belcourt_generate_image.py"],
                cwd=tmp, capture_output=True, text=True,
                env={**os.environ, **(env or {})},
            )
            self.assertEqual(result.returncode, 0, msg=result.stderr)
            for image in ("result.jpg", "result_optimized.jpg"):
                self.assertGreater(os.path.getsize(os.path.join(tmp, image)), 0)
            return result.stdout


class GenerateImageTest(GeneratorRunner, unittest.TestCase):
    def test_normal_day(self):
        out = self.run_generator([parse(NORMAL_DAY_HTML)])
        self.assertIn("Processing showtimes for date: Sunday, Mar 10", out)
        self.assertIn("Line: ANORA (35mm) 1:25pm, 6:35pm", out)
        self.assertNotIn("\u2014", out)
        self.assertNotIn("No shows found", out)

    def test_closed_for_event(self):
        out = self.run_generator([parse(CLOSED_FOR_EVENT_HTML)])
        self.assertIn(
            "Line: A Red Carpet Evening \u2014 No films are screening today as we prepare for", out
        )

    def test_old_json_with_description_in_showtimes_still_renders(self):
        # JSON written before the "description" field existed (no such key)
        old = {"date": ["Sunday, Mar 10"], "shows": {"0": {
            "show": ["A Red Carpet Evening"], "showtimes": ["No films are screening today"]}}}
        out = self.run_generator([old])
        self.assertIn("Line: A Red Carpet Evening No films are screening today", out)

    def test_title_only_event(self):
        item = {"date": ["Sunday, Mar 10"], "shows": {"0": {
            "show": ["MEMBERS ONLY"], "showtimes": [], "description": ""}}}
        out = self.run_generator([item])
        self.assertIn("Line: MEMBERS ONLY\n", out)

    def test_empty_event_list_renders_closed_message(self):
        out = self.run_generator([parse(EMPTY_LIST_HTML)])
        self.assertIn("No shows found; rendering closed message", out)

    def test_no_today_block_falls_back_to_scrape_date(self):
        item = parse(NO_TODAY_BLOCK_HTML)
        item["currenttime"] = "2024-12-25 10:07:56"
        out = self.run_generator([item])
        self.assertIn("Processing showtimes for date: Wednesday, Dec 25", out)
        self.assertIn("No shows found; rendering closed message", out)

    def test_missing_currenttime_and_empty_output(self):
        # Worst case: spider produced nothing usable. Still make an image.
        self.run_generator([{}])
        self.run_generator([])

    def test_last_resort_date_uses_central_not_machine_tz(self):
        # Run the generator in UTC+14, where "today" is usually a day ahead of
        # Nashville. With no date and no currenttime, it must still use the
        # Central date. Compute the expected date before and after the run so
        # the test can't flake if Central midnight passes mid-test.
        def central_today():
            now = datetime.now(CENTRAL)
            return f"{now:%A, %b} {now.day}"

        before = central_today()
        out = self.run_generator([{}], env={"TZ": "Pacific/Kiritimati"})
        after = central_today()
        self.assertTrue(
            f"Processing showtimes for date: {before}" in out
            or f"Processing showtimes for date: {after}" in out,
            msg=out,
        )


@unittest.skipUnless(os.path.isdir(TEST_DATA_DIR), "belcourt/test_data/ not present (gitignored)")
class RealSavedPagesTest(GeneratorRunner, unittest.TestCase):
    """End-to-end over every saved page in test_data/, when available locally."""

    def test_saved_pages(self):
        pages = [p for p in sorted(os.listdir(TEST_DATA_DIR)) if p.endswith(".html")]
        for page in pages:
            with self.subTest(page=page):
                with open(os.path.join(TEST_DATA_DIR, page), encoding="utf-8") as f:
                    item = parse(f.read())
                self.assertTrue(item["date"], "saved page should have a date")
                self.run_generator([item])


if __name__ == "__main__":
    unittest.main()
