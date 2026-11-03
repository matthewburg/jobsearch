"""Per-person settings, read from the kit's profile/ folder.

profile/settings.json holds the few numbers code needs: the pay band, when a
listing counts as stale, test mode, and private terms that must never appear in
a shared copy of the kit. profile/search.md (written for people and Claude)
holds keywords and locations; search_defaults() pulls them out for scripts.

Missing files fall back to DEFAULTS, so tests and a fresh copy still run.

  python -I job-finder/guard/settings.py    # show what's loaded
"""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path

KIT_ROOT = Path(__file__).resolve().parent.parent.parent
PROFILE_DIR = KIT_ROOT / "profile"

DEFAULTS = {
    "pay": {"floor": None, "target_low": None, "target_high": None},
    "stale_days": 45,
    "test_mode": True,
    "private_terms": [],
    "resume_style": "modern",     # the style tailored drafts use (a stylesheet in resume-builder/themes/)
    "collector": {
        "start_jitter_minutes": 120,  # random delay after the scheduled trigger
        "daily_searches": 3,          # the first N searches in search.md run every day
        "rotate_days": 3,             # the rest each run at least this often
        "max_pages": 3,               # per search, only while pages keep coming back mostly new
        "linkedin_reserve": 1,        # LinkedIn requests left for Claude's review each day
        "search_share": 0.4,          # share of the LinkedIn budget for search pages (the rest: postings)
        "weekend_share": 0.5,         # budget multiplier on Saturday and Sunday
        "max_window_days": 30,        # how far back to look on the first run or after a gap
    },
}


def load(profile_dir: Path = PROFILE_DIR) -> dict:
    """DEFAULTS overlaid with profile/settings.json. Keys starting with _ are notes."""
    out = copy.deepcopy(DEFAULTS)
    path = Path(profile_dir) / "settings.json"
    if not path.exists():
        return out
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ValueError(f"{path} isn't valid JSON: {e}") from e
    for key, value in data.items():
        if key.startswith("_"):
            continue
        if isinstance(out.get(key), dict) and isinstance(value, dict):
            out[key].update({k: v for k, v in value.items() if not k.startswith("_")})
        else:
            out[key] = value
    return out


def _bullets(md: str, heading: str) -> list[str]:
    m = re.search(rf"^##\s+{re.escape(heading)}\s*$(.*?)(?=^##\s|\Z)", md, re.M | re.S | re.I)
    if not m:
        return []
    items = [line[2:].strip() for line in m.group(1).splitlines() if line.startswith("- ")]
    return [i for i in items if i and not i.startswith("_(")]  # skip template placeholders


def _section(md: str, heading_start: str) -> str:
    m = re.search(rf"^##\s+{re.escape(heading_start)}.*?$(.*?)(?=^##\s|\Z)", md, re.M | re.S | re.I)
    return m.group(1) if m else ""


def _watchlist(md: str) -> list[dict]:
    """Rows of the 'Company watchlist' table: company, platform, slug."""
    out = []
    for line in _section(md, "Company watchlist").splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 3 or set(cells[0]) <= set("-: ") or cells[0].lower() == "company":
            continue
        company, platform, slug = cells[0], cells[1].lower(), cells[2].strip("`")
        if "_(" in company + slug or platform not in ("greenhouse", "lever", "ashby"):
            continue
        out.append({"company": company, "platform": platform, "slug": slug})
    return out


def _skip_words(md: str) -> list[str]:
    m = re.search(r"Title words that mean noise:\*\*\s*(.+)", _section(md, "Skip"))
    if not m or m.group(1).strip().startswith("_("):
        return []
    return [w.strip().strip('"') for w in m.group(1).split(",") if w.strip()]


def search_defaults(profile_dir: Path = PROFILE_DIR) -> dict:
    """Searches, locations, title net, watchlist, and skip words from profile/search.md."""
    path = Path(profile_dir) / "search.md"
    md = path.read_text(encoding="utf-8") if path.exists() else ""
    return {"keywords": _bullets(md, "Searches") or _bullets(md, "Keywords"),
            "locations": _bullets(md, "Locations"),
            "title_words": _bullets(md, "Title net"),
            "watchlist": _watchlist(md),
            "skip_words": _skip_words(md)}


if __name__ == "__main__":
    print(json.dumps({"profile": str(PROFILE_DIR), "settings": load(), "search": search_defaults()}, indent=1))
