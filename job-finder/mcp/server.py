"""job-finder MCP server (stdio, stdlib only).

Exposes the guard-protected collectors and the job store as MCP tools, so
Claude can use them from any session. Same guard, caps, and logs as the
scripts. Nothing here can apply to a job, submit a form, or contact anyone.

stdout carries the MCP protocol only; all logging goes to state/logs/.
"""

from __future__ import annotations

import json
import sys
import traceback
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for sub in ("guard", "store", "collectors"):
    sys.path.insert(0, str(ROOT / sub))

import ats  # noqa: E402
import linkedin  # noqa: E402
from db import STATUSES, Store  # noqa: E402
from polite import Guard, GuardRefused  # noqa: E402
from runlog import LOG_DIR, RunLog  # noqa: E402
from settings import search_defaults  # noqa: E402

PROTOCOL_VERSION = "2025-06-18"
log = RunLog("mcp", echo=False)


def guard():
    return Guard(log=RunLog("guard", echo=False))


def store():
    return Store(log=RunLog("store", echo=False))


SLOW = ("Requests are paced by the guard like a person browsing, so this can take "
        "1–5 minutes per call. Capped per day; refuses during cooldowns and at night.")
SEEN = ("Each result carries `seen` (null = never come up before; else first_seen, days_seen, and any "
        "triage decision) and `job_id` (already in the store). Skip what's been seen; spend effort on new ones.")
SEEN_ITEM = {"type": "object", "properties": {
    "source": {"type": "string", "description": "linkedin / indeed / ziprecruiter / dice / ats:greenhouse …"},
    "source_id": {"type": "string"}, "title": {"type": "string"}, "company": {"type": "string"},
    "reason": {"type": "string"}}, "required": ["source", "source_id"]}


def record(items: list[dict], query: str) -> list[dict]:
    """Mark results seen and keep details for anything still waiting for review."""
    s = store()
    s.check_seen(items)
    for i in items:
        if not i["job_id"] and not (i["seen"] or {}).get("decision"):
            s.save_listing(i, query)
    return items


def with_counts(items: list[dict]) -> dict:
    new = sum(1 for i in items if not i["seen"] and not i["job_id"])
    return {"new": new, "already_seen": len(items) - new, "results": items}

