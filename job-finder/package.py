"""Build a clean, shareable copy of the kit: the engine only, no personal data.

Copies SETUP.md, templates/, resume-builder/, the job-finder code and docs, and
the kit's own root files from kit/ (README.md, CLAUDE.md, AGENTS.md, LICENSE, .gitignore). Never
copies profile/, samples/, job-finder/state/, or anything else. It builds in a
temporary folder and scans every file for your home folder path and for the
private_terms in profile/settings.json (whole words, any case). If anything
matches, it lists the hits and stops without touching --out.

--out is a new or empty folder, or a git repo made by an earlier run: then its
contents are replaced (the .git folder is kept), so `git status` shows exactly
what changed in the engine. Commit and push from there.

  python -I job-finder/package.py --out ../jobsearch
  python -I job-finder/package.py --out ../job-search-kit --zip
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
import tempfile
from pathlib import Path

JF = Path(__file__).resolve().parent
KIT = JF.parent
sys.path.insert(0, str(JF / "guard"))
from settings import load as load_settings  # noqa: E402

ENGINE = [
    "SETUP.md",
    "templates",
    "resume-builder",
    "job-finder/README.md", "job-finder/SPEC.md", "job-finder/PLAYBOOK.md", "job-finder/RESEARCH.md",
    "job-finder/install.py", "job-finder/package.py", "job-finder/collect.py", "job-finder/schedule-collector.ps1", "job-finder/report.ps1",
    "job-finder/guard", "job-finder/collectors", "job-finder/store", "job-finder/app",
    "job-finder/mcp", "job-finder/tests",
]
ROOT_FILES = KIT / "kit"  # become the shared kit's top-level files
SKIP_DIRS = {"__pycache__", "state", ".pytest_cache"}
SKIP_SUFFIXES = {".pyc", ".db", ".log", ".jsonl", ".lock"}


def engine_files():
    """(source, path inside the kit) for every file the shared kit gets."""
    for entry in ENGINE:
        p = KIT / entry
        if p.is_file():
            yield p, p.relative_to(KIT)
        else:
            for f in sorted(p.rglob("*")):
                rel = f.relative_to(KIT)
                if f.is_file() and not SKIP_DIRS & set(rel.parts) and f.suffix not in SKIP_SUFFIXES:
                    yield f, rel
    for f in sorted(ROOT_FILES.iterdir()):
        if f.is_file():
            yield f, Path(f.name)


def private_patterns() -> list[tuple[str, re.Pattern]]:
    home = str(Path.home())
    pats = [(home, re.compile(re.escape(home).replace(r"\\", r"[\\/]+"), re.I))]
    for term in load_settings()["private_terms"]:
        pats.append((term, re.compile(rf"(?<!\w){re.escape(term)}(?!\w)", re.I)))
    return pats


def scan(root: Path) -> list[str]:
    hits = []
    pats = private_patterns()
    for f in sorted(root.rglob("*")):
        if not f.is_file():
            continue
        try:
            text = f.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for n, line in enumerate(text.splitlines(), 1):
            for term, pat in pats:
                if pat.search(line):
                    hits.append(f"{f.relative_to(root).as_posix()}:{n}: {term!r}")
    return hits


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, required=True,
                    help="new or empty folder, or a kit git repo from an earlier run (refreshed in place)")
    ap.add_argument("--zip", action="store_true", help="also make <out>.zip")
    args = ap.parse_args(argv)
    out = args.out.resolve()

    if out == KIT or KIT in out.parents:
        print("--out must be outside the kit folder.")
        return 1
    existing = [p for p in out.iterdir() if p.name != ".git"] if out.exists() else []
    if existing and not (out / ".git").is_dir():
        print(f"{out} already has files in it and isn't a kit repo. Pick a new folder.")
        return 1

    with tempfile.TemporaryDirectory() as tmp:
        build = Path(tmp)
        files = list(engine_files())
        for src, rel in files:
            (build / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, build / rel)

        hits = scan(build)
        if hits:
            print(f"Stopped: {len(hits)} private match(es). Nothing was written. Fix these in the kit, then run again:")
            print("  " + "\n  ".join(hits))
            return 2

        out.mkdir(parents=True, exist_ok=True)
        for p in existing:  # refresh: whatever the engine no longer has disappears too
            shutil.rmtree(p) if p.is_dir() else p.unlink()
        shutil.copytree(build, out, dirs_exist_ok=True)

    print(f"Copied {len(files)} files to {out}. Private-data scan: clean.")
    if (out / ".git").is_dir():
        print("It's a git repo: review with `git status` / `git diff` there, then commit and push.")
    if args.zip:
        archive = shutil.make_archive(str(out), "zip", root_dir=out.parent, base_dir=out.name)
        print(f"Zip: {archive}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
