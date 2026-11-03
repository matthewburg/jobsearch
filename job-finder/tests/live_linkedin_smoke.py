"""Tiny live check of the LinkedIn logged-out guest endpoint, through the guard.

Makes at most 2 requests: one search page, then one posting. Saves the raw
responses to ../state/smoke/ and logs what it could parse (see guard/watch.py).

Run:  python -I job-finder/tests/live_linkedin_smoke.py
"""

import html
import re
import sys
from pathlib import Path
from urllib.parse import urlencode

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "guard"))
from polite import STATE_DIR, Guard, GuardRefused  # noqa: E402
from runlog import RunLog  # noqa: E402
from settings import search_defaults  # noqa: E402

OUT = STATE_DIR / "smoke"


def text(fragment):
    return html.unescape(re.sub(r"<[^>]+>", " ", fragment)).split()


def main():
    log = RunLog("linkedin-smoke")
    OUT.mkdir(parents=True, exist_ok=True)
    g = Guard()
    # The first keyword and location from profile/search.md
    search = search_defaults()
    keywords = (search["keywords"] or ["Product Manager"])[0]
    location = re.sub(r"\s*\(.*\)$", "", (search["locations"] or ["United States"])[0])
    log("start", f"1 search + 1 posting, logged out: {keywords!r} in {location!r}")
    query = urlencode({"keywords": keywords, "location": location, "start": 0})
    url = f"https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?{query}"
    try:
        status, body = g.fetch(url)
    except GuardRefused as e:
        log("stopped", str(e))
        return
    (OUT / "search.html").write_text(body, encoding="utf-8")

    ids = re.findall(r"urn:li:jobPosting:(\d+)", body)
    titles = [" ".join(text(t)) for t in re.findall(r'class="base-search-card__title"[^>]*>(.*?)</h3>', body, re.S)]
    companies = [" ".join(text(c)) for c in re.findall(r'class="base-search-card__subtitle"[^>]*>(.*?)</h4>', body, re.S)]
    log("parsed", "search page", postings=len(ids), titles=len(titles), companies=len(companies))
    for t, c in list(zip(titles, companies))[:10]:
        log("posting", f"{t} | {c}")
    if not ids:
        log("warn", "no posting ids found: page layout may have changed")
        return

    try:
        status, body = g.fetch(f"https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{ids[0]}")
    except GuardRefused as e:
        log("stopped", str(e))
        return
    (OUT / f"posting-{ids[0]}.html").write_text(body, encoding="utf-8")
    desc = re.search(r'class="show-more-less-html__markup[^"]*"[^>]*>(.*?)</div>', body, re.S)
    words = text(desc.group(1)) if desc else []
    if words:
        log("parsed", f"posting {ids[0]} description", words=len(words))
    else:
        log("warn", f"posting {ids[0]}: no description found: layout may have changed")
    log("done", "")


if __name__ == "__main__":
    main()
