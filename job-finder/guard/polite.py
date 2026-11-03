"""Polite, logged-out, read-only request guard for the job finder.

Every network request any collector makes (plain HTTP or a headless browser)
must pass through Guard.permit(). The guard, not the caller, decides when a
request may go out, so a bug or a loop in a collector cannot hammer a site.

What it enforces:
  - Allowlist: only known hosts and known read-only URL paths. Login, apply,
    checkpoint and similar paths are refused outright.
  - Read-only: GET only (per-site exceptions must be listed explicitly).
  - Logged-out: refuses Cookie / Authorization headers; fetch() uses no cookie jar.
  - Human pacing: one request at a time across ALL processes (file lock), a
    randomized wait between requests (with occasional longer "reading" pauses),
    hourly and daily caps per site, and daytime-only hours.
  - Pushback: a 429/999/403, a CAPTCHA, or a login wall puts that site into a
    long cooldown and every later request to it is refused until it expires.

Caps are deliberately low. TEST_MODE (default on) lowers them further.
Stdlib only.
"""

from __future__ import annotations

import json
import os
import random
import re
import sys
import time
import urllib.error
import urllib.request
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
from runlog import RunLog  # noqa: E402
from settings import load as load_settings  # noqa: E402

STATE_DIR = Path(__file__).resolve().parent.parent / "state"

# From profile/settings.json ("test_mode"). Flip to false only once the test runs look healthy.
TEST_MODE = bool(load_settings()["test_mode"])

# A single, fixed, ordinary desktop browser identity. Never rotated.
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"
)

# Paths that are never fetched, on any site.
FORBIDDEN_PATH = re.compile(
    r"(login|signin|sign-in|signup|sign-up|register|checkpoint|authwall|"
    r"apply|easy-apply|account|messaging|inbox|/in/|/feed)",
    re.IGNORECASE,
)

