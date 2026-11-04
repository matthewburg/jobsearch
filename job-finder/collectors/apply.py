"""How to apply to a job: what to submit and what to have ready, before you start.

Read-only, through the guard. Nothing here fills in or submits an application.

  - Greenhouse: the public job API lists the real application form (?questions=true),
    so we know whether a cover letter is asked for, and every question that's required.
  - Lever: the public API doesn't expose the form. Lever forms always have a resume
    upload and an "Additional information" box (where a cover letter goes), so we say so.
  - Anything else (Ashby, Workday, iCIMS, LinkedIn, ...): the form isn't readable, so we
    scan the posting text for instructions (cover letter, portfolio, time zone, ...).

Result (stored as jobs.apply_info):
  {platform, url, checked, source: "form" | "posting text",
   cover_letter: "required" | "optional" | "not asked" | "unknown",
   resume: "required" | "optional" | "unknown",
   prepare: ["Salary expectations (required)", ...],   # answers to have ready
   notes: ["Location: Remote - US (East or Central)", ...]}  # instructions and caveats
"""

from __future__ import annotations

import html
import json
import re
from datetime import date
from urllib.parse import parse_qs, urlparse

# Fields every form has; not worth listing as something to prepare.
_BASIC = re.compile(r"^(first name|last name|preferred (first )?name|full name|name|email|e-mail|phone|"
                    r"resume/?cv|resume|cv)\b", re.I)
_COVER = re.compile(r"cover letter", re.I)

# Instructions worth surfacing from the posting text, as (label, pattern).
# Kept narrow on purpose: "portfolio" or "assessment" alone usually describes the company's product, not the application.
_TZ = r"time ?zones?|\b(east(ern)?|central|mountain|pacific)\b[^.]{0,25}\b(time|hours|or|only)\b|\b(EST|CST|MST|PST|ET|CT|PT)\b|must (live|reside|be (located|based))"
_HINTS = [
    ("Cover letter", r"cover letter"),
    ("Portfolio or work samples", r"portfolio of (your )?work|(link|links) to (your )?portfolio|(submit|include|share) (a |your )?portfolio|work samples?|writing samples?|samples of your work"),
    ("References", r"(provide|list|submit|include) (\w+ )?references\b|references (are )?required"),
    ("Assessment or take-home", r"take[- ]home|\d+[- ]minute assessment|(complete|take) an? (\w+[- ])*(assessment|exercise|work sample)|case study (exercise|presentation)"),
    ("Deadline", r"(apply|applications?) (by|before|close[sd]?) |application deadline"),
    ("Time zone or location", _TZ),
    ("Travel", r"travel (up to|required|\d+%)|\d+% travel"),
    ("Clearance or citizenship", r"security clearance|U\.?S\.? citizen(ship)? (is )?required"),
    ("Sponsorship", r"(not|unable to|cannot) (offer|provide|sponsor)[^.]{0,40}sponsorship|sponsorship (is )?not available"),
    ("Salary expectations", r"salary (expectations|requirements)"),
]
_TZ_LOCATION = r"\b(east(ern)?|central|mountain|pacific|west(ern)?|EST|CST|MST|PST|ET|CT|PT)\b|time ?zone"


