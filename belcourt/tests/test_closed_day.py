"""Tests for issue #1: produce an image even when the Belcourt has no showtimes.

Covers both halves of the pipeline:

  * the spider (belcourt/spiders/showtimes.py) parsing small HTML snippets that
    mirror the real site's markup, including the shapes seen on closed days
  * the image generator (belcourt_generate_image.py), run as a script in a temp
    directory against the JSON the spider would produce, so we check it exits
    cleanly and writes result.jpg

The real saved pages in belcourt/test_data/ are gitignored, so they are only
exercised when present on your machine (see RealSavedPagesTest).

Run from the repo root, in the inkyenv conda environment (needs Scrapy + Pillow):
    conda run -n inkyenv python -m unittest discover -s belcourt/tests
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

from scrapy.http import HtmlResponse

BELCOURT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BELCOURT_DIR)

from belcourt.spiders.showtimes import ShowtimesSpider, clean_text  # noqa: E402

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

    def test_closed_for_event_uses_one_clean_description(self):
        show = parse(CLOSED_FOR_EVENT_HTML)["shows"][0]
        self.assertEqual(show["show"], ["A Red Carpet Evening"])
        self.assertEqual(
            show["showtimes"],
            ["No films are screening today as we prepare for tonight’s SOLD OUT Red Carpet Evening"],
        )

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

    def run_generator(self, payload):
        with tempfile.TemporaryDirectory() as tmp:
            for name in ("belcourt_generate_image.py", "Montserrat-Bold.ttf", "belcourt-logo.png"):
                shutil.copy(os.path.join(BELCOURT_DIR, name), tmp)
            with open(os.path.join(tmp, "output_showtimes.json"), "w") as f:
                # round-trip through JSON so int keys become strings, as on disk
                json.dump(payload, f)
            result = subprocess.run(
                [sys.executable, "belcourt_generate_image.py"],
                cwd=tmp, capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 0, msg=result.stderr)
            for image in ("result.jpg", "result_optimized.jpg"):
                self.assertGreater(os.path.getsize(os.path.join(tmp, image)), 0)
            return result.stdout


class GenerateImageTest(GeneratorRunner, unittest.TestCase):
    def test_normal_day(self):
        out = self.run_generator([parse(NORMAL_DAY_HTML)])
        self.assertIn("Processing showtimes for date: Sunday, Mar 10", out)
        self.assertNotIn("No shows found", out)

    def test_closed_for_event(self):
        out = self.run_generator([parse(CLOSED_FOR_EVENT_HTML)])
        self.assertIn("Processing show: A Red Carpet Evening", out)

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