TOOLS = [
    {
        "name": "guard_status",
        "description": "Today's request counts, daily caps, and any cooldowns per site. Call this before a batch of LinkedIn requests.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "linkedin_search",
        "description": ("Search LinkedIn jobs through the logged-out guest feed (one page, ~10 results). LinkedIn "
                        "matches loosely across the whole posting, so a few broad searches beat many title variants. "
                        "If most of a page is new, the next page (start += 10) is usually worth it. " + SEEN + " " + SLOW),
        "inputSchema": {"type": "object", "properties": {
            "keywords": {"type": "string"},
            "location": {"type": "string", "default": "United States"},
            "workplace": {"type": "string", "enum": ["remote", "hybrid", "onsite"]},
            "posted_within_days": {"type": "integer", "minimum": 1, "maximum": 30},
            "start": {"type": "integer", "default": 0, "description": "Paging offset. Keep paging minimal."},
        }, "required": ["keywords"]},
    },
    {
        "name": "linkedin_posting",
        "description": "Full LinkedIn posting by job id (description, salary, applicants, seniority) through the logged-out guest feed. " + SLOW,
        "inputSchema": {"type": "object", "properties": {"job_id": {"type": "string"}}, "required": ["job_id"]},
    },
    {
        "name": "ats_jobs",
        "description": ("Open jobs from a company's public job board (Greenhouse, Lever, or Ashby) by board slug. The whole "
                        "board is one request; titles are filtered loosely by the 'Title net' words in profile/search.md "
                        "unless you pass keyword. found=false means the company doesn't use that platform. " + SEEN),
        "inputSchema": {"type": "object", "properties": {
            "platform": {"type": "string", "enum": ["greenhouse", "lever", "ashby"]},
            "company_slug": {"type": "string"},
            "keyword": {"type": "string", "description": "Title terms separated by | (any match, loose). '*' returns every job."},
            "include_description": {"type": "boolean", "default": False},
        }, "required": ["platform", "company_slug"]},
    },
    {
        "name": "jobs_list",
        "description": "Jobs in the local job store with status, score, analysis, sources, and history. Use this to avoid resurfacing jobs already reviewed, applied to, or dismissed.",
        "inputSchema": {"type": "object", "properties": {
            "status": {"type": "string", "enum": list(STATUSES)},
            "min_score": {"type": "integer"},
            "include_description": {"type": "boolean", "default": False},
        }},
    },
    {
        "name": "job_save",
        "description": ("Insert or merge a reviewed job into the store (deduped by company + title; extra sources are merged). "
                        "Fields: title, company, location, workplace, employment_type, salary_min, salary_max, salary_text, "
                        "posted_on (YYYY-MM-DD), applicants, description, sources [{source, source_id, url, posted_on}], "
                        "analysis {score, fit, lean, summary, why[], concerns[], level, resume, ai_forward}, "
                        "company_info {what, size, funding, sentiment, news, website, data_notes}, flags [{level: red|yellow, text}], "
                        "gaps [{what, why}]: research not done yet (description, employer_posting, salary, sentiment, news, "
                        "company_profile), so the next review finishes it; pass [] once complete. The employer's own posting "
                        "goes in sources as {source: 'company', source_id: <its job id or url>, url}. Merging fills empty fields "
                        "and replaces a shorter description; overwrite: true replaces every field given."),
        "inputSchema": {"type": "object", "properties": {"job": {"type": "object"}}, "required": ["job"]},
    },
    {
        "name": "jobs_incomplete",
        "description": ("Open jobs with research still to do, most worth finishing first (jobs the person marked "
                        "interested or later, then by score). Each lists its gaps, including a missing or stale company "
                        "one-pager. Start of the daily review's backfill step."),
        "inputSchema": {"type": "object", "properties": {"limit": {"type": "integer", "default": 20}}},
    },
    {
        "name": "company_get",
        "description": "A company's one-pager, if one has been written (null otherwise). Check before researching a company again.",
        "inputSchema": {"type": "object", "properties": {"company": {"type": "string"}}, "required": ["company"]},
    },
    {
        "name": "company_save",
        "description": ("Save (or replace) a company one-pager, shown in the report from every job at that company. "
                        "profile: {tagline, website, careers, overview, sections [{heading, text?, bullets[]?}], "
                        "news [{date, text, url}], for_you [], questions [], sources [{title, url}]}. "
                        "See PLAYBOOK section 7 for what goes in it."),
        "inputSchema": {"type": "object", "properties": {
            "company": {"type": "string"}, "profile": {"type": "object"}}, "required": ["company", "profile"]},
    },
    {
        "name": "job_set_status",
        "description": "Change a job's status (recorded in its history). This only updates the local tracker; it never applies anywhere.",
        "inputSchema": {"type": "object", "properties": {
            "job_id": {"type": "integer"},
            "status": {"type": "string", "enum": list(STATUSES)},
            "note": {"type": "string"},
        }, "required": ["job_id", "status"]},
    },
    {
        "name": "seen_check",
        "description": ("Record listings from the connector searches (Indeed, ZipRecruiter, Dice) as seen and annotate them, "
                        "the same way linkedin_search and ats_jobs do. Call it right after each connector search. " + SEEN),
        "inputSchema": {"type": "object", "properties": {"items": {"type": "array", "items": SEEN_ITEM}},
                        "required": ["items"]},
    },
    {
        "name": "seen_skip",
        "description": ("Mark listings triaged out (wrong field, wrong level, deal-breaker) with a short reason, so later runs "
                        "don't review them again. Not for jobs worth showing: save those with job_save, even with a low score."),
        "inputSchema": {"type": "object", "properties": {"items": {"type": "array", "items": SEEN_ITEM}},
                        "required": ["items"]},
    },
    {
        "name": "seen_stats",
        "description": "New listings per source per day over the last N days, plus saved / skipped / unreviewed totals. Shows whether the net is wide enough.",
        "inputSchema": {"type": "object", "properties": {"days": {"type": "integer", "default": 7}}},
    },
    {
        "name": "review_queue",
        "description": ("Start of the daily review: listings the background collector found that haven't been reviewed "
                        "(no saved/skipped decision), newest first, with the details it kept (description, salary, "
                        "applicants), plus the latest collector and review runs. Every item must end up either saved "
                        "(job_save) or skipped (seen_skip)."),
        "inputSchema": {"type": "object", "properties": {
            "limit": {"type": "integer", "default": 40},
            "description_chars": {"type": "integer", "default": 2500}}},
    },
    {
        "name": "review_done",
        "description": ("End of the daily review: record what this review did, so the report shows it and tomorrow's "
                        "review knows. summary: two or three plain sentences for the person (top picks, anything odd)."),
        "inputSchema": {"type": "object", "properties": {
            "summary": {"type": "string"},
            "stats": {"type": "object", "description": "e.g. {reviewed, saved, skipped, connector_searches, top: [job ids]}"},
            "status": {"type": "string", "enum": ["done", "stopped"], "default": "done"}},
            "required": ["summary"]},
    },
    {
        "name": "log_tail",
        "description": "The last lines of today's job-finder log (requests, waits, refusals, pushback, parse warnings).",
        "inputSchema": {"type": "object", "properties": {"lines": {"type": "integer", "default": 40}}},
    },
]


