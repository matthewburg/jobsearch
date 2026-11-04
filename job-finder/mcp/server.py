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

import apply as apply_details  # noqa: E402
import ats  # noqa: E402
import drafts  # noqa: E402
import linkedin  # noqa: E402
import setup_state  # noqa: E402
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
                        "apply_info (set by apply_check), gaps [{what, why}]: research not done yet (description, employer_posting, salary, sentiment, news, "
                        "company_profile), so the next review finishes it; pass [] once complete. The employer's own posting "
                        "goes in sources as {source: 'company', source_id: <its job id or url>, url}. Merging fills empty fields "
                        "and replaces a shorter description; overwrite: true replaces every field given."),
        "inputSchema": {"type": "object", "properties": {"job": {"type": "object"}}, "required": ["job"]},
    },
    {
        "name": "apply_check",
        "description": ("How to apply to a stored job, so the person knows what to have ready: whether a cover letter is "
                        "required, optional, or not asked; the answers to prepare (salary expectations, LinkedIn, work "
                        "authorization, custom questions); and instructions from the posting (time zone, portfolio, "
                        "deadline). Greenhouse forms are read exactly; Lever and other sites fall back to the posting text. "
                        "Saves the result on the job (shown on its card) and returns it. Read-only: never fills in or submits "
                        "anything. Pass notes to add what you learned elsewhere (e.g. from reading the form in a browser). " + SLOW),
        "inputSchema": {"type": "object", "properties": {
            "job_id": {"type": "integer"},
            "url": {"type": "string", "description": "Posting URL to check; defaults to the job's company posting."},
            "notes": {"type": "array", "items": {"type": "string"}, "description": "Extra instructions to keep with it."},
        }, "required": ["job_id"]},
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
        "name": "drafts_pending",
        "description": ("Jobs the person marked Interested (or Applying) that don't have a tailored resume draft yet, "
                        "oldest mark first, with the posting, analysis, and resume advice. Empty = nothing to do. "
                        "Start of the resume-drafts task (PLAYBOOK section 8)."),
        "inputSchema": {"type": "object", "properties": {"limit": {"type": "integer", "default": 3}}},
    },
    {
        "name": "resume_draft_save",
        "description": ("Write or revise a job's tailored resume draft: saves resume.json (JSON Resume, same shape as "
                        "profile/resume.json) and notes.md in resumes/<job>/, renders it in the person's resume_style "
                        "(HTML + PDF), and links it to the job in the report. notes: markdown with what was tailored and "
                        "why, gaps against the posting, open questions, and a revision log. summary: one line for the card. "
                        "If the result has warnings (standing corrections from profile/resume-rules.json, or over the "
                        "page limit), fix every one and save again."),
        "inputSchema": {"type": "object", "properties": {
            "job_id": {"type": "integer"}, "resume": {"type": "object"},
            "notes": {"type": "string"}, "summary": {"type": "string"}},
            "required": ["job_id", "resume", "notes"]},
    },
    {
        "name": "resume_draft_get",
        "description": "A job's current resume draft (resume JSON, notes, folder), or null. Read it before revising.",
        "inputSchema": {"type": "object", "properties": {"job_id": {"type": "integer"}}, "required": ["job_id"]},
    },
    {
        "name": "resume_draft_render",
        "description": "Re-render a job's draft after its resume.json was edited directly in its folder, and refresh the report.",
        "inputSchema": {"type": "object", "properties": {"job_id": {"type": "integer"}}, "required": ["job_id"]},
    },
    {
        "name": "setup_status",
        "description": ("Setup progress: each step (installed, profile, connectors, tests, first_run, collector_schedule, "
                        "review_schedule, drafts_schedule, base_resume) with done / check / todo, plus the schedules "
                        "and their next runs. The report's Setup page shows the same thing."),
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "setup_mark",
        "description": ("Record a setup step as done (or not). Only after you've verified it: tests passed, the task "
                        "exists and its first run worked, the person approved their profile. For schedule steps pass "
                        "schedule {label, kind: 'claude' | 'windows', task, cron: 'M H dom mon dow' (local time), note} "
                        "so the report can show the next run."),
        "inputSchema": {"type": "object", "properties": {
            "step": {"type": "string", "enum": setup_state.STEP_IDS}, "done": {"type": "boolean", "default": True},
            "note": {"type": "string"}, "schedule": {"type": "object"}}, "required": ["step"]},
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
                        "applicants), plus the latest collector and review runs. Listings the person rescued from the "
                        "filtered-out list come first (decision 'rescue', their note in reason): save them, and treat the "
                        "note as tuning feedback. Every item must end up either saved (job_save) or skipped (seen_skip)."),
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


def apply_url(job: dict) -> str | None:
    """The best posting to read apply details from: the employer's own, then an ATS board, then anything."""
    srcs = [s for s in job.get("sources", []) if s.get("url")]
    for pick in (lambda s: s["source"] == "company", lambda s: s["source"].startswith("ats:"), lambda s: True):
        hit = next((s["url"] for s in srcs if pick(s)), None)
        if hit:
            return hit
    return None


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
    if name == "apply_check":
        s = store()
        j = next((x for x in s.jobs() if x["id"] == int(args["job_id"])), None)
        if not j:
            raise KeyError(f"no job {args['job_id']}")
        url = args.get("url") or apply_url(j)
        info = apply_details.check(guard(), url, j.get("description") or "", j.get("location")) if url else {
            "checked": date.today().isoformat(), "cover_letter": "unknown", "resume": "unknown", "prepare": [],
            "notes": ["No posting URL on file: find the employer's own posting first."]}
        info["notes"] = info.get("notes", []) + list(args.get("notes") or [])
        s.set_apply_info(j["id"], info)
        return info
    if name == "jobs_incomplete":
        return store().incomplete(int(args.get("limit", 20)))
    if name == "company_get":
        return store().company(args["company"])
    if name == "company_save":
        return {"key": store().save_company(args["company"], args["profile"])}
    if name == "drafts_pending":
        keep = ("id", "title", "company", "location", "workplace", "salary_text", "status", "description", "analysis")
        return [{k: j[k] for k in keep} for j in store().drafts_pending()[:int(args.get("limit", 3))]]
    if name == "resume_draft_save":
        return drafts.save_resume(store(), int(args["job_id"]), args["resume"], args["notes"], args.get("summary", ""))
    if name == "resume_draft_get":
        return drafts.read(store(), int(args["job_id"]))
    if name == "resume_draft_render":
        doc = drafts.read(store(), int(args["job_id"]))
        if not doc:
            raise KeyError(f"job {args['job_id']} has no resume draft")
        return drafts.render(store(), int(args["job_id"]), drafts.KIT / doc["path"], doc.get("summary") or "")
    if name == "setup_status":
        return setup_state.status(store())
    if name == "setup_mark":
        setup_state.mark(args["step"], args.get("done", True), args.get("note", ""), args.get("schedule"))
        return setup_state.status(store())
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
