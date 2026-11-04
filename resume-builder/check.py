"""Check resume content against the person's standing rules before it goes out.

Rules live in profile/resume-rules.json: phrasings that were corrected once and must not come back
(a retired figure, a tool that isn't really used, a claim worded too strongly, work listed under the
wrong role), each with why and what to write instead. A rule with "in" applies only to entries whose
label ("Company / Position", "summary", "project …", "skills") matches it. The builder runs this on
every build, and resume_draft_save returns the warnings, so every draft, old or new, is held to the
same corrections.

  python -I resume-builder/check.py                      # the base resume and every draft
  python -I resume-builder/check.py resumes/acme/resume.json
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
KIT = HERE.parent
RULES = KIT / "profile" / "resume-rules.json"


def load_rules(path: Path = RULES) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"rules": []}


def blocks(resume: dict) -> list[tuple[str, str]]:
    """(label, text) per entry, so a rule can match within one job or project but not across them."""
    def text(v) -> str:
        if isinstance(v, str):
            return v
        if isinstance(v, dict):
            return " ".join(text(x) for k, x in v.items() if not k.startswith("_"))
        if isinstance(v, list):
            return " ".join(text(x) for x in v)
        return ""
    out = [("summary", text(resume.get("basics", {})))]
    for w in resume.get("work", []):
        out.append((f"{w.get('name', '')} / {w.get('position', '')}", text(w)))
    for p in resume.get("projects", []):
        out.append((f"project {p.get('name', '')}", text(p)))
    for key in ("skills", "certificates", "education"):
        out.append((key, text(resume.get(key, []))))
    return out


def pdf_pages(pdf: Path) -> int | None:
    if not pdf.exists():
        return None
    counts = re.findall(rb"/Count (\d+)", pdf.read_bytes())
    return max(int(c) for c in counts) if counts else None


def check(resume: dict, folder: Path | None = None, rules: dict | None = None) -> list[str]:
    """Warnings for one resume: rule matches, plus the page limit when a rendered PDF is in `folder`."""
    rules = rules or load_rules()
    warnings = []
    for label, txt in blocks(resume):
        for r in rules.get("rules", []):
            if r.get("in") and not re.search(r["in"], label, re.I):
                continue  # rule applies only to entries whose label matches, e.g. one role
            m = re.search(r["pattern"], txt, re.I | re.S)
            if m:
                warnings.append(f"{label}: \"{m.group(0)[:60]}\": {r['why']} Instead: {r['fix']}")
    limit = rules.get("max_pages")
    if folder and limit:
        for pdf in sorted(folder.glob("*.pdf")):
            n = pdf_pages(pdf)
            if n and n > limit:
                warnings.append(f"{pdf.name}: {n} pages; the limit is {limit}.")
    return warnings


def main(argv=None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    files = [Path(a) for a in args] or [KIT / "profile" / "resume.json", *sorted((KIT / "resumes").glob("*/resume.json"))]
    rules = load_rules()
    total = 0
    for f in files:
        folder = f.parent if f.parent.parent.name == "resumes" else None
        found = check(json.loads(f.read_text(encoding="utf-8")), folder, rules)
        total += len(found)
        print(f"{'ok  ' if not found else 'FIX '}{f.relative_to(KIT) if f.is_relative_to(KIT) else f}")
        for w in found:
            print(f"     - {w}")
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main())
