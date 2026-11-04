"""Render resume content into styled HTML and PDF.

Content is JSON Resume (jsonresume.org), usually profile/resume.json. Every
style shares one semantic, single-column layout, so applicant tracking systems
read them all the same way. A style is just a stylesheet in themes/. PDFs
come from headless Chrome or Edge, which ships with Windows.

  python -I resume-builder/build.py                      # all styles -> resumes/styles/ (+ a gallery page)
  python -I resume-builder/build.py --style modern       # one style
  python -I resume-builder/build.py --data resumes/acme/resume.json --out resumes/acme --style modern
"""

from __future__ import annotations

import argparse
import html
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
KIT = HERE.parent
THEMES = HERE / "themes"
MONTHS = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()
BROWSERS = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
]


def styles() -> list[str]:
    return sorted(p.stem for p in THEMES.glob("*.css") if p.stem != "base")


def e(s) -> str:
    return html.escape(str(s or ""))


def month(d: str | None) -> str:
    """'2025-11' -> 'Nov 2025'; '' or None -> 'Present'."""
    if not d:
        return "Present"
    parts = d.split("-")
    return f"{MONTHS[int(parts[1]) - 1]} {parts[0]}" if len(parts) > 1 else parts[0]


def span(start, end) -> str:
    return f"{month(start)} – {month(end)}"


def group_work(work: list[dict]) -> list[dict]:
    """Consecutive roles at the same company become one block (shows progression)."""
    groups: list[dict] = []
    for w in work:
        if groups and groups[-1]["name"] == w.get("name"):
            groups[-1]["roles"].append(w)
        else:
            groups.append({"name": w.get("name"), "location": w.get("location"), "roles": [w]})
    for g in groups:
        g["start"], g["end"] = g["roles"][-1].get("startDate"), g["roles"][0].get("endDate")
    return groups


def render(data: dict, style: str) -> str:
    b = data.get("basics", {})
    loc = b.get("location") or {}
    contact = [", ".join(x for x in (loc.get("city"), loc.get("region")) if x), b.get("phone"), b.get("email")]
    contact += [b.get("url", "").replace("https://", "")] + [p.get("url", "").replace("https://", "")
                                                            for p in b.get("profiles", [])]
    out = [f'<header class="head"><h1 class="name">{e(b.get("name"))}</h1>']
    if b.get("label"):
        out.append(f'<p class="label">{e(b["label"])}</p>')
    out.append('<p class="contact">' + '<span class="sep"> · </span>'.join(e(c) for c in contact if c) + "</p></header>")

    if b.get("summary"):
        out.append(f'<section class="summary"><h2>Summary</h2><p>{e(b["summary"])}</p></section>')

    if data.get("work"):
        out.append('<section class="experience"><h2>Experience</h2>')
        for g in group_work(data["work"]):
            multi = len(g["roles"]) > 1
            # Company line always carries location · dates; role lines repeat dates only when there are several roles
            where = [e(g["location"])] if g.get("location") else []
            out.append(f'<article class="job{" multi" if multi else ""}"><div class="job-head">'
                       f'<h3 class="company">{e(g["name"])}</h3><span class="where">'
                       + '<span class="sep"> · </span>'.join(where + [span(g["start"], g["end"])])
                       + "</span></div>")
            for r in g["roles"]:
                lean = not r.get("highlights") and not r.get("summary")
                dates = f'<span class="dates">{span(r.get("startDate"), r.get("endDate"))}</span>' if multi else ""
                out.append(f'<div class="role{" lean" if lean else ""}"><div class="role-head">'
                           f'<h4 class="title">{e(r.get("position"))}</h4>{dates}</div>')
                if r.get("summary"):
                    out.append(f'<p class="role-summary">{e(r["summary"])}</p>')
                if r.get("highlights"):
                    out.append("<ul>" + "".join(f"<li>{e(h)}</li>" for h in r["highlights"]) + "</ul>")
                out.append("</div>")
            out.append("</article>")
        out.append("</section>")

    if data.get("projects"):
        out.append('<section class="projects"><h2>Selected Projects</h2><ul class="plain">')
        for p in data["projects"]:
            kw = f' <span class="kw">({e(", ".join(p["keywords"]))})</span>' if p.get("keywords") else ""
            out.append(f'<li><strong class="pname">{e(p.get("name"))}.</strong> {e(p.get("description"))}{kw}</li>')
        out.append("</ul></section>")

    if data.get("skills"):
        out.append('<section class="skills"><h2>Skills</h2>')
        for s in data["skills"]:
            out.append(f'<p><strong>{e(s.get("name"))}:</strong> {e(", ".join(s.get("keywords", [])))}</p>')
        out.append("</section>")

    if data.get("education"):
        out.append('<section class="education"><h2>Education</h2>')
        for ed in data["education"]:
            what = ", ".join(x for x in (ed.get("studyType"), ed.get("area")) if x)
            out.append(f'<p><strong>{e(ed.get("institution"))}</strong>'
                       + (f'<span class="sep"> · </span>{e(what)}' if what else "")
                       + (f'<span class="sep"> · </span>{e(ed.get("endDate", "")[:4])}' if ed.get("endDate") else "")
                       + "</p>")
        out.append("</section>")

    if data.get("certificates"):
        out.append('<section class="certs"><h2>Certifications</h2>')
        for c in data["certificates"]:
            out.append(f'<p><strong>{e(c.get("name"))}</strong><span class="sep"> · </span>{e(c.get("issuer"))}'
                       + (f'<span class="sep"> · </span>{e(c.get("date"))}' if c.get("date") else "") + "</p>")
        out.append("</section>")

    css = (THEMES / "base.css").read_text(encoding="utf-8") + (THEMES / f"{style}.css").read_text(encoding="utf-8")
    return (f'<!doctype html>\n<html lang="en"><head><meta charset="utf-8">'
            f'<title>{e(b.get("name"))} – Resume</title><style>{css}</style></head>'
            f'<body class="theme-{style}"><main class="resume">{"".join(out)}</main></body></html>\n')