def call_tool(name: str, args: dict):
    if name == "guard_status":
        return guard().status()
    if name == "linkedin_search":
        results = linkedin.search(guard(), **{k: v for k, v in args.items()
                                              if k in ("keywords", "location", "workplace", "posted_within_days", "start")})
        return with_counts(record(results, f"linkedin: {args['keywords']} | {args.get('location', 'United States')}"))
    if name == "linkedin_posting":
        detail = linkedin.posting(guard(), str(args["job_id"]))
        store().save_listing(detail)
        return detail
    if name == "ats_jobs":
        keyword = args.get("keyword") or search_defaults()["title_words"] or None
        if keyword == "*":
            keyword = None
        board = ats.jobs(guard(), args["platform"], args["company_slug"], keyword,
                         bool(args.get("include_description")))
        for j in board["jobs"]:
            j.setdefault("company", j["company_slug"])
        return {"found": board["found"], "total": board.get("total", 0), "title_filter": keyword,
                **with_counts(record(board["jobs"], f"{args['platform']}: {args['company_slug']}"))}
    if name == "seen_check":
        return with_counts(record(args["items"], "connector"))
    if name == "seen_skip":
        s = store()
        for i in args["items"]:
            s.mark_seen(i["source"], i["source_id"], "skipped", i.get("reason", ""), i.get("title"), i.get("company"))
        return {"skipped": len(args["items"])}
    if name == "seen_stats":
        return store().seen_stats(int(args.get("days", 7)))
    if name == "review_queue":
        s = store()
        q = s.review_queue(int(args.get("limit", 40)), int(args.get("description_chars", 2500)))
        return {"recent_runs": s.runs(4), **q}
    if name == "review_done":
        s = store()
        run_id = s.start_run("review")
        s.finish_run(run_id, args.get("status", "done"), args.get("stats"), args["summary"])
        return {"run_id": run_id}
    if name == "jobs_list":
        jobs = store().jobs()
        if args.get("status"):
            jobs = [j for j in jobs if j["status"] == args["status"]]
        if args.get("min_score") is not None:
            jobs = [j for j in jobs if (j.get("analysis") or {}).get("score", -1) >= args["min_score"]]
        if not args.get("include_description"):
            for j in jobs:
                j.pop("description", None)
        return jobs
    if name == "job_save":
        job_id, is_new = store().upsert(args["job"])
        return {"job_id": job_id, "new": is_new}
    if name == "jobs_incomplete":
        return store().incomplete(int(args.get("limit", 20)))
    if name == "company_get":
        return store().company(args["company"])
    if name == "company_save":
        return {"key": store().save_company(args["company"], args["profile"])}
    if name == "job_set_status":
        store().set_status(int(args["job_id"]), args["status"], args.get("note", ""))
        return {"ok": True}
    if name == "log_tail":
        path = LOG_DIR / f"{date.today().isoformat()}.log"
        lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
        return "\n".join(lines[-int(args.get("lines", 40)):]) or "(no log yet today)"
    raise KeyError(f"unknown tool {name!r}")


def handle(msg: dict):
    method, mid = msg.get("method"), msg.get("id")
    if method == "initialize":
        return {"protocolVersion": msg.get("params", {}).get("protocolVersion", PROTOCOL_VERSION),
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "job-finder", "version": "0.1.0"},
                "instructions": "Local job-search tools. Read-only collection behind a pacing guard; never applies to jobs."}
    if method == "ping":
        return {}
    if method == "tools/list":
        return {"tools": TOOLS}
    if method == "tools/call":
        name = msg["params"]["name"]
        args = msg["params"].get("arguments") or {}
        log("tool", name, args=json.dumps(args)[:300])
        try:
            result = call_tool(name, args)
            text = result if isinstance(result, str) else json.dumps(result, indent=1, default=str)
            log("tool_ok", name, chars=len(text))
            return {"content": [{"type": "text", "text": text}], "isError": False}
        except GuardRefused as e:
            log("tool_refused", f"{name}: {e}")
            return {"content": [{"type": "text", "text": f"Guard refused: {e}"}], "isError": True}
        except Exception as e:  # report tool errors to the caller, keep the server alive
            log("error", f"{name}: {e}", trace=traceback.format_exc()[-800:])
            return {"content": [{"type": "text", "text": f"Error in {name}: {e}"}], "isError": True}
    if mid is None:
        return None  # notification (e.g. notifications/initialized)
    raise LookupError(method)


def main():
    log("start", "job-finder MCP server")
    sys.stdin.reconfigure(encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        mid = msg.get("id")
        try:
            result = handle(msg)
            if mid is None:
                continue
            reply = {"jsonrpc": "2.0", "id": mid, "result": result}
        except LookupError as e:
            reply = {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"Method not found: {e}"}}
        except Exception as e:
            log("error", f"protocol: {e}")
            reply = {"jsonrpc": "2.0", "id": mid, "error": {"code": -32603, "message": str(e)}}
        sys.stdout.write(json.dumps(reply) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
