"""Setup progress and schedules, for the report's Setup page and status line.

Claude records a step as done (`setup_mark`) only after it has actually checked
it: tests passed, the scheduled task exists and ran once, and so on. Where the
code can check a step itself (the installer ran, a review has happened, the
Windows collector task exists), that check has to pass too.

State lives in profile/setup.json, which is the person's own file:
  {"steps": {"<id>": {"done": true, "at": "...", "note": "..."}},
   "schedules": {"<id>": {"label": "...", "kind": "claude" | "windows", "task": "...",
                           "cron": "M H dom mon dow", "note": "..."}}}
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

KIT = Path(__file__).resolve().parent.parent.parent
PROFILE = KIT / "profile"
STATE_FILE = PROFILE / "setup.json"
COLLECTOR_TASK = "Job Finder Collector"  # the name schedule-collector.ps1 registers

# (id, title, what it is, what to say to Claude, needed before the job list opens)
STEPS = [
    ("installed", "Install the kit", "Creates your private folders and registers the job-finder tools with Claude.",
     "Set this up for me.", True),
    ("profile", "Build your profile",
     "Claude reads your resumes and interviews you: target roles and level, pay, locations, deal-breakers, "
     "companies you like, and what never to mention. This is what every score and resume draws on.",
     "Let's build my profile.", True),
    ("connectors", "Connect the job sites", "Indeed, ZipRecruiter, and Dice connectors in the Claude app (you sign in yourself).",
     "Help me connect the job sites.", True),
    ("tests", "Check that it works", "Offline tests, then one small live LinkedIn check through the request guard.",
     "Run the setup tests.", True),
    ("first_run", "First job search", "Claude runs the playbook once by hand so you can see the report before anything is automated.",
     "Run the job finder for the first time.", True),
    ("collector_schedule", "Daily collection", "A background task on this computer that gathers new listings every morning. No Claude involved.",
     "Help me schedule the daily collection.", False),
    ("review_schedule", "Daily review", "A Claude scheduled task that triages, researches, and scores what was collected.",
     "Set up the daily review task.", False),
    ("drafts_schedule", "Resume drafts", "A Claude scheduled task that drafts a tailored resume for each job you mark Interested.",
     "Set up the resume drafts task.", False),
    ("base_resume", "Base resume", "Your source-of-truth resume and the style every tailored draft uses.",
     "Let's build my base resume.", False),
]
STEP_IDS = [s[0] for s in STEPS]


def load() -> dict:
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {"steps": {}, "schedules": {}}


def save(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


def mark(step: str, done: bool = True, note: str = "", schedule: dict | None = None) -> dict:
    """Record a step (and, for schedule steps, the schedule: {label, kind, task, cron, note})."""
    if step not in STEP_IDS:
        raise ValueError(f"unknown step {step!r}; one of {STEP_IDS}")
    state = load()
    state.setdefault("steps", {})[step] = {"done": bool(done), "at": datetime.now().isoformat(timespec="seconds"),
                                           "note": note}
    if schedule:
        if schedule.get("cron"):
            next_cron(schedule["cron"])  # raises on a bad expression
        state.setdefault("schedules", {})[step] = schedule
    save(state)
    return state


# ---- checks the code can do itself ----

def _placeholders(path: Path) -> int | None:
    return path.read_text(encoding="utf-8").count("_(") if path.exists() else None


_task_cache: tuple[float, dict | None] = (0.0, None)


def collector_task() -> dict | None:
    """The Windows collector task's state from schtasks, or None (not Windows / not registered).
    Cached for a minute: the app asks on every page load."""
    global _task_cache
    if sys.platform != "win32":
        return None
    if time.monotonic() - _task_cache[0] < 60:
        return _task_cache[1]
    try:
        # CREATE_NO_WINDOW: the app server runs windowless (pythonw), so a console child would flash a window
        out = subprocess.run(["schtasks", "/query", "/tn", COLLECTOR_TASK, "/fo", "LIST", "/v"],
                             capture_output=True, text=True, timeout=10,
                             creationflags=subprocess.CREATE_NO_WINDOW).stdout
    except (OSError, subprocess.TimeoutExpired):
        return None
    fields = dict(re.findall(r"^([A-Za-z ]+):\s+(.*?)\s*$", out, re.M))
    task = None if "Next Run Time" not in fields else {
        "next_run": _parse_win_time(fields.get("Next Run Time")), "last_run": _parse_win_time(fields.get("Last Run Time")),
        "status": fields.get("Status"), "last_result": fields.get("Last Result")}
    _task_cache = (time.monotonic(), task)
    return task


def _parse_win_time(s: str | None) -> str | None:
    for fmt in ("%m/%d/%Y %I:%M:%S %p", "%d/%m/%Y %H:%M:%S", "%m/%d/%Y %H:%M:%S"):
        try:
            return datetime.strptime(s or "", fmt).isoformat(timespec="minutes")
        except ValueError:
            pass
    return None


def auto_checks(store, task: dict | None = None) -> dict:
    """{step: (ok, detail)} for the steps the code can verify. `task`: collector_task(), if already fetched."""
    checks = {"installed": (PROFILE.is_dir() and (KIT / "job-finder" / "state").is_dir(),
                            "profile/ and job-finder/state/ exist" if PROFILE.is_dir() else "the installer hasn't run")}
    left = [n for n in (_placeholders(PROFILE / "targets.md"), _placeholders(PROFILE / "search.md")) if n is not None]
    if len(left) < 2:
        checks["profile"] = (False, "targets.md or search.md is missing")
    else:
        checks["profile"] = (sum(left) <= 3, "filled in" if sum(left) <= 3 else f"{sum(left)} blanks left in targets.md and search.md")
    reviews = store.runs(1, "review")
    checks["first_run"] = (bool(reviews), f"last review {reviews[0]['started'][:16].replace('T', ' ')}" if reviews else "no review yet")
    if task is not None or sys.platform == "win32":
        checks["collector_schedule"] = (task is not None, "Windows task registered" if task else "Windows task not found")
    try:
        name = json.loads((PROFILE / "resume.json").read_text(encoding="utf-8"))["basics"]["name"]
        checks["base_resume"] = (name != "Jordan Rivera", "profile/resume.json is yours" if name != "Jordan Rivera"
                                 else "profile/resume.json is still the sample")
    except (FileNotFoundError, KeyError, json.JSONDecodeError):
        checks["base_resume"] = (False, "no profile/resume.json yet")
    return checks


AUTO_ONLY = {"installed", "first_run", "collector_schedule"}  # done as soon as the check passes


def status(store) -> dict:
    """Every step with its state (done / check / todo), plus schedules with their next run."""
    state, task = load(), collector_task()
    checks = auto_checks(store, task)
    steps = []
    for sid, title, what, ask, required in STEPS:
        marked = state.get("steps", {}).get(sid, {})
        ok, detail = checks.get(sid, (None, ""))
        if ok is False:
            st = "check" if marked.get("done") else "todo"
        elif ok and sid in AUTO_ONLY:
            st = "done"
        else:
            st = "done" if marked.get("done") else "todo"
        steps.append({"id": sid, "title": title, "what": what, "ask": ask, "required": required, "state": st,
                      "detail": detail, "note": marked.get("note", ""), "at": marked.get("at")})
    ready = all(s["state"] == "done" for s in steps if s["required"])
    return {"steps": steps, "ready": ready, "complete": all(s["state"] == "done" for s in steps),
            "schedules": schedules(state, task)}


def schedules(state: dict | None = None, task: dict | None = None) -> list[dict]:
    state = state or load()
    out = []
    task = task or collector_task()
    if task:
        out.append({"id": "collector_schedule", "label": "Collection", "kind": "windows", "next": task["next_run"],
                    "last": task["last_run"], "note": "plus a random start delay of up to 2 hours, never before 7 AM"})
    for sid, s in state.get("schedules", {}).items():
        if s.get("kind") == "windows" and task:
            continue
        nxt = None
        try:
            nxt = next_cron(s["cron"]).isoformat(timespec="minutes") if s.get("cron") else None
        except ValueError:
            pass
        out.append({"id": sid, "label": s.get("label", sid), "kind": s.get("kind", "claude"), "next": nxt,
                    "cron": s.get("cron"), "note": s.get("note", ""), "task": s.get("task")})
    order = {sid: i for i, sid in enumerate(STEP_IDS)}
    return sorted(out, key=lambda s: order.get(s["id"], 99))


# ---- cron (5 fields: minute hour day-of-month month day-of-week; local time) ----

def _field(spec: str, lo: int, hi: int) -> set[int]:
    vals: set[int] = set()
    for part in spec.split(","):
        rng, _, step = part.partition("/")
        if rng == "*":
            a, b = lo, hi
        elif "-" in rng:
            a, b = (int(x) for x in rng.split("-"))
        else:
            a = b = int(rng)
            if step:
                b = hi
        if not (lo <= a <= hi and lo <= b <= hi):
            raise ValueError(f"cron value out of range: {part}")
        vals.update(range(a, b + 1, int(step) if step else 1))
    return vals


def next_cron(expr: str, after: datetime | None = None) -> datetime:
    """The next time a cron expression fires after `after` (default: now)."""
    parts = expr.split()
    if len(parts) != 5:
        raise ValueError(f"cron needs 5 fields: {expr!r}")
    mins, hours, doms, mons = (_field(p, lo, hi) for p, (lo, hi) in zip(parts[:4], [(0, 59), (0, 23), (1, 31), (1, 12)]))
    dows = {d % 7 for d in _field(parts[4], 0, 7)}  # 0 and 7 are both Sunday
    t = (after or datetime.now()).replace(second=0, microsecond=0) + timedelta(minutes=1)
    for _ in range(60 * 24 * 370):
        if (t.month in mons and t.hour in hours and t.minute in mins
                and (t.day in doms if parts[2] != "*" else True)
                and ((t.isoweekday() % 7) in dows if parts[4] != "*" else True)):
            return t
        t += timedelta(minutes=1)
    raise ValueError(f"cron never fires: {expr!r}")
