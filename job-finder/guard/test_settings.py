"""Offline tests for settings.py (temp folders, no network).

  python -I job-finder/guard/test_settings.py
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from settings import DEFAULTS, load, search_defaults  # noqa: E402

TEMPLATES = Path(__file__).resolve().parent.parent.parent / "templates" / "profile"


class SettingsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def test_missing_files_give_defaults(self):
        self.assertEqual(load(self.tmp), DEFAULTS)
        self.assertTrue(DEFAULTS["collector"]["linkedin_reserve"] >= 0)
        self.assertTrue(all(v == [] for v in search_defaults(self.tmp).values()))

    def test_file_overlays_defaults_and_skips_notes(self):
        (self.tmp / "settings.json").write_text(json.dumps(
            {"_help": "x", "pay": {"floor": 1, "_n": "y"}, "test_mode": False}), encoding="utf-8")
        s = load(self.tmp)
        self.assertEqual(s["pay"], {"floor": 1, "target_low": None, "target_high": None})
        self.assertFalse(s["test_mode"])
        self.assertEqual(s["stale_days"], 45)
        self.assertNotIn("_help", s)

    def test_bad_json_names_the_file(self):
        (self.tmp / "settings.json").write_text("{nope", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "settings.json"):
            load(self.tmp)

    def test_search_md_bullets_in_order(self):
        (self.tmp / "search.md").write_text(
            "# S\n## Searches\nintro\n- Director of Product\n- Principal PM\n\n## Title net\n- product\n"
            "## Locations\n- Denver, Colorado\n## LinkedIn filters\n- **Posted within:** 7 days\n", encoding="utf-8")
        got = search_defaults(self.tmp)
        self.assertEqual(got["keywords"], ["Director of Product", "Principal PM"])
        self.assertEqual(got["locations"], ["Denver, Colorado"])
        self.assertEqual(got["title_words"], ["product"])

    def test_watchlist_table_and_skip_words(self):
        (self.tmp / "search.md").write_text(
            "## Company watchlist (job boards)\nintro\n\n| Company | Platform | Slug | Why |\n|---|---|---|---|\n"
            "| Acme | Greenhouse | `acme` | x |\n| _(e.g. Foo)_ | greenhouse | _(foo)_ | |\n| Bad | workday | bad | |\n\n"
            "## Skip\n- **Companies:** _( )_\n- **Title words that mean noise:** intern, \"food science\"\n",
            encoding="utf-8")
        got = search_defaults(self.tmp)
        self.assertEqual(got["watchlist"], [{"company": "Acme", "platform": "greenhouse", "slug": "acme"}])
        self.assertEqual(got["skip_words"], ["intern", "food science"])

    def test_old_keywords_heading_still_works(self):
        (self.tmp / "search.md").write_text("## Keywords\n- Head of Product\n", encoding="utf-8")
        self.assertEqual(search_defaults(self.tmp)["keywords"], ["Head of Product"])

    def test_template_placeholders_are_ignored(self):
        self.assertTrue(all(v == [] for v in search_defaults(TEMPLATES).values()))
        s = load(TEMPLATES)
        self.assertTrue(s["test_mode"])
        self.assertEqual(s["private_terms"], [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
