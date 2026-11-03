"""Background collector: one human-paced browsing session a day, no Claude needed.

Run by the OS scheduler (see schedule-collector.ps1). It waits a random start
delay, then works through today's plan like one person checking job sites:
- LinkedIn: the searches that are due (the first few every day, the rest
  rotated), paging deeper only while pages come back mostly new, opening the
  full posting for new listings whose titles pass the title net.
- Company job boards: every watchlist company (one request each).
Every request goes through the guard (pacing, caps, daytime only, back-off).
Everything returned is recorded in `seen`. New listings and their details wait
in `listings` until Claude's daily review triages and scores them.

  python -I job-finder/collect.py            # as scheduled (random start delay first)
  python -I job-finder/collect.py --now      # start right away
  python -I job-finder/collect.py --plan     # show today's plan; no network, no changes
  python -I job-finder/collect.py --force    # run even if today's collection already finished
"""

from __future__ import annotations

import argparse
import json
import math
import random
import re
import sys
import time
import traceback
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
for sub in ("guard", "store", "collectors"):
    sys.path.insert(0, str(ROOT / sub))

import ats  # noqa: E402
import linkedin  # noqa: E402
from db import Store  # noqa: E402
from polite import ACTIVE_HOURS, STATE_DIR, Guard, GuardRefused  # noqa: E402
from runlog import RunLog  # noqa: E402
from settings import load as load_settings  # noqa: E402
from settings import search_defaults  # noqa: E402

STATE_PATH = STATE_DIR / "collector_state.json"


def parse_location(raw: str) -> tuple[str, str | None]:
    """'United States (remote only)' -> ('United States', 'remote')."""
    m = re.search(r"\((.*?)\)\s*$", raw)
    note = (m.group(1) if m else "").lower()
    workplace = next((w for w in ("remote", "hybrid", "onsite") if w in note), None)
    return re.sub(r"\s*\(.*\)\s*$", "", raw).strip(), workplace


def unit_key(keywords: str, location: str) -> str:
    return f"{keywords}|{location}"


def plan(search: dict, cfg: dict, state: dict, today: date, linkedin_available: int) -> dict:
    """Today's work, worked out without touching the network. Each search looks back to
    just before it last ran (30 days if never), so rotated or missed searches catch up."""
    budget = max(0, linkedin_available)
    if today.weekday() >= 5:
        budget = math.floor(budget * cfg["weekend_share"])
    search_budget = 0 if budget <= 0 else min(budget, max(1, round(budget * cfg["search_share"])))

    due = []
    for i, kw in enumerate(search["keywords"]):
        for raw in search["locations"] or ["United States"]:
            location, workplace = parse_location(raw)
            last = state.get("last_run", {}).get(unit_key(kw, location))
            days = (today - date.fromisoformat(last)).days if last else 999
            interval = 1 if i < cfg["daily_searches"] else cfg["rotate_days"]
            if days >= interval:
                window = cfg["max_window_days"] if last is None else max(2, min(days + 1, cfg["max_window_days"]))
                due.append({"keywords": kw, "location": location, "workplace": workplace,
                            "priority": i, "overdue": days - interval, "window_days": window})
    due.sort(key=lambda u: (-min(u["overdue"], 30), u["priority"]))
    window = max((u["window_days"] for u in due), default=2)
    return {"window_days": window, "linkedin_budget": budget, "search_budget": search_budget,
            "posting_budget": budget - search_budget, "searches": due, "boards": search["watchlist"]}


def _is_candidate(title: str, search: dict) -> bool:
    if search["skip_words"] and ats.title_matches(title, search["skip_words"]):
        return False
    return not search["title_words"] or ats.title_matches(title, search["title_words"])


