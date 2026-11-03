"""SQLite store for jobs: dedupe across sources, statuses, and history.

One row per real job (deduped by company + normalized title), with every source
that listed it in `sources`. Every status change is kept in `events`, which is
the paper trail for the tracker and the unemployment work-search log.

Statuses: new, interested, applying, applied, interviewing, offer, rejected,
ghosted, dismissed.
"""

from __future__ import annotations

import json
import re
import sqlite3
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "guard"))
from runlog import RunLog  # noqa: E402

DB_PATH = Path(__file__).resolve().parent.parent / "state" / "jobs.db"

STATUSES = ("new", "interested", "applying", "applied", "interviewing",
            "offer", "rejected", "ghosted", "dismissed")
MARKED = ("interested", "applying", "applied", "interviewing", "offer")  # the person picked these
CLOSED = ("rejected", "ghosted", "dismissed")

# Company one-pagers: written for every marked job, and for new jobs scoring this high.
PROFILE_MIN_SCORE = 60
PROFILE_MAX_AGE_DAYS = 30
BACKFILL_MIN_SCORE = 45  # weak fits aren't worth more research unless the person marks them


def wants_profile(job: dict) -> bool:
    return job["status"] in MARKED or ((job.get("analysis") or {}).get("score") or 0) >= PROFILE_MIN_SCORE

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id              INTEGER PRIMARY KEY,
    dedupe_key      TEXT UNIQUE NOT NULL,
    title           TEXT NOT NULL,
    company         TEXT NOT NULL,
    location        TEXT,
    workplace       TEXT,            -- remote / hybrid / onsite
    employment_type TEXT,            -- full-time / contract / ...
    salary_min      INTEGER,
    salary_max      INTEGER,
    salary_text     TEXT,
    posted_on       TEXT,            -- earliest posting date seen (YYYY-MM-DD)
    applicants      TEXT,
    description     TEXT,
    first_seen      TEXT NOT NULL,
    last_seen       TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'new',
    status_changed  TEXT,
    analysis        TEXT,            -- JSON: Claude's review (score, fit, notes, ...)
    company_info    TEXT,            -- JSON: what they do, size, funding, sentiment
    flags           TEXT,            -- JSON list of red/yellow flags
    gaps            TEXT             -- JSON list of {what, why}: research still to do; empty = complete
);
CREATE TABLE IF NOT EXISTS documents (
    id      INTEGER PRIMARY KEY,
    job_id  INTEGER NOT NULL REFERENCES jobs(id),
    kind    TEXT NOT NULL,            -- resume / cover_letter
    path    TEXT NOT NULL,            -- folder under the kit, e.g. resumes/25-acme-group-pm
    status  TEXT NOT NULL DEFAULT 'draft',   -- draft / final / sent
    summary TEXT,                     -- one or two lines: what was tailored
    created TEXT NOT NULL,
    updated TEXT NOT NULL,
    UNIQUE(job_id, kind)
);
CREATE TABLE IF NOT EXISTS companies (
    key     TEXT PRIMARY KEY,         -- normalize_company(name)
    name    TEXT NOT NULL,
    profile TEXT NOT NULL,            -- JSON one-pager (see PLAYBOOK section 7)
    updated TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sources (
    job_id    INTEGER NOT NULL REFERENCES jobs(id),
    source    TEXT NOT NULL,          -- linkedin / indeed / ziprecruiter / dice / ats
    source_id TEXT NOT NULL,
    url       TEXT,
    posted_on TEXT,
    seen_at   TEXT NOT NULL,
    UNIQUE(source, source_id)
);
CREATE TABLE IF NOT EXISTS seen (
    source     TEXT NOT NULL,         -- every listing any search returned, saved or not
    source_id  TEXT NOT NULL,
    title      TEXT,
    company    TEXT,
    first_seen TEXT NOT NULL,         -- YYYY-MM-DD
    last_seen  TEXT NOT NULL,
    days_seen  INTEGER NOT NULL DEFAULT 1,
    decision   TEXT,                  -- null = not reviewed yet / saved / skipped
    reason     TEXT,
    PRIMARY KEY (source, source_id)
);
CREATE TABLE IF NOT EXISTS listings (
    source       TEXT NOT NULL,       -- details the background collector fetched, waiting for review
    source_id    TEXT NOT NULL,
    title        TEXT,
    company      TEXT,
    location     TEXT,
    workplace    TEXT,
    posted_on    TEXT,
    salary_text  TEXT,
    applicants   TEXT,
    url          TEXT,
    query        TEXT,                -- the search or board that found it
    description  TEXT,
    collected_at TEXT NOT NULL,
    PRIMARY KEY (source, source_id)
);
CREATE TABLE IF NOT EXISTS runs (
    id       INTEGER PRIMARY KEY,
    kind     TEXT NOT NULL,           -- collect / review
    started  TEXT NOT NULL,
    finished TEXT,
    status   TEXT NOT NULL,           -- running / done / stopped / failed
    stats    TEXT,                    -- JSON counts
    summary  TEXT                     -- one or two plain sentences
);
CREATE TABLE IF NOT EXISTS events (
    id      INTEGER PRIMARY KEY,
    job_id  INTEGER NOT NULL REFERENCES jobs(id),
    at      TEXT NOT NULL,
    kind    TEXT NOT NULL,            -- found / status / note / analysis
    detail  TEXT
);
"""

_COMPANY_NOISE = re.compile(
    r"\b(inc|llc|ltd|corp|corporation|co|company|the|us|usa)\b\.?", re.I)
_TITLE_ALIASES = [
    (r"\bsr\.?\b", "senior"), (r"\bmgr\b", "manager"), (r"\bpm\b", "product manager"),
    (r"\bdir\.?\b", "director"), (r"\bvp\b", "vice president"),
]


def normalize_company(name: str) -> str:
    s = (name or "").lower().replace("&", "and")
    s = re.sub(r"\btechnology\b", "tech", s)
    s = _COMPANY_NOISE.sub(" ", s)
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", s).split())


def normalize_title(title: str) -> str:
    s = (title or "").lower()
    s = re.sub(r"\(.*?\)", lambda m: " " + m.group(0)[1:-1] + " ", s)
    for pat, rep in _TITLE_ALIASES:
        s = re.sub(pat, rep, s)
    s = re.sub(r"\b(remote|hybrid|onsite|on-site|united states|us)\b", " ", s)
    s = s.replace("director of product management", "director product management")
    s = s.replace("director, product management", "director product management")
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", s).split())


def dedupe_key(company: str, title: str) -> str:
    return f"{normalize_company(company)}|{normalize_title(title)}"


# Indeed connector ids (JOBSEARCH_100012 …) are per-search counters, not stable job ids:
# the same number can mean a different job tomorrow.
_UNSTABLE_ID = re.compile(r"^JOBSEARCH_\d+$")


def stable_id(source_id, company: str | None = None, title: str | None = None) -> str:
    """The source id, or company + title when the source's ids aren't stable."""
    sid = str(source_id)
    if _UNSTABLE_ID.match(sid) and company and title:
        return "ct:" + dedupe_key(company, title)
    return sid


class Store:
    def __init__(self, path: Path = DB_PATH, log=None):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)
        cols = {r["name"] for r in self.db.execute("PRAGMA table_info(jobs)")}
        if "gaps" not in cols:  # databases created before gaps existed
            self.db.execute("ALTER TABLE jobs ADD COLUMN gaps TEXT")
        self.log = log or RunLog("store")

    # ---- writes ----

    def upsert(self, job: dict) -> tuple[int, bool]:
        """Insert or merge a job. Returns (job_id, is_new).

        `job` keys: title, company, and optionally location, workplace,
        employment_type, salary_min/max/text, posted_on, applicants, description,
        analysis (dict), company_info (dict), flags (list), gaps (list of
        {what, why}; [] marks the job complete), and
        sources: [{source, source_id, url, posted_on}].

        Merging fills empty fields only, except that a longer description replaces
        a shorter one (a full posting beats a search card), and `overwrite: true`
        lets every field given replace what's stored (corrections, backfills).
        """
        now = datetime.now().isoformat(timespec="seconds")
        key = dedupe_key(job["company"], job["title"])
        row = self.db.execute("SELECT * FROM jobs WHERE dedupe_key=?", (key,)).fetchone()
        fields = ("location", "workplace", "employment_type", "salary_min", "salary_max",
                  "salary_text", "applicants", "description")
        if row is None:
            cur = self.db.execute(
                f"INSERT INTO jobs (dedupe_key, title, company, first_seen, last_seen, posted_on, "
                f"analysis, company_info, flags, gaps, {', '.join(fields)}) "
                f"VALUES (?,?,?,?,?,?,?,?,?,?,{','.join('?' * len(fields))})",
                (key, job["title"], job["company"], now, now, job.get("posted_on"),
                 _j(job.get("analysis")), _j(job.get("company_info")), _j(job.get("flags")),
                 _j(job.get("gaps")), *[job.get(f) for f in fields]))
            job_id, is_new = cur.lastrowid, True
            self._event(job_id, "found", f"{job['title']} @ {job['company']}")
            self.log("new", f"{job['title']} @ {job['company']}", job_id=job_id)
        else:
            job_id, is_new = row["id"], False
            replace = bool(job.get("overwrite"))
            updates = {f: job[f] for f in fields if job.get(f) and (replace or not row[f])}
            if job.get("description") and len(job["description"]) > len(row["description"] or ""):
                updates["description"] = job["description"]
            # keep the EARLIEST posting date any source reports (ghost-listing signal)
            if job.get("posted_on") and (not row["posted_on"] or job["posted_on"] < row["posted_on"]):
                updates["posted_on"] = job["posted_on"]
            for f in ("analysis", "company_info", "flags", "gaps"):
                if job.get(f) is not None:
                    updates[f] = _j(job[f])
            updates["last_seen"] = now
            sets = ", ".join(f"{k}=?" for k in updates)
            self.db.execute(f"UPDATE jobs SET {sets} WHERE id=?", (*updates.values(), job_id))
            self.log("merged", f"{job['title']} @ {job['company']} (already known)", job_id=job_id)
        for s in job.get("sources", []):
            sid = stable_id(s["source_id"], job["company"], job["title"])
            inserted = self.db.execute(
                "INSERT OR IGNORE INTO sources (job_id, source, source_id, url, posted_on, seen_at) "
                "VALUES (?,?,?,?,?,?)",
                (job_id, s["source"], sid, s.get("url"), s.get("posted_on"), now)).rowcount
            if inserted and not is_new:
                self.log("dedupe", f"also listed on {s['source']}", job_id=job_id)
            if s["source"] != "company":  # the employer's own posting is research, not a listing a search found
                self._touch_seen(s["source"], sid, job["title"], job["company"], "saved")
        self.db.commit()
        return job_id, is_new

    def check_seen(self, items: list[dict]) -> list[dict]:
        """Record search results as seen and say what's already known about each.

        Each item needs source and source_id (title and company help matching).
        Adds `seen`: None if it's never come up before, else {first_seen,
        days_seen, decision, reason}; and `job_id`: the stored job it matches,
        by source id or by company + title (catches the same job on another site).
        """
        for it in items:
            src = it["source"]
            sid = it["source_id"] = stable_id(it["source_id"], it.get("company"), it.get("title"))
            prior = self.db.execute("SELECT first_seen, days_seen, decision, reason FROM seen "
                                    "WHERE source=? AND source_id=?", (src, sid)).fetchone()
            it["seen"] = dict(prior) if prior else None
            hit = self.db.execute("SELECT job_id FROM sources WHERE source=? AND source_id=?",
                                  (src, sid)).fetchone()
            if not hit and it.get("company") and it.get("title"):
                hit = self.db.execute("SELECT id AS job_id FROM jobs WHERE dedupe_key=?",
                                      (dedupe_key(it["company"], it["title"]),)).fetchone()
            it["job_id"] = hit["job_id"] if hit else None
            self._touch_seen(src, sid, it.get("title"), it.get("company"))
        self.db.commit()
        new = sum(1 for it in items if not it["seen"] and not it["job_id"])
        self.log("seen", f"{len(items)} listings, {new} new", new=new)
        return items

    def mark_seen(self, source: str, source_id: str, decision: str, reason: str = "",
                  title: str | None = None, company: str | None = None) -> None:
        """Record a triage decision ("skipped" + why) so the listing isn't reviewed again."""
        source_id = stable_id(source_id, company, title)
        self._touch_seen(source, source_id, title, company, decision, reason)
        self.db.commit()
        self.log("triage", f"{source}:{source_id} {decision}" + (f": {reason}" if reason else ""))

    def seen_stats(self, days: int = 7) -> dict:
        """How many new listings each source turned up per day: is the net wide enough?"""
        rows = self.db.execute(
            "SELECT source, first_seen, COUNT(*) AS n FROM seen "
            "WHERE first_seen >= date('now', 'localtime', ?) GROUP BY source, first_seen ORDER BY first_seen",
            (f"-{int(days)} days",)).fetchall()
        by_source: dict = {}
        for r in rows:
            by_source.setdefault(r["source"], {})[r["first_seen"]] = r["n"]
        totals = self.db.execute(
            "SELECT COUNT(*) AS seen, SUM(decision='saved') AS saved, SUM(decision='skipped') AS skipped, "
            "SUM(decision IS NULL) AS unreviewed FROM seen").fetchone()
        return {"new_per_day": by_source, "totals": dict(totals)}

    def save_listing(self, item: dict, query: str = "") -> None:
        """Keep the collected details of a listing until Claude reviews it."""
        cols = ("title", "company", "location", "workplace", "posted_on", "salary_text",
                "applicants", "url", "description")
        self.db.execute(
            f"INSERT INTO listings (source, source_id, query, collected_at, {', '.join(cols)}) "
            f"VALUES (?,?,?,?,{','.join('?' * len(cols))}) ON CONFLICT(source, source_id) DO UPDATE SET "
            + ", ".join(f"{c} = COALESCE(excluded.{c}, {c})" for c in cols),
            (item["source"], stable_id(item["source_id"], item.get("company"), item.get("title")), query,
             datetime.now().isoformat(timespec="seconds"),
             *[item.get(c) for c in cols]))
        self.db.commit()

    def review_queue(self, limit: int = 40, description_chars: int = 2500) -> dict:
        """Listings seen but not yet reviewed (no saved/skipped decision), newest first,
        with whatever details the collector kept. Listings the person rescued from the
        filtered-out list come first, with their note in `reason`."""
        total = self.db.execute("SELECT COUNT(*) FROM seen WHERE decision IS NULL OR decision='rescue'").fetchone()[0]
        rows = self.db.execute(
            "SELECT s.source, s.source_id, s.title, s.company, s.first_seen, s.days_seen, s.decision, s.reason, "
            "l.location, l.workplace, l.posted_on, l.salary_text, l.applicants, l.url, l.query, l.description "
            "FROM seen s LEFT JOIN listings l USING (source, source_id) WHERE s.decision IS NULL OR s.decision='rescue' "
            "ORDER BY s.decision IS NULL, s.first_seen DESC, l.posted_on DESC LIMIT ?", (int(limit),)).fetchall()
        items = []
        for r in rows:
            d = {k: v for k, v in dict(r).items() if v is not None}
            if d.get("description"):
                d["description"] = d["description"][:description_chars]
            hit = self.db.execute("SELECT id FROM jobs WHERE dedupe_key=?",
                                  (dedupe_key(d.get("company", ""), d.get("title", "")),)).fetchone()
            d["job_id"] = hit["id"] if hit else None
            items.append(d)
        return {"unreviewed": total, "items": items}

    def start_run(self, kind: str) -> int:
        cur = self.db.execute("INSERT INTO runs (kind, started, status) VALUES (?,?,?)",
                              (kind, datetime.now().isoformat(timespec="seconds"), "running"))
        self.db.commit()
        return cur.lastrowid

    def finish_run(self, run_id: int, status: str, stats: dict | None = None, summary: str = "") -> None:
        self.db.execute("UPDATE runs SET finished=?, status=?, stats=?, summary=? WHERE id=?",
                        (datetime.now().isoformat(timespec="seconds"), status, _j(stats), summary, run_id))
        self.db.commit()

    def runs(self, limit: int = 10, kind: str | None = None) -> list[dict]:
        sql = "SELECT * FROM runs" + (" WHERE kind=?" if kind else "") + " ORDER BY id DESC LIMIT ?"
        out = []
        for r in self.db.execute(sql, ((kind,) if kind else ()) + (int(limit),)):
            d = dict(r)
            d["stats"] = json.loads(d["stats"]) if d["stats"] else None
            out.append(d)
        return out

    def dashboard(self, days: int = 14) -> dict:
        """Numbers for the app's Home page: daily intake, where listings come from, the
        pipeline, and how much work the system has done."""
        since = (date.today() - timedelta(days=int(days) - 1)).isoformat()
        one = lambda sql, *a: self.db.execute(sql, a).fetchone()[0] or 0  # noqa: E731
        per_day = [dict(r) for r in self.db.execute(
            "SELECT first_seen AS day, COUNT(*) AS found, SUM(decision='saved') AS kept, "
            "SUM(decision='skipped') AS filtered, SUM(decision IS NULL OR decision='rescue') AS waiting "
            "FROM seen WHERE first_seen >= ? GROUP BY first_seen ORDER BY first_seen", (since,))]
        sources: dict = {}
        for r in self.db.execute("SELECT source, COUNT(*) AS n FROM seen GROUP BY source"):
            name = "company job boards" if r["source"].startswith("ats:") else r["source"]
            sources[name] = sources.get(name, 0) + r["n"]
        status = {r["status"]: r["n"] for r in self.db.execute("SELECT status, COUNT(*) AS n FROM jobs GROUP BY status")}
        strong = sum(1 for j in self.db.execute("SELECT analysis FROM jobs WHERE status='new'")
                     if j["analysis"] and (json.loads(j["analysis"]).get("score") or 0) >= 70)
        work = {"linkedin_searches": 0, "linkedin_postings": 0, "boards": 0, "connector_searches": 0}
        for r in self.runs(10000):
            for key in work:
                work[key] += int((r["stats"] or {}).get(key) or 0)
        return {
            "per_day": per_day, "sources": sources, "status": status, "strong": strong,
            "totals": {"found": one("SELECT COUNT(*) FROM seen"), "kept": one("SELECT COUNT(*) FROM seen WHERE decision='saved'"),
                       "filtered": one("SELECT COUNT(*) FROM seen WHERE decision='skipped'"),
                       "jobs": one("SELECT COUNT(*) FROM jobs")},
            "work": {**work,
                     "collections": one("SELECT COUNT(*) FROM runs WHERE kind='collect'"),
                     "reviews": one("SELECT COUNT(*) FROM runs WHERE kind='review'"),
                     "companies_researched": one("SELECT COUNT(DISTINCT company) FROM jobs WHERE company_info IS NOT NULL"),
                     "one_pagers": one("SELECT COUNT(*) FROM companies"),
                     "drafts": one("SELECT COUNT(*) FROM documents"),
                     "since": (self.db.execute("SELECT MIN(started) FROM runs").fetchone()[0] or "")[:10]},
        }

    def _touch_seen(self, source, source_id, title=None, company=None, decision=None, reason=None):
        today = date.today().isoformat()
        self.db.execute(
            "INSERT INTO seen (source, source_id, title, company, first_seen, last_seen, decision, reason) "
            "VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(source, source_id) DO UPDATE SET "
            "days_seen = days_seen + (last_seen < excluded.last_seen), last_seen = excluded.last_seen, "
            "title = COALESCE(title, excluded.title), company = COALESCE(company, excluded.company), "
            "decision = COALESCE(excluded.decision, decision), reason = COALESCE(excluded.reason, reason)",
            (source, str(source_id), title, company, today, today, decision, reason or None))

    def set_status(self, job_id: int, status: str, note: str = "") -> None:
        if status not in STATUSES:
            raise ValueError(f"unknown status {status!r}")
        now = datetime.now().isoformat(timespec="seconds")
        self.db.execute("UPDATE jobs SET status=?, status_changed=? WHERE id=?", (status, now, job_id))
        self._event(job_id, "status", f"{status}" + (f": {note}" if note else ""))
        self.db.commit()
        self.log("status", f"job {job_id} -> {status}", job_id=job_id, note=note)

    def add_note(self, job_id: int, note: str) -> None:
        self._event(job_id, "note", note)
        self.db.commit()

    # ---- tailored documents (resume and cover letter drafts) ----

    def save_document(self, job_id: int, kind: str, path: str, summary: str = "", status: str = "draft") -> None:
        now = datetime.now().isoformat(timespec="seconds")
        existed = self.db.execute("SELECT 1 FROM documents WHERE job_id=? AND kind=?", (job_id, kind)).fetchone()
        self.db.execute(
            "INSERT INTO documents (job_id, kind, path, status, summary, created, updated) VALUES (?,?,?,?,?,?,?) "
            "ON CONFLICT(job_id, kind) DO UPDATE SET path=excluded.path, status=excluded.status, "
            "summary=excluded.summary, updated=excluded.updated",
            (job_id, kind, path, status, summary, now, now))
        label = kind.replace("_", " ")
        self._event(job_id, "document", f"{label} {'revised' if existed else 'drafted'}: {path}")
        self.db.commit()
        self.log("document", f"job {job_id} {label} {'revised' if existed else 'drafted'}", job_id=job_id, path=path)

    def set_document_status(self, job_id: int, kind: str, status: str) -> None:
        if status not in ("draft", "final", "sent"):
            raise ValueError(f"unknown document status {status!r}")
        n = self.db.execute("UPDATE documents SET status=?, updated=? WHERE job_id=? AND kind=?",
                            (status, datetime.now().isoformat(timespec="seconds"), job_id, kind)).rowcount
        if not n:
            raise KeyError(f"job {job_id} has no {kind}")
        self._event(job_id, "document", f"{kind.replace('_', ' ')} marked {status}")
        self.db.commit()

    def documents(self) -> list[dict]:
        return [dict(r) for r in self.db.execute(
            "SELECT d.*, j.title, j.company, j.status AS job_status FROM documents d JOIN jobs j ON j.id = d.job_id "
            "ORDER BY d.updated DESC")]

    def drafts_pending(self, kind: str = "resume") -> list[dict]:
        """Jobs the person marked interested (or applying) that don't have this draft yet, oldest mark first."""
        rows = self.db.execute(
            "SELECT j.id FROM jobs j WHERE j.status IN ('interested', 'applying') AND NOT EXISTS "
            "(SELECT 1 FROM documents d WHERE d.job_id = j.id AND d.kind = ?) ORDER BY j.status_changed", (kind,))
        ids = [r["id"] for r in rows]
        return [j for j in self.jobs() if j["id"] in ids]

    # ---- audit: everything the collector saw, and what happened to it ----

    def audit(self, days: int = 7, decision: str | None = None, limit: int = 300) -> dict:
        """Listings first seen in the last `days`, with their fate: saved (and the job), skipped
        (and why), rescued, or waiting for review. Plus per-day counts for the funnel."""
        since = (date.today() - timedelta(days=int(days) - 1)).isoformat()
        where, args = "s.first_seen >= ?", [since]
        if decision == "waiting":
            where += " AND s.decision IS NULL"
        elif decision:
            where += " AND s.decision = ?"
            args.append(decision)
        rows = self.db.execute(
            f"SELECT s.source, s.source_id, s.title, s.company, s.first_seen, s.last_seen, s.days_seen, "
            f"s.decision, s.reason, l.location, l.workplace, l.salary_text, l.posted_on, l.url, l.query, "
            f"(SELECT job_id FROM sources x WHERE x.source = s.source AND x.source_id = s.source_id) AS job_id "
            f"FROM seen s LEFT JOIN listings l USING (source, source_id) WHERE {where} "
            f"ORDER BY s.first_seen DESC, s.company LIMIT ?", (*args, int(limit))).fetchall()
        per_day = self.db.execute(
            "SELECT first_seen AS day, COUNT(*) AS seen, SUM(decision='saved') AS saved, "
            "SUM(decision='skipped') AS skipped, SUM(decision='rescue') AS rescued, SUM(decision IS NULL) AS waiting "
            "FROM seen WHERE first_seen >= ? GROUP BY first_seen ORDER BY first_seen DESC", (since,)).fetchall()
        return {"since": since, "per_day": [dict(r) for r in per_day], "items": [dict(r) for r in rows]}

    def rescue(self, source: str, source_id: str, note: str = "") -> None:
        """The person wants a filtered-out listing looked at again. The next review scores it
        and treats the note as tuning feedback."""
        row = self.db.execute("SELECT decision, reason, title, company FROM seen WHERE source=? AND source_id=?",
                              (source, source_id)).fetchone()
        if row is None:
            raise KeyError(f"{source}:{source_id} was never seen")
        was = f"was {row['decision']}" + (f": {row['reason']}" if row["reason"] else "") if row["decision"] else "was waiting"
        reason = f"rescued by you ({was})" + (f". Your note: {note}" if note else "")
        self.db.execute("UPDATE seen SET decision='rescue', reason=? WHERE source=? AND source_id=?",
                        (reason, source, source_id))
        self.db.commit()
        self.log("rescue", f"{row['title']} @ {row['company']}", note=note)

    def save_company(self, name: str, profile: dict) -> str:
        """Insert or replace a company's one-pager. Returns its key."""
        key = normalize_company(name)
        self.db.execute(
            "INSERT INTO companies (key, name, profile, updated) VALUES (?,?,?,?) "
            "ON CONFLICT(key) DO UPDATE SET name=excluded.name, profile=excluded.profile, updated=excluded.updated",
            (key, name, json.dumps(profile), datetime.now().isoformat(timespec="seconds")))
        self.db.commit()
        self.log("company", f"one-pager saved: {name}")
        return key

    def companies(self) -> dict:
        """Every one-pager, keyed by normalized company name."""
        return {r["key"]: {"name": r["name"], "updated": r["updated"], **json.loads(r["profile"])}
                for r in self.db.execute("SELECT * FROM companies")}

    def company(self, name: str) -> dict | None:
        return self.companies().get(normalize_company(name))

    def incomplete(self, limit: int = 20) -> list[dict]:
        """Open jobs with research still to do, most worth finishing first: jobs the person
        marked (interested and later) before the rest, then by score. A job counts if it has
        gaps, or it qualifies for a company one-pager that's missing or stale. Unmarked jobs
        under BACKFILL_MIN_SCORE are left out."""
        profiles = self.companies()
        stale = (date.today() - timedelta(days=PROFILE_MAX_AGE_DAYS)).isoformat()
        out = []
        for j in self.jobs():
            score = (j["analysis"] or {}).get("score") or 0
            if j["status"] in CLOSED or (j["status"] not in MARKED and score < BACKFILL_MIN_SCORE):
                continue
            gaps = list(j["gaps"] or [])
            p = profiles.get(normalize_company(j["company"]))
            if wants_profile(j) and not any(g.get("what") == "company_profile" for g in gaps):
                if not p:
                    gaps.append({"what": "company_profile", "why": "qualifies for a one-pager; none written yet"})
                elif p["updated"][:10] < stale:
                    gaps.append({"what": "company_profile", "why": f"one-pager is from {p['updated'][:10]}; refresh it"})
            if gaps:
                out.append({"id": j["id"], "title": j["title"], "company": j["company"], "status": j["status"],
                            "score": (j["analysis"] or {}).get("score"), "gaps": gaps,
                            "sources": j["sources"], "has_description": bool(j["description"])})
        marked = lambda x: x["status"] in MARKED  # noqa: E731
        out.sort(key=lambda x: (not marked(x), -(x["score"] or 0)))
        return out[:limit]

    # ---- reads ----

    def jobs(self) -> list[dict]:
        out = []
        for r in self.db.execute("SELECT * FROM jobs ORDER BY id"):
            d = dict(r)
            for f in ("analysis", "company_info", "flags", "gaps"):
                d[f] = json.loads(d[f]) if d[f] else None
            d["company_key"] = normalize_company(d["company"])
            d["documents"] = [dict(x) for x in self.db.execute(
                "SELECT kind, path, status, summary, created, updated FROM documents WHERE job_id=?", (r["id"],))]
            d["sources"] = [dict(s) for s in self.db.execute(
                "SELECT source, source_id, url, posted_on FROM sources WHERE job_id=?", (r["id"],))]
            d["events"] = [dict(e) for e in self.db.execute(
                "SELECT at, kind, detail FROM events WHERE job_id=? ORDER BY id", (r["id"],))]
            d["age_days"] = (date.today() - date.fromisoformat(d["posted_on"])).days if d["posted_on"] else None
            out.append(d)
        return out

    def _event(self, job_id, kind, detail):
        self.db.execute("INSERT INTO events (job_id, at, kind, detail) VALUES (?,?,?,?)",
                        (job_id, datetime.now().isoformat(timespec="seconds"), kind, detail))


def _j(v):
    return None if v is None else json.dumps(v)