# Response hints that a site is pushing back.
PUSHBACK_STATUS = {401, 403, 429, 999}
PUSHBACK_TEXT = re.compile(
    r"(captcha|are you a robot|unusual activity|security verification|"
    r"authwall|checkpoint/challenge|access denied|too many requests)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class SitePolicy:
    hosts: tuple[str, ...]
    paths: tuple[str, ...]          # regexes; a URL path must match one
    wait_s: tuple[float, float]     # randomized gap between requests to this site
    per_hour: int
    per_day: int
    cooldown_h: float = 24
    methods: tuple[str, ...] = ("GET",)
    test_per_day: int | None = None  # cap while TEST_MODE is on


SITES: dict[str, SitePolicy] = {
    "linkedin": SitePolicy(
        hosts=("www.linkedin.com", "linkedin.com"),
        paths=(
            r"^/jobs-guest/jobs/api/seeMoreJobPostings/search$",
            r"^/jobs-guest/jobs/api/jobPosting/\d+$",
        ),
        wait_s=(25, 90),
        per_hour=15,
        per_day=40,
        cooldown_h=48,
        test_per_day=6,
    ),
    "greenhouse": SitePolicy(
        hosts=("boards-api.greenhouse.io",),
        paths=(r"^/v1/boards/[\w-]+/jobs$",),
        wait_s=(5, 20),
        per_hour=60,
        per_day=200,
        test_per_day=10,
    ),
    "lever": SitePolicy(
        hosts=("api.lever.co",),
        paths=(r"^/v0/postings/[\w-]+$",),
        wait_s=(5, 20),
        per_hour=60,
        per_day=200,
        test_per_day=10,
    ),
    "ashby": SitePolicy(
        hosts=("api.ashbyhq.com",),
        paths=(r"^/posting-api/job-board/[\w.-]+$",),
        wait_s=(5, 20),
        per_hour=60,
        per_day=200,
        test_per_day=10,
    ),
}

CHALLENGE_PAGE_MAX = 20_000   # real challenge/login-wall pages are small


def pushback_snippet(body: str) -> str:
    """The part of a response worth scanning for CAPTCHA / login-wall text.

    Full job descriptions can legitimately contain words like "access denied"
    or "captcha" (security roles), so only small pages are scanned in full;
    for normal-sized pages only the <title> is checked.
    """
    if len(body) < CHALLENGE_PAGE_MAX:
        return body
    m = re.search(r"<title[^>]*>(.*?)</title>", body[:5000], re.S | re.I)
    return m.group(1) if m else ""


GLOBAL_MIN_GAP_S = 4         # between any two requests, any site
ACTIVE_HOURS = (7, 22)        # local time; nothing runs overnight
LONG_PAUSE_CHANCE = 0.15      # sometimes linger, like reading a posting
LONG_PAUSE_S = (60, 180)
LOCK_STALE_S = 15 * 60


class GuardRefused(Exception):
    """The guard refused a request. Never retry around this."""


@dataclass
class Guard:
    state_dir: Path = STATE_DIR
    test_mode: bool = TEST_MODE
    clock: callable = time.time
    sleep: callable = time.sleep
    now_local: callable = datetime.now
    rng: random.Random = field(default_factory=random.Random)
    log: callable = field(default_factory=lambda: RunLog("guard"))

    # ---------- public API ----------

    @contextmanager
    def permit(self, url: str, method: str = "GET", headers: dict | None = None):
        """Wait until a request to `url` is allowed, then yield the site name.

        Holds the cross-process lock for the wait and the request itself, so
        only one request is ever in flight. Call report() with the response.
        """
        try:
            site, policy = self._check_static(url, method, headers or {})
        except GuardRefused as e:
            self.log("refused", str(e), url=url)
            raise
        with self._lock():
            state = self._load()
            try:
                self._check_dynamic(site, policy, state)
            except GuardRefused as e:
                self.log("refused", str(e), site=site, url=url)
                raise
            self._wait(site, policy, state, url)
            self._record(site, state)
            self._save(state)
            yield site

    def report(self, site: str, status: int, body_snippet: str = "") -> None:
        """Tell the guard how a request went. Pushback triggers a cooldown."""
        if status in PUSHBACK_STATUS or PUSHBACK_TEXT.search(body_snippet or ""):
            hours = SITES[site].cooldown_h
            with self._lock():
                state = self._load()
                state.setdefault(site, {})["cooldown_until"] = self.clock() + hours * 3600
                state[site]["last_pushback"] = {"status": status, "at": self.clock()}
                self._save(state)
            msg = (
                f"{site} pushed back (status {status}); cooling down {hours:g}h. "
                "Switch this source to email alerts if it keeps happening."
            )
            self.log("pushback", msg, site=site, status=status)
            raise GuardRefused(msg)

    def fetch(self, url: str) -> tuple[int, str]:
        """Logged-out GET through the guard. No cookie jar, no auth."""
        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/json;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }
        with self.permit(url, "GET", headers) as site:
            # build_opener without HTTPCookieProcessor = cookies are never stored or sent
            opener = urllib.request.build_opener()
            req = urllib.request.Request(url, headers=headers, method="GET")
            self.log("request", "", site=site, url=url)
            started = time.monotonic()
            try:
                with opener.open(req, timeout=30) as resp:
                    status, body = resp.status, resp.read().decode("utf-8", "replace")
            except urllib.error.HTTPError as e:
                status, body = e.code, e.read().decode("utf-8", "replace")
            except (urllib.error.URLError, TimeoutError) as e:
                self.log("error", f"network error: {e}", site=site, url=url)
                raise
            ms = int((time.monotonic() - started) * 1000)
            self.log("response", "", site=site, status=status, bytes=len(body), ms=ms, url=url)
        self.report(site, status, pushback_snippet(body))
        return status, body

    def status(self) -> dict:
        state = self._load()
        out = {}
        day_ago, hour_ago = self.clock() - 86400, self.clock() - 3600
        for site, policy in SITES.items():
            s = state.get(site, {})
            times = s.get("times", [])
            out[site] = {
                "last_hour": sum(t > hour_ago for t in times),
                "last_day": sum(t > day_ago for t in times),
                "day_cap": self._day_cap(policy),
                "cooldown_until": s.get("cooldown_until"),
            }
        return out

    # ---------- checks ----------

    def _check_static(self, url, method, headers):
        parsed = urlparse(url)
        if parsed.scheme != "https":
            raise GuardRefused(f"https only: {url}")
        for name in headers:
            if name.lower() in ("cookie", "authorization"):
                raise GuardRefused("logged-out only: Cookie/Authorization headers are refused")
        if FORBIDDEN_PATH.search(parsed.path):
            raise GuardRefused(f"forbidden path (login/apply/account): {parsed.path}")
        for site, policy in SITES.items():
            if parsed.hostname in policy.hosts:
                if method.upper() not in policy.methods:
                    raise GuardRefused(f"{site}: method {method} not allowed (read-only)")
                if not any(re.match(p, parsed.path) for p in policy.paths):
                    raise GuardRefused(f"{site}: path not on the allowlist: {parsed.path}")
                return site, policy
        raise GuardRefused(f"host not on the allowlist: {parsed.hostname}")

    def _check_dynamic(self, site, policy, state):
        hour = self.now_local().hour
        if not (ACTIVE_HOURS[0] <= hour < ACTIVE_HOURS[1]):
            raise GuardRefused(f"outside active hours {ACTIVE_HOURS} (local hour {hour})")
        s = state.get(site, {})
        if s.get("cooldown_until", 0) > self.clock():
            left = (s["cooldown_until"] - self.clock()) / 3600
            raise GuardRefused(f"{site} is cooling down after pushback ({left:.1f}h left)")
        times = s.get("times", [])
        now = self.clock()
        if sum(t > now - 3600 for t in times) >= policy.per_hour:
            raise GuardRefused(f"{site}: hourly cap {policy.per_hour} reached")
        cap = self._day_cap(policy)
        if sum(t > now - 86400 for t in times) >= cap:
            raise GuardRefused(f"{site}: daily cap {cap} reached")

    def _day_cap(self, policy):
        if self.test_mode and policy.test_per_day is not None:
            return min(policy.per_day, policy.test_per_day)
        return policy.per_day

    # ---------- pacing ----------

    def _wait(self, site, policy, state, url=""):
        now = self.clock()
        site_last = max(state.get(site, {}).get("times", [0]) or [0])
        global_last = state.get("_global_last", 0)
        gap = self.rng.uniform(*policy.wait_s)
        if self.rng.random() < LONG_PAUSE_CHANCE:
            gap += self.rng.uniform(*LONG_PAUSE_S)
        ready_at = max(site_last + gap, global_last + GLOBAL_MIN_GAP_S)
        delay = ready_at - now
        if delay > 0:
            self.log("waiting", f"{delay:.0f}s before next request", site=site, url=url)
            self.sleep(delay)

    def _record(self, site, state):
        now = self.clock()
        s = state.setdefault(site, {})
        s["times"] = [t for t in s.get("times", []) if t > now - 86400] + [now]
        state["_global_last"] = now

    # ---------- state + lock ----------

    @property
    def _state_path(self):
        return Path(self.state_dir) / "guard_state.json"

    @property
    def _lock_path(self):
        return Path(self.state_dir) / "guard.lock"

    def _load(self):
        try:
            return json.loads(self._state_path.read_text())
        except FileNotFoundError:
            return {}

    def _save(self, state):
        Path(self.state_dir).mkdir(parents=True, exist_ok=True)
        tmp = self._state_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(state, indent=1))
        os.replace(tmp, self._state_path)

    @contextmanager
    def _lock(self):
        Path(self.state_dir).mkdir(parents=True, exist_ok=True)
        deadline = time.time() + LOCK_STALE_S + 60
        while True:
            try:
                fd = os.open(self._lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(fd, str(os.getpid()).encode())
                os.close(fd)
                break
            except FileExistsError:
                try:
                    if time.time() - self._lock_path.stat().st_mtime > LOCK_STALE_S:
                        self._lock_path.unlink(missing_ok=True)
                        continue
                except FileNotFoundError:
                    continue
                if time.time() > deadline:
                    raise GuardRefused("another collector holds the request lock")
                time.sleep(1)
        try:
            yield
        finally:
            self._lock_path.unlink(missing_ok=True)


if __name__ == "__main__":
    print(json.dumps(Guard().status(), indent=2))