def _text(s: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", html.unescape(s or ""))).split())


def greenhouse_ids(url: str) -> tuple[str, str] | None:
    """(board slug, job id) from a Greenhouse posting URL, or None."""
    u = urlparse(url or "")
    if "greenhouse.io" not in u.netloc:
        return None
    q = parse_qs(u.query)
    if q.get("for") and q.get("token"):          # boards.greenhouse.io/embed/job_app?for=acme&token=123
        return q["for"][0], q["token"][0]
    m = re.search(r"/([\w-]+)/jobs/(\d+)", u.path)  # job-boards.greenhouse.io/acme/jobs/123
    return (m.group(1), m.group(2)) if m else None


def lever_ids(url: str) -> tuple[str, str] | None:
    u = urlparse(url or "")
    if u.netloc != "jobs.lever.co":
        return None
    parts = [p for p in u.path.split("/") if p]
    return (parts[0], parts[1]) if len(parts) >= 2 else None


def platform_of(url: str) -> str | None:
    host = urlparse(url or "").netloc
    for name, mark in (("greenhouse", "greenhouse.io"), ("lever", "lever.co"), ("ashby", "ashbyhq.com"),
                       ("workday", "myworkdayjobs.com"), ("icims", "icims.com"), ("smartrecruiters", "smartrecruiters.com"),
                       ("workable", "workable.com"), ("bamboohr", "bamboohr.com"), ("jobvite", "jobvite.com"),
                       ("linkedin", "linkedin.com")):
        if mark in host:
            return name
    return None


def hints(text: str, location: str | None = None) -> list[str]:
    """Instruction sentences from the posting text, labeled, at most one per kind."""
    out = []
    if location and re.search(_TZ_LOCATION, location, re.I):
        out.append(f"Time zone or location: posting says \"{location}\"")
    sentences = re.split(r"(?<=[.!?])\s+", _text(text))
    for label, pat in _HINTS:
        if any(o.startswith(label) for o in out):
            continue
        for s in sentences:
            if re.search(pat, s, re.I) and len(s) < 400:
                out.append(f"{label}: \"{s.strip()}\"")
                break
    return out


def _greenhouse_form(data: dict) -> dict:
    cover, resume, prepare = "not asked", "unknown", []
    for q in data.get("questions", []):
        label, req = (q.get("label") or "").strip(), bool(q.get("required"))
        if _COVER.search(label):
            cover = "required" if req else "optional"
        elif re.match(r"^resume", label, re.I):
            resume = "required" if req else "optional"
        elif not _BASIC.match(label):
            short = label if len(label) <= 140 else label[:137] + "..."
            prepare.append(f"{short} ({'required' if req else 'optional'})")
    if data.get("demographic_questions") or data.get("compliance"):
        prepare.append("Voluntary demographic / EEO questions (optional)")
    return {"cover_letter": cover, "resume": resume, "prepare": prepare}


def check(guard, url: str, description: str = "", location: str | None = None) -> dict:
    """Apply details for one posting URL (the employer's own posting is best)."""
    info = {"platform": platform_of(url), "url": url, "checked": date.today().isoformat(),
            "source": "posting text", "cover_letter": "unknown", "resume": "unknown", "prepare": [], "notes": []}
    text = description or ""
    gh = greenhouse_ids(url)
    lv = lever_ids(url)
    if gh:
        status, body = guard.fetch(f"https://boards-api.greenhouse.io/v1/boards/{gh[0]}/jobs/{gh[1]}?questions=true")
        if status == 200:
            data = json.loads(body)
            info.update(_greenhouse_form(data), source="form")
            text = _text(data.get("content")) or text
            location = (data.get("location") or {}).get("name") or location
        elif status == 404:
            info["notes"].append("The Greenhouse posting is gone (404): the job may be closed.")
    elif lv:
        status, body = guard.fetch(f"https://api.lever.co/v0/postings/{lv[0]}/{lv[1]}")
        if status == 200:
            data = json.loads(body)
            text = _text(data.get("descriptionPlain") or data.get("description")) + " " + \
                " ".join(_text(x.get("content")) for x in data.get("lists", [])) + " " + _text(data.get("additionalPlain")) or text
            location = (data.get("categories") or {}).get("location") or location
            info.update(resume="required", cover_letter="optional",
                        prepare=["Lever's form has an \"Additional information\" box; a short cover note can go there. "
                                 "Custom questions, if any, only show on the form itself."])
        elif status == 404:
            info["notes"].append("The Lever posting is gone (404): the job may be closed.")
    else:
        info["prepare"].append(f"The application form ({info['platform'] or 'company site'}) can't be read ahead of time; "
                               "expect name, contact, resume, and possibly custom questions.")
    if location:
        info["location"] = location
    info["notes"] += hints(text, location)
    if info["cover_letter"] == "unknown" and any(n.startswith("Cover letter") for n in info["notes"]):
        info["cover_letter"] = "mentioned in posting"
    return info
