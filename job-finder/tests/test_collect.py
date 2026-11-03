"""Offline tests for the background collector (fake guard, temp store, no network).

  python -I job-finder/tests/test_collect.py
"""

import json
import random
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent.parent
for sub in ("", "guard", "store", "collectors"):
    sys.path.insert(0, str(ROOT / sub))
import collect  # noqa: E402
from db import Store  # noqa: E402
from polite import GuardRefused  # noqa: E402
from runlog import null_log  # noqa: E402
from settings import DEFAULTS  # noqa: E402

CFG = dict(DEFAULTS["collector"])
SEARCH = {"keywords": ["Director of Product", "Principal PM", "Head of Product", "Group PM", "VP Product"],
          "locations": ["Denver, Colorado", "United States (remote only)"],
          "title_words": ["product", "PM"], "skip_words": ["intern"],
          "watchlist": [{"company": "Acme", "platform": "greenhouse", "slug": "acme"}]}
MONDAY, SATURDAY = date(2026, 11, 2), date(2026, 11, 7)


def card(jid, title):
    return (f'<li><div data-entity-urn="urn:li:jobPosting:{jid}"><h3 class="base-search-card__title">{title}</h3>'
            f'<h4 class="base-search-card__subtitle">Co{jid}</h4><span class="job-search-card__location">Remote</span>'
            f'<time datetime="2026-11-01"></time></div></li>')


class FakeGuard:
    """Serves canned LinkedIn and Greenhouse responses; can refuse after N LinkedIn requests."""

    def __init__(self, cap=40, used=0, refuse_after=None, titles=None):
        self.cap, self.used, self.refuse_after = cap, used, refuse_after
        self.titles = titles or ["Director of Product", "Product Intern", "Staff Accountant"]
        self.urls, self.log = [], null_log

    def status(self):
        return {"linkedin": {"day_cap": self.cap, "last_day": self.used, "cooldown_until": None}}

    def fetch(self, url):
        self.urls.append(url)
        if "linkedin" in url:
            if self.refuse_after is not None and sum("linkedin" in u for u in self.urls) > self.refuse_after:
                raise GuardRefused("daily cap reached for linkedin")
            if "jobPosting/" in url:
                jid = url.rsplit("/", 1)[1]
                return 200, (f'<h2 class="top-card-layout__title">Job {jid}</h2>'
                             f'<div class="show-more-less-html__markup">Full description {jid}</div>')
            q = parse_qs(urlparse(url).query)
            base = int(q["start"][0]) * 10 + len(q["keywords"][0]) * 1000
            return 200, "".join(card(base + i, t) for i, t in enumerate(self.titles))
        return 200, json.dumps({"jobs": [
            {"id": 1, "title": "Senior Product Manager", "absolute_url": "https://x/1", "content": "desc"},
            {"id": 2, "title": "Payroll Specialist", "absolute_url": "https://x/2", "content": "desc"}]})


class PlanTests(unittest.TestCase):
    def test_first_run_backfills_and_everything_is_due(self):
        p = collect.plan(SEARCH, CFG, {}, MONDAY, 39)
        self.assertEqual(p["window_days"], 30)
        self.assertEqual(len(p["searches"]), 10)
        self.assertEqual(p["search_budget"] + p["posting_budget"], 39)
        self.assertEqual(p["searches"][1]["workplace"], "remote")

    def test_rotation_daily_vs_every_few_days(self):
        state = {"last_collect": "2026-11-01",
                 "last_run": {collect.unit_key(k, loc): "2026-11-01"
                              for k in SEARCH["keywords"] for loc in ("Denver, Colorado", "United States")}}
        due = {s["keywords"] for s in collect.plan(SEARCH, CFG, state, MONDAY, 39)["searches"]}
        self.assertEqual(due, set(SEARCH["keywords"][:3]))  # rotated ones ran yesterday
        later = collect.plan(SEARCH, CFG, state, date(2026, 11, 4), 39)
        self.assertEqual(len(later["searches"]), 10)
        self.assertEqual(later["window_days"], 4)  # gap widens the look-back

    def test_weekend_is_lighter_and_no_budget_means_no_searches(self):
        self.assertEqual(collect.plan(SEARCH, CFG, {}, SATURDAY, 20)["linkedin_budget"], 10)
        self.assertEqual(collect.plan(SEARCH, CFG, {}, MONDAY, 0)["search_budget"], 0)


class ActiveHoursTests(unittest.TestCase):
    def test_early_trigger_waits_until_seven(self):
        from datetime import datetime
        waits = []
        collect.wait_for_active_hours(null_log, datetime(2026, 11, 1, 6, 20), waits.append)
        self.assertTrue(40 * 60 + 60 <= waits[0] <= 40 * 60 + 900)
        collect.wait_for_active_hours(null_log, datetime(2026, 11, 1, 8, 0), waits.append)
        self.assertEqual(len(waits), 1)


class CollectorTests(unittest.TestCase):
    def setUp(self):
        tmp = Path(tempfile.mkdtemp())
        self.store = Store(tmp / "jobs.db", log=null_log)
        self.state = tmp / "collector_state.json"

    def run_collector(self, guard, today=MONDAY):
        c = collect.Collector(guard, self.store, null_log, SEARCH, CFG, self.state, random.Random(1), today)
        return c.run()

    def test_collects_queue_and_opens_only_title_net_matches(self):
        g = FakeGuard(cap=10)  # 9 available -> 4 search pages, 5 postings
        stats = self.run_collector(g)
        self.assertEqual(stats["boards"], 1)
        self.assertEqual(stats["linkedin_searches"], 4)
        q = self.store.review_queue(limit=100)["items"]
        titles = {i["title"] for i in q}
        self.assertIn("Senior Product Manager", titles)          # board match, via the title net
        self.assertNotIn("Payroll Specialist", titles)            # filtered by the title net
        opened = [u for u in g.urls if "jobPosting/" in u]
        self.assertTrue(opened)
        self.assertTrue(all(i.get("description") for i in q if i["source"] == "linkedin"
                            and i["title"].startswith("Job ")))  # posting details replaced card titles
        self.assertEqual(json.loads(self.state.read_text())["last_collect"], "2026-11-02")

    def test_second_day_sees_repeats_as_seen(self):
        self.run_collector(FakeGuard(cap=10))
        stats = self.run_collector(FakeGuard(cap=10), today=date(2026, 11, 3))
        self.assertLess(stats["new"], stats["listings"])

    def test_guard_refusal_stops_linkedin_but_boards_still_run(self):
        stats = self.run_collector(FakeGuard(cap=40, refuse_after=1))
        self.assertEqual(stats["linkedin_searches"], 1)
        self.assertEqual(stats["boards"], 1)
        self.assertTrue(any("linkedin" in s for s in stats["stopped"]))

    def test_pages_deeper_only_when_mostly_new_and_budget_spare(self):
        g = FakeGuard(cap=40, titles=[f"Product Role {i}" for i in range(10)])
        self.run_collector(g)
        starts = [parse_qs(urlparse(u).query)["start"][0] for u in g.urls if "seeMoreJobPostings" in u]
        self.assertIn("10", starts)


if __name__ == "__main__":
    unittest.main(verbosity=2)