class Collector:
    def __init__(self, guard, store, log, search, cfg, state_path=STATE_PATH, rng=None, today=None):
        self.g, self.store, self.log, self.search, self.cfg = guard, store, log, search, cfg
        self.state_path = Path(state_path)
        self.rng = rng or random.Random()
        self.today = today or date.today()
        self.state = json.loads(self.state_path.read_text(encoding="utf-8")) if self.state_path.exists() else {}
        self.stats = {"linkedin_searches": 0, "linkedin_postings": 0, "boards": 0, "listings": 0,
                      "new": 0, "candidates": 0, "stopped": []}

    def linkedin_available(self) -> int:
        s = self.g.status()["linkedin"]
        if s.get("cooldown_until"):
            return 0
        return s["day_cap"] - s["last_day"] - self.cfg["linkedin_reserve"]

    def run(self) -> dict:
        p = plan(self.search, self.cfg, self.state, self.today, self.linkedin_available())
        self.stats["window_days"] = p["window_days"]
        self.log("plan", f"{len(p['searches'])} LinkedIn searches due, budget {p['search_budget']} search pages + "
                         f"{p['posting_budget']} postings, {len(p['boards'])} boards, looking back up to {p['window_days']} days")

        searches = p["searches"][:p["search_budget"]]
        tasks = [("linkedin", s, 0) for s in searches]
        for b in self.rng.sample(p["boards"], len(p["boards"])):  # boards at random points, like a person would
            tasks.insert(self.rng.randint(0, len(tasks)), ("board", b, 0))

        self.search_budget, self.posting_budget = p["search_budget"], p["posting_budget"]
        self.per_search = math.ceil(self.posting_budget / max(1, len(searches)))
        self.linkedin_ok, self.boards_ok = True, {}
        while tasks:
            kind, item, page = tasks.pop(0)
            if kind == "linkedin":
                more = self._linkedin(item, page, item["window_days"],
                                      first_pages_left=sum(t[0] == "linkedin" and t[2] == 0 for t in tasks))
                if more:
                    tasks.insert(0, ("linkedin", item, page + 1))
            else:
                self._board(item)

        self.state["last_collect"] = self.today.isoformat()
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps(self.state, indent=1), encoding="utf-8")
        return self.stats

    def _record(self, items: list[dict], query: str) -> list[dict]:
        self.store.check_seen(items)
        new = [i for i in items if not i["seen"] and not i["job_id"]]
        for i in items:  # keep details for anything still waiting for review, not just today's new ones
            if not i["job_id"] and not (i["seen"] or {}).get("decision"):
                self.store.save_listing(i, query)
        self.stats["listings"] += len(items)
        self.stats["new"] += len(new)
        return new

    def _linkedin(self, unit: dict, page: int, window: int, first_pages_left: int) -> bool:
        """One search page, then postings for its promising new cards. True = fetch the next page."""
        if not self.linkedin_ok or self.search_budget <= 0:
            return False
        query = f"linkedin: {unit['keywords']} | {unit['location']}" + (f" ({unit['workplace']})" if unit["workplace"] else "")
        try:
            cards = linkedin.search(self.g, keywords=unit["keywords"], location=unit["location"],
                                    workplace=unit["workplace"], posted_within_days=window, start=page * 10)
        except GuardRefused as e:
            self._stop("linkedin", e)
            return False
        self.search_budget -= 1
        self.stats["linkedin_searches"] += 1
        self.state.setdefault("last_run", {})[unit_key(unit["keywords"], unit["location"])] = self.today.isoformat()
        new = self._record(cards, query)
        candidates = sorted((c for c in new if _is_candidate(c["title"], self.search)),
                            key=lambda c: c.get("posted_on") or "", reverse=True)
        self.stats["candidates"] += len(candidates)
        self.log("page", f"{query} p{page + 1}: {len(cards)} listings, {len(new)} new, {len(candidates)} to open")

        for c in candidates[:min(self.per_search, self.posting_budget)]:
            try:
                detail = linkedin.posting(self.g, c["source_id"])
            except GuardRefused as e:
                self._stop("linkedin", e)
                return False
            self.posting_budget -= 1
            self.stats["linkedin_postings"] += 1
            self.store.save_listing(detail, query)

        mostly_new = cards and len(new) > len(cards) / 2
        spare = self.search_budget > first_pages_left
        return bool(mostly_new and spare and page + 1 < self.cfg["max_pages"])

    def _board(self, b: dict):
        if self.boards_ok.get(b["platform"]) is False:
            return
        try:
            board = ats.jobs(self.g, b["platform"], b["slug"], self.search["title_words"] or None,
                             include_description=True)
        except GuardRefused as e:
            self.boards_ok[b["platform"]] = False
            self._stop(b["platform"], e)
            return
        self.stats["boards"] += 1
        if not board["found"]:
            self.log("warn", f"{b['company']}: no {b['platform']} board at slug {b['slug']!r}")
            return
        for j in board["jobs"]:
            j["company"] = b["company"]
        new = self._record(board["jobs"], f"{b['platform']}: {b['company']}")
        self.stats["candidates"] += len(new)

    def _stop(self, site: str, err: Exception):
        if site == "linkedin":
            self.linkedin_ok = False
        self.stats["stopped"].append(f"{site}: {err}")
        self.log("stopped", f"{site}: {err}")


def wait_for_active_hours(log, now=None, sleep=time.sleep) -> None:
    """If the trigger fired early (clock change, early wake), wait for the guard's day to start."""
    now = now or datetime.now()
    start = now.replace(hour=ACTIVE_HOURS[0], minute=0, second=0, microsecond=0)
    if now < start:
        wait = (start - now).total_seconds() + random.uniform(60, 900)
        log("waiting", f"before active hours: starting in {wait / 60:.0f} min")
        sleep(wait)


def summarize(stats: dict) -> str:
    s = (f"{stats['listings']} listings checked ({stats['new']} new) from {stats['linkedin_searches']} LinkedIn "
         f"search pages, {stats['linkedin_postings']} postings, and {stats['boards']} company boards.")
    if stats["stopped"]:
        s += " Stopped early: " + "; ".join(stats["stopped"])
    return s


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--now", action="store_true", help="skip the random start delay")
    ap.add_argument("--plan", action="store_true", help="print today's plan and exit")
    ap.add_argument("--force", action="store_true", help="run even if today's collection already finished")
    args = ap.parse_args(argv)

    log = RunLog("collector")
    cfg = load_settings()["collector"]
    search = search_defaults()
    guard = Guard(log=RunLog("guard"))
    store = Store(log=RunLog("store"))

    if args.plan:
        c = Collector(guard, store, log, search, cfg)
        print(json.dumps(plan(search, cfg, c.state, date.today(), c.linkedin_available()), indent=1))
        return 0

    last = store.runs(1, kind="collect")
    if last and last[0]["status"] == "done" and last[0]["started"][:10] == date.today().isoformat() and not args.force:
        log("skip", "today's collection already finished (use --force to run again)")
        return 0

    if not args.now:
        delay = random.uniform(0, cfg["start_jitter_minutes"] * 60)
        log("waiting", f"random start delay: {delay / 60:.0f} min")
        time.sleep(delay)
        wait_for_active_hours(log)

    run_id = store.start_run("collect")
    log("start", "daily collection")
    try:
        stats = Collector(guard, store, log, search, cfg).run()
    except Exception as e:
        log("error", f"collector failed: {e}", trace=traceback.format_exc()[-800:])
        store.finish_run(run_id, "failed", summary=f"Failed: {e}")
        return 1
    status = "stopped" if stats["stopped"] and not stats["listings"] else "done"
    store.finish_run(run_id, status, stats, summarize(stats))
    log("done", summarize(stats))
    return 0


if __name__ == "__main__":
    sys.exit(main())
