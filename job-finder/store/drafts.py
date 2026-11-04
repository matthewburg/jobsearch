"""Tailored resume drafts: one folder per job under resumes/, recorded in the store.

  resumes/<job id>-<company>-<title>/
    resume.json   the tailored content (JSON Resume), edited directly when revising
    notes.md      what was tailored and why, gaps to address, open questions, revision log
    <style>.html / .pdf   rendered in the person's resume_style
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

KIT = Path(__file__).resolve().parent.parent.parent
RESUMES = KIT / "resumes"
sys.path.insert(0, str(KIT / "resume-builder"))
sys.path.insert(0, str(KIT / "job-finder" / "guard"))
import build as resume_build  # noqa: E402
import check as resume_check  # noqa: E402
from settings import load as load_settings  # noqa: E402


def slug(job: dict) -> str:
    words = lambda s, n: "-".join(re.sub(r"[^a-z0-9]+", " ", s.lower()).split()[:n])  # noqa: E731
    return f"{job['id']}-{words(job['company'], 2)}-{words(job['title'], 5)}"


def style() -> str:
    s = load_settings().get("resume_style") or "modern"
    return s if s in resume_build.styles() else "modern"


def save_resume(store, job_id: int, resume: dict, notes: str, summary: str = "") -> dict:
    """Write (or revise) the job's resume draft, render it, and record it."""
    job = next((j for j in store.jobs() if j["id"] == job_id), None)
    if job is None:
        raise KeyError(f"no job {job_id}")
    existing = next((d for d in job["documents"] if d["kind"] == "resume"), None)
    folder = KIT / existing["path"] if existing else RESUMES / slug(job)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "resume.json").write_text(json.dumps(resume, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (folder / "notes.md").write_text(notes.rstrip() + "\n", encoding="utf-8")
    return render(store, job_id, folder, summary or (existing or {}).get("summary", ""))


def render(store, job_id: int, folder: Path, summary: str = "") -> dict:
    """Re-render a draft folder after its resume.json was edited by hand, and record it."""
    resume = json.loads((folder / "resume.json").read_text(encoding="utf-8"))
    st = style()
    built = resume_build.build(resume, folder, [st])
    rel = folder.relative_to(KIT).as_posix()
    store.save_document(job_id, "resume", rel, summary)
    out = {"path": rel, "html": f"{rel}/{st}.html", "pdf": f"{rel}/{st}.pdf" if built["pdf"] else None}
    # standing corrections from profile/resume-rules.json, plus the page limit: fix each, then save again
    warnings = resume_check.check(resume, folder)
    if warnings:
        out["warnings"] = warnings
    return out


def read(store, job_id: int) -> dict | None:
    doc = next((d for j in store.jobs() if j["id"] == job_id for d in j["documents"] if d["kind"] == "resume"), None)
    if not doc:
        return None
    folder = KIT / doc["path"]
    notes = folder / "notes.md"
    return {**doc, "resume": json.loads((folder / "resume.json").read_text(encoding="utf-8")),
            "notes": notes.read_text(encoding="utf-8") if notes.exists() else ""}
