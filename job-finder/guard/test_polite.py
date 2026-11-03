"""Offline tests for the guard. No network: a fake clock stands in for time.

Run:  python -I job-finder/guard/test_polite.py
"""

import random
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from polite import Guard, GuardRefused, SITES  # noqa: E402
from runlog import null_log  # noqa: E402

SEARCH = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?keywords=product&location=Denver&start=0"
DETAIL = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/4012345678"


class FakeClock:
    def __init__(self):
        self.t = 1_800_000_000.0
        self.slept = []

    def time(self):
        return self.t

    def sleep(self, s):
        self.slept.append(s)
        self.t += s


def make_guard(tmp, test_mode=True, hour=10):
    clock = FakeClock()
    g = Guard(
        state_dir=Path(tmp),
        test_mode=test_mode,
        clock=clock.time,
        sleep=clock.sleep,
        now_local=lambda: datetime(2026, 11, 2, hour, 0),
        rng=random.Random(1),
        log=null_log,
    )
    return g, clock


def hit(g, url=SEARCH):
    with g.permit(url) as site:
        pass
    g.report(site, 200, "<li>job</li>")


class TestStaticRules(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.g, _ = make_guard(self.tmp)

    def refused(self, url, **kw):
        with self.assertRaises(GuardRefused):
            with self.g.permit(url, **kw):
                pass

    def test_unknown_host(self):
        self.refused("https://www.indeed.com/jobs?q=product")

    def test_http_not_https(self):
        self.refused(SEARCH.replace("https", "http"))

    def test_login_and_apply_paths(self):
        self.refused("https://www.linkedin.com/login")
        self.refused("https://www.linkedin.com/jobs/view/123/apply")
        self.refused("https://www.linkedin.com/checkpoint/challenge")
        self.refused("https://www.linkedin.com/in/someone")

    def test_logged_in_linkedin_pages_not_allowlisted(self):
        self.refused("https://www.linkedin.com/jobs/search/?keywords=product")

    def test_cookie_and_auth_headers(self):
        self.refused(SEARCH, headers={"Cookie": "li_at=abc"})
        self.refused(SEARCH, headers={"Authorization": "Bearer x"})

    def test_post_refused(self):
        self.refused(SEARCH, method="POST")


class TestPacing(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def test_gap_between_requests_is_humanlike(self):
        g, clock = make_guard(self.tmp)
        lo = SITES["linkedin"].wait_s[0]
        hit(g)
        start = clock.t
        hit(g, DETAIL)
        self.assertGreaterEqual(clock.t - start, lo)

    def test_daily_cap_in_test_mode(self):
        g, _ = make_guard(self.tmp)
        cap = SITES["linkedin"].test_per_day
        for _ in range(cap):
            hit(g)
        with self.assertRaisesRegex(GuardRefused, "daily cap"):
            hit(g)

    def test_hourly_cap_outside_test_mode(self):
        g, clock = make_guard(self.tmp, test_mode=False)
        # Freeze time so every request lands in the same hour
        g.sleep = lambda s: None
        for _ in range(SITES["linkedin"].per_hour):
            hit(g)
        with self.assertRaisesRegex(GuardRefused, "hourly cap"):
            hit(g)

    def test_caps_survive_a_new_process(self):
        g, clock = make_guard(self.tmp)
        for _ in range(SITES["linkedin"].test_per_day):
            hit(g)
        g2 = Guard(state_dir=Path(self.tmp), clock=clock.time, sleep=clock.sleep,
                   now_local=lambda: datetime(2026, 11, 2, 10), log=null_log)
        with self.assertRaisesRegex(GuardRefused, "daily cap"):
            hit(g2)

    def test_night_hours_refused(self):
        g, _ = make_guard(self.tmp, hour=3)
        with self.assertRaisesRegex(GuardRefused, "active hours"):
            hit(g)


class TestPushback(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def test_429_triggers_cooldown(self):
        g, clock = make_guard(self.tmp)
        with g.permit(SEARCH) as site:
            pass
        with self.assertRaises(GuardRefused):
            g.report(site, 429)
        with self.assertRaisesRegex(GuardRefused, "cooling down"):
            hit(g)
        clock.t += 49 * 3600
        hit(g)  # allowed again after the cooldown

    def test_captcha_text_triggers_cooldown(self):
        g, _ = make_guard(self.tmp)
        with g.permit(SEARCH) as site:
            pass
        with self.assertRaises(GuardRefused):
            g.report(site, 200, "<title>Security Verification</title> captcha")
        with self.assertRaisesRegex(GuardRefused, "cooling down"):
            hit(g)

    def test_security_job_text_is_not_pushback(self):
        from polite import pushback_snippet
        posting = "<html><title>Director, Security</title>" + "x" * 30000 + " access denied captcha </html>"
        self.assertEqual(pushback_snippet(posting), "Director, Security")
        g, _ = make_guard(self.tmp)
        with g.permit(SEARCH) as site:
            pass
        g.report(site, 200, pushback_snippet(posting))  # must not raise
        hit(g, DETAIL)

    def test_small_challenge_page_is_pushback(self):
        from polite import pushback_snippet
        page = "<html><title>Security Verification</title>Please complete the CAPTCHA</html>"
        g, _ = make_guard(self.tmp)
        with g.permit(SEARCH) as site:
            pass
        with self.assertRaises(GuardRefused):
            g.report(site, 200, pushback_snippet(page))

    def test_linkedin_999(self):
        g, _ = make_guard(self.tmp)
        with g.permit(SEARCH) as site:
            pass
        with self.assertRaises(GuardRefused):
            g.report(site, 999)


if __name__ == "__main__":
    unittest.main(verbosity=2)