def find_browser() -> str | None:
    for p in BROWSERS:
        if Path(p).exists():
            return p
    for name in ("google-chrome", "chromium", "chrome", "msedge"):
        if shutil.which(name):
            return shutil.which(name)
    return None


def to_pdf(html_path: Path, pdf_path: Path, browser: str) -> None:
    with tempfile.TemporaryDirectory() as profile:  # throwaway profile: never touches your real browser
        subprocess.run([browser, "--headless=new", "--disable-gpu", "--no-first-run", f"--user-data-dir={profile}",
                        "--no-pdf-header-footer", f"--print-to-pdf={pdf_path}", html_path.as_uri()],
                       check=True, capture_output=True, timeout=90,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))  # no window flash from a windowless app


def gallery(out: Path, names: list[str], person: str) -> None:
    cards = "".join(
        f'<figure><a class="frame" href="{n}.pdf" target="_blank" title="Open the {n} PDF">'
        f'<iframe src="{n}.html" title="{n}" loading="lazy" scrolling="no" tabindex="-1"></iframe></a>'
        f'<figcaption><b>{n.title()}</b> · <a href="{n}.html" target="_blank">HTML</a> · '
        f'<a href="{n}.pdf" target="_blank">PDF</a></figcaption></figure>' for n in names)
    (out / "index.html").write_text(f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>Resume styles</title><meta name="viewport" content="width=device-width, initial-scale=1"><style>
body {{ margin: 0; padding: 24px; background: #e9e8e4; font: 14px/1.4 system-ui, sans-serif; color: #222; }}
h1 {{ font-size: 18px; margin: 0 0 4px; }} p {{ margin: 0 0 18px; color: #555; }}
.grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(440px, 1fr)); gap: 22px; }}
body {{ padding-bottom: 48px; }}
figure {{ margin: 0; }} .frame {{ display: block; width: 440px; height: 570px; overflow: hidden; background: #fff;
  box-shadow: 0 2px 10px rgba(0,0,0,.15); border-radius: 3px; }}
.frame:hover {{ box-shadow: 0 0 0 2px #1f6f78, 0 2px 10px rgba(0,0,0,.15); }}
/* previews ignore the mouse so the wheel scrolls the gallery; click opens the PDF */
iframe {{ width: 816px; height: 1056px; border: 0; transform: scale(.539); transform-origin: 0 0; pointer-events: none; }}
figcaption {{ margin-top: 8px; }} a {{ color: #1f6f78; }}
</style></head><body><h1>Resume styles: {e(person)}</h1>
<p>Same content, same single-column structure, different typography. Page one shown; open the PDF for the full resume.</p>
<div class="grid">{cards}</div></body></html>
""", encoding="utf-8")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data", type=Path, default=KIT / "profile" / "resume.json")
    ap.add_argument("--out", type=Path, default=KIT / "resumes" / "styles")
    ap.add_argument("--style", choices=styles(), action="append", help="repeat for several; default: all")
    ap.add_argument("--no-pdf", action="store_true")
    args = ap.parse_args(argv)

    data = json.loads(args.data.read_text(encoding="utf-8"))
    names = args.style or styles()
    built = build(data, args.out, names, pdf=not args.no_pdf)
    if not args.no_pdf and not built["pdf"]:
        print("No Chrome or Edge found: writing HTML only (open it and Print > Save as PDF).")
    for n in names:
        print(f"{n}: {args.out / (n + '.html')}" + (" + .pdf" if built["pdf"] else ""))
    if len(names) > 1:
        print(f"gallery: {args.out / 'index.html'}")
    for w in rule_warnings(data, args.out):
        print(f"RULE: {w}")
    return 0


def rule_warnings(data: dict, out: Path) -> list[str]:
    """The person's standing corrections (profile/resume-rules.json) and the page limit, via check.py."""
    sys.path.insert(0, str(HERE))
    import check
    return check.check(data, out)


def build(data: dict, out: Path, names: list[str], pdf: bool = True) -> dict:
    """Render `data` in each style into `out` (HTML, plus PDF when a browser is found).
    Several styles also get a gallery page. Returns {"pdf": bool}."""
    out.mkdir(parents=True, exist_ok=True)
    browser = find_browser() if pdf else None
    for n in names:
        page = out / f"{n}.html"
        page.write_text(render(data, n), encoding="utf-8")
        if browser:
            to_pdf(page, out / f"{n}.pdf", browser)
    if len(names) > 1:
        gallery(out, names, data.get("basics", {}).get("name", ""))
    return {"pdf": bool(browser)}


if __name__ == "__main__":
    sys.exit(main())
