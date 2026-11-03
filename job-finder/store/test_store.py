"""Offline tests for the store's seen-tracking and the loose title matcher.

  python -I job-finder/store/test_store.py
"""

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for sub in ("store", "guard", "collectors"):
    sys.path.insert(0, str(ROOT / sub))
from ats import title_matches  # noqa: E402
from db import Store  # noqa: E402
from runlog import null_log  # noqa: E402


def card(sid, title="Director of Product", company="Acme", source="linkedin"):
    return {"source": source, "source_id": sid, "title": title, "company": company}


class SeenTests(unittest.TestCase):
    def setUp(self):
        self.s = Store(Path(tempfile.mkdtemp()) / "jobs.db", log=null_log)

    def test_first_time_new_second_time_seen(self):
        first = self.s.check_seen([card("1")])[0]
        self.assertIsNone(first["seen"])
        self.assertIsNone(first["job_id"])
        again = self.s.check_seen([card("1")])[0]
        self.assertEqual(again["seen"]["days_seen"], 1)
        self.assertIsNone(again["seen"]["decision"])

    def test_saved_job_is_known_on_other_sites(self):
        job_id, _ = self.s.upsert({"title": "Director of Product", "company": "Acme Inc",
                                   "sources": [{"source": "linkedin", "source_id": "1"}]})
        same_site = self.s.check_seen([card("1")])[0]
        self.assertEqual(same_site["seen"]["decision"], "saved")
        other_site = self.s.check_seen([card("z9", title="Director of Product", company="Acme",
                                             source="indeed")])[0]
        self.assertIsNone(other_site["seen"])
        self.assertEqual(other_site["job_id"], job_id)

    def test_skip_is_remembered_with_reason(self):
        self.s.check_seen([card("2", title="Pharmacist")])
        self.s.mark_seen("linkedin", "2", "skipped", "wrong field")
        seen = self.s.check_seen([card("2", title="Pharmacist")])[0]["seen"]
        self.assertEqual((seen["decision"], seen["reason"]), ("skipped", "wrong field"))

    def test_indeed_counter_ids_dont_collide(self):
        """JOBSEARCH_1 today and JOBSEARCH_1 tomorrow can be different jobs."""
        job_id, _ = self.s.upsert({"title": "Head of Product", "company": "Globex",
                                   "sources": [{"source": "indeed", "source_id": "JOBSEARCH_1"}]})
        other = self.s.check_seen([card("JOBSEARCH_1", title="Payroll Clerk", company="Zed", source="indeed")])[0]
        self.assertIsNone(other["seen"])
        self.assertIsNone(other["job_id"])
        same = self.s.check_seen([card("JOBSEARCH_7", title="Head of Product", company="GLOBEX", source="indeed")])[0]
        self.assertEqual(same["job_id"], job_id)
        self.assertEqual(same["seen"]["decision"], "saved")
        self.s.mark_seen("indeed", "JOBSEARCH_9", "skipped", "noise", title="Payroll Clerk", company="Zed")
        self.assertEqual(self.s.check_seen([card("JOBSEARCH_2", title="Payroll Clerk", company="Zed",
                                                 source="indeed")])[0]["seen"]["decision"], "skipped")

    def test_stats_count_new_listings(self):
        self.s.check_seen([card("1"), card("2"), card("3", source="dice")])
        stats = self.s.seen_stats()
        self.assertEqual(sum(stats["new_per_day"]["linkedin"].values()), 2)
        self.assertEqual(stats["totals"]["seen"], 3)
        self.assertEqual(stats["totals"]["unreviewed"], 3)


class CompletenessTests(unittest.TestCase):
    def setUp(self):
        self.s = Store(Path(tempfile.mkdtemp()) / "jobs.db", log=null_log)

    def save(self, **kw):
        return self.s.upsert({"title": "Group PM", "company": "Acme", **kw})[0]

    def test_gaps_listed_until_cleared(self):
        jid = self.save(description="card", gaps=[{"what": "description", "why": "card only"}],
                        analysis={"score": 50})
        self.assertEqual([g["what"] for g in self.s.incomplete()[0]["gaps"]], ["description"])
        self.save(description="the full posting, much longer than the card", gaps=[])
        job = next(j for j in self.s.jobs() if j["id"] == jid)
        self.assertEqual(job["description"], "the full posting, much longer than the card")
        self.assertEqual(self.s.incomplete(), [])

    def test_shorter_description_never_replaces(self):
        self.save(description="the full posting text")
        self.save(description="card")
        self.assertEqual(self.s.jobs()[0]["description"], "the full posting text")

    def test_overwrite_replaces_fields(self):
        self.save(location="Seattle, WA")
        self.save(location="Remote (US)", overwrite=True)
        self.assertEqual(self.s.jobs()[0]["location"], "Remote (US)")

    def test_marked_or_strong_jobs_need_a_one_pager(self):
        weak = self.s.upsert({"title": "PM", "company": "Weak Co", "analysis": {"score": 40}, "gaps": []})[0]
        self.s.upsert({"title": "PM", "company": "Strong Co", "analysis": {"score": 72}, "gaps": []})
        self.assertEqual([j["company"] for j in self.s.incomplete()], ["Strong Co"])
        self.s.set_status(weak, "interested")
        self.assertEqual([j["company"] for j in self.s.incomplete()], ["Weak Co", "Strong Co"])  # marked first
        self.s.save_company("Strong Co, Inc.", {"overview": "x"})
        self.assertEqual([j["company"] for j in self.s.incomplete()], ["Weak Co"])
        self.assertEqual(self.s.company("strong co")["overview"], "x")

    def test_dismissed_jobs_are_never_incomplete(self):
        jid = self.save(gaps=[{"what": "news"}], analysis={"score": 50})
        self.s.set_status(jid, "dismissed")
        self.assertEqual(self.s.incomplete(), [])

    def test_weak_fits_skip_backfill_unless_marked(self):
        jid = self.save(gaps=[{"what": "news"}], analysis={"score": 30})
        self.assertEqual(self.s.incomplete(), [])
        self.s.set_status(jid, "interested")
        self.assertEqual(len(self.s.incomplete()), 1)


class TitleNetTests(unittest.TestCase):
    NET = ["product", "PM", "AI"]

    def test_variants_match(self):
        for t in ["VP, Products", "Product Director", "Director, Product Management", "Group PM",
                  "Head of Product (Remote)", "Sr. Product Manager - AI Platform", "AI Solutions Lead"]:
            self.assertTrue(title_matches(t, self.NET), t)

    def test_unrelated_and_word_fragments_dont(self):
        for t in ["Production Supervisor", "Airline Pilot", "Software Engineer", "Maintenance Aide"]:
            self.assertFalse(title_matches(t, self.NET), t)

    def test_multiword_terms(self):
        self.assertTrue(title_matches("Director - Product  Management", ["product management"]))
        self.assertFalse(title_matches("Product Marketing Manager", ["product management"]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
