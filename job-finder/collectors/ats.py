"""Public company job boards (Greenhouse, Lever, Ashby), through the guard.

A 404 means the company doesn't host its board on that platform: it's not an
error, and it doesn't mean "no jobs".
"""

from __future__ import annotations

import html
import json
import re
from datetime import datetime, timezone


def _text(s: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", html.unescape(s or ""))).split())


def _url(platform: str, slug: str) -> str:
    if platform == "greenhouse":
        return f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true"
    if platform == "lever":
        return f"https://api.lever.co/v0/postings/{slug}?mode=json"
    if platform == "ashby":
        return f"https://api.ashbyhq.com/posting-api/job-board/{slug}?includeCompensation=true"
    raise ValueError(f"unknown platform {platform!r} (greenhouse, lever, ashby)")


def _normalize(platform: str, slug: str, data) -> list[dict]:
    out = []
    if platform == "greenhouse":
        for j in data.get("jobs", []):
            out.append({"source_id": str(j["id"]), "title": j.get("title"),
                        "location": (j.get("location") or {}).get("name"),
                        "posted_on": (j.get("first_published") or j.get("updated_at") or "")[:10] or None,
                        "url": j.get("absolute_url"), "description": _text(j.get("content"))})
    elif platform == "lever":
        for j in data:
            created = j.get("createdAt")
            out.append({"source_id": j["id"], "title": j.get("text"),
                        "location": (j.get("categories") or {}).get("location"),
                        "workplace": j.get("workplaceType"),
                        "posted_on": datetime.fromtimestamp(created / 1000, timezone.utc).date().isoformat() if created else None,
                        "url": j.get("hostedUrl"), "description": _text(j.get("descriptionPlain") or j.get("description"))})
    elif platform == "ashby":
        for j in data.get("jobs", []):
            comp = (j.get("compensation") or {}).get("compensationTierSummary")
            out.append({"source_id": j["id"], "title": j.get("title"), "location": j.get("location"),
                        "workplace": "remote" if j.get("isRemote") else None,
                        "posted_on": (j.get("publishedAt") or "")[:10] or None, "salary_text": comp,
                        "url": j.get("jobUrl"), "description": _text(j.get("descriptionPlain") or j.get("descriptionHtml"))})
    for j in out:
        j.update(source=f"ats:{platform}", company_slug=slug)
    return out


def title_matches(title: str, terms: list[str]) -> bool:
    """Loose on purpose: any term, any case, ignoring punctuation and word order
    around it, plurals allowed ("product" matches "VP, Products")."""
    t = " ".join(re.sub(r"[^a-z0-9]+", " ", (title or "").lower()).split())
    for term in terms:
        words = re.sub(r"[^a-z0-9]+", " ", term.lower()).split()
        if words and re.search(r"\b" + r"\s+".join(map(re.escape, words)) + r"s?\b", t):
            return True
    return False


def jobs(guard, platform: str, slug: str, keyword: str | list[str] | None = None,
         include_description: bool = False) -> dict:
    """The whole board is one request; `keyword` only trims what comes back.
    It matches job titles (descriptions are full of boilerplate): a list, or
    terms separated by |, matched loosely by title_matches(). None returns all.
    Descriptions are left out unless asked for, to keep results small."""
    status, body = guard.fetch(_url(platform, slug))
    if status == 404:
        guard.log("info", f"{slug} not hosted on {platform}")
        return {"found": False, "jobs": []}
    results = _normalize(platform, slug, json.loads(body))
    total = len(results)
    if keyword:
        terms = keyword.split("|") if isinstance(keyword, str) else keyword
        results = [j for j in results if title_matches(j["title"], terms)]
    for j in results:
        desc = j.pop("description", "") or ""
        if include_description:
            j["description"] = desc[:6000]
    guard.log("parsed", f"{platform}/{slug}", total=total, matched=len(results))
    return {"found": True, "total": total, "jobs": results}
