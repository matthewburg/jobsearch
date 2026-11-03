"""LinkedIn logged-out guest feed: search and posting parsers.

Every request goes through the guard (pacing, caps, logged-out, read-only).
"""

from __future__ import annotations

import html
import re
from datetime import date
from urllib.parse import urlencode

BASE = "https://www.linkedin.com/jobs-guest/jobs/api"

# LinkedIn's guest filters
WORKPLACE = {"onsite": "1", "remote": "2", "hybrid": "3"}


def _text(fragment: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", fragment or "")).split())


def _first(pattern: str, s: str) -> str:
    m = re.search(pattern, s, re.S)
    return _text(m.group(1)) if m else ""


def search_url(keywords: str, location: str = "United States", workplace: str | None = None,
               posted_within_days: int | None = None, start: int = 0) -> str:
    q = {"keywords": keywords, "location": location, "start": start}
    if workplace:
        q["f_WT"] = WORKPLACE[workplace]
    if posted_within_days:
        q["f_TPR"] = f"r{int(posted_within_days) * 86400}"
    return f"{BASE}/seeMoreJobPostings/search?{urlencode(q)}"


def posting_url(job_id: str) -> str:
    return f"{BASE}/jobPosting/{job_id}"


def parse_search(body: str) -> list[dict]:
    out = []
    for card in re.split(r"<li>", body)[1:]:
        jid = re.search(r"jobPosting:(\d+)", card)
        if not jid:
            continue
        posted = re.search(r'datetime="([^"]+)"', card)
        out.append({
            "source": "linkedin",
            "source_id": jid.group(1),
            "title": _first(r'base-search-card__title"[^>]*>(.*?)</h3>', card),
            "company": _first(r'base-search-card__subtitle"[^>]*>(.*?)</h4>', card),
            "location": _first(r'job-search-card__location"[^>]*>(.*?)</span>', card),
            "posted_on": posted.group(1) if posted else None,
            "salary_text": _first(r'job-search-card__salary-info"[^>]*>(.*?)</span>', card) or None,
            "url": f"https://www.linkedin.com/jobs/view/{jid.group(1)}",
        })
    return out


def parse_posting(job_id: str, body: str) -> dict:
    desc = _first(r'show-more-less-html__markup[^"]*"[^>]*>(.*?)</div>', body)
    flat = _text(body)
    salary = re.findall(r"\$[\d,]{5,}(?:\.\d+)?\s*(?:-|–|to|and)\s*\$[\d,]{5,}(?:\.\d+)?", flat)
    applicants = re.search(r"(Over \d+ applicants|\d+ applicants|Be among the first \d+ applicants)", flat)
    criteria = [_text(c) for c in re.findall(r"description__job-criteria-text[^>]*>(.*?)</span>", body, re.S)]
    return {
        "source": "linkedin",
        "source_id": job_id,
        "title": _first(r'top-card-layout__title[^>]*>(.*?)</h2>', body),
        "company": _first(r'topcard__org-name-link[^>]*>(.*?)</a>', body)
                   or _first(r'topcard__flavor[^>]*>(.*?)</span>', body),
        "location": _first(r'topcard__flavor--bullet[^>]*>(.*?)</span>', body),
        "posted_ago": _first(r'posted-time-ago__text[^>]*>(.*?)</span>', body),
        "applicants": applicants.group(1) if applicants else None,
        "seniority": criteria[0] if len(criteria) > 0 else None,
        "employment_type": criteria[1] if len(criteria) > 1 else None,
        "industry": criteria[-1] if len(criteria) > 2 else None,
        "salary_text": salary[0] if salary else None,
        "description": desc,
        "description_words": len(desc.split()),
        "url": f"https://www.linkedin.com/jobs/view/{job_id}",
        "fetched_on": date.today().isoformat(),
    }


def search(guard, **kwargs) -> list[dict]:
    status, body = guard.fetch(search_url(**kwargs))
    results = parse_search(body)
    guard.log("parsed", "linkedin search", results=len(results))
    if status == 200 and not results:
        guard.log("warn", "linkedin search returned no cards: layout may have changed")
    return results


def posting(guard, job_id: str) -> dict:
    status, body = guard.fetch(posting_url(job_id))
    result = parse_posting(job_id, body)
    if not result["description"]:
        guard.log("warn", f"linkedin posting {job_id}: no description found, layout may have changed")
    return result
