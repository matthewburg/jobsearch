"""Local job search app: http://127.0.0.1:8765

Serves the app page and a small JSON API over the SQLite store, the setup
state, and the person's own files. Local only (binds 127.0.0.1). Every change
is logged.

  python -I job-finder/app/server.py

Reads and writes stay inside the kit: profile files (Markdown and JSON) can be
viewed and edited; rendered resume drafts are served read-only from resumes/.
"""

import json
import mimetypes
import re
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

ROOT = Path(__file__).resolve().parent
KIT = ROOT.parent.parent
sys.path.insert(0, str(ROOT.parent / "store"))
sys.path.insert(0, str(ROOT.parent / "guard"))
import drafts  # noqa: E402
import setup_state  # noqa: E402
from db import PROFILE_MIN_SCORE, STATUSES, Store  # noqa: E402
from runlog import RunLog  # noqa: E402
from settings import load as load_settings  # noqa: E402

HOST, PORT = "127.0.0.1", 8765
log = RunLog("report-app")
STATIC = {"/": "report.html", "/index.html": "report.html", "/report.css": "report.css", "/report.js": "report.js",
          "/favicon.svg": "favicon.svg", "/favicon.ico": "favicon.ico"}
EDITABLE = (".md", ".json")


def kit_path(rel: str, roots: tuple[str, ...]) -> Path:
    """A path inside one of the allowed kit folders, or ValueError."""
    p = (KIT / rel).resolve()
    if not any(p.is_relative_to((KIT / r).resolve()) for r in roots):
        raise ValueError(f"not allowed: {rel}")
    return p


def first_name() -> str:
    """For the Home greeting: the first name in profile/resume.json, unless it's still the template's sample."""
    try:
        name = json.loads((KIT / "profile" / "resume.json").read_text(encoding="utf-8"))["basics"]["name"]
    except (FileNotFoundError, KeyError, json.JSONDecodeError):
        return ""
    return "" if name == "Jordan Rivera" else name.split()[0]


def profile_files() -> list[dict]:
    """The person's Markdown and JSON files, for the Profile page: profile/ and draft notes."""
    out = []
    for f in sorted((KIT / "profile").rglob("*")):
        if f.is_file() and f.suffix in EDITABLE and f.name != "setup.json":
            rel = f.relative_to(KIT).as_posix()
            out.append({"path": rel, "group": "/".join(rel.split("/")[1:-1]) or "profile", "name": f.name,
                        "modified": f.stat().st_mtime})
    return out


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype + ("; charset=utf-8" if ctype.startswith(("text", "application/j")) else ""))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj, default=str))

    def do_GET(self):
        url = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(url.query).items()}
        try:
            if url.path in STATIC:
                name = STATIC[url.path]
                ctype = {"html": "text/html", "css": "text/css", "js": "text/javascript", "svg": "image/svg+xml", "ico": "image/x-icon"}[name.rsplit(".", 1)[1]]
                return self._send(200, (ROOT / name).read_bytes(), ctype)
            store = Store(log=log)
            if url.path == "/api/jobs":
                return self._json({"jobs": store.jobs(), "statuses": STATUSES})
            if url.path == "/api/companies":
                return self._json({"companies": store.companies()})
            if url.path == "/api/runs":
                return self._json({"runs": store.runs(10), "unreviewed": store.review_queue(limit=0)["unreviewed"]})
            if url.path == "/api/settings":
                s = load_settings()
                return self._json({"pay": s["pay"], "stale_days": s["stale_days"], "test_mode": s["test_mode"],
                                   "profile_min_score": PROFILE_MIN_SCORE, "resume_style": drafts.style()})
            if url.path == "/api/overview":
                docs = store.documents()
                return self._json({"setup": setup_state.status(store),
                                   "drafts": {"ready": sum(d["status"] == "draft" and d["job_status"] not in ("dismissed",) for d in docs),
                                              "pending": len(store.drafts_pending())},
                                   "unreviewed": store.review_queue(limit=0)["unreviewed"],
                                   "name": first_name()})
            if url.path == "/api/dashboard":
                return self._json(store.dashboard(int(q.get("days", 14))))
            if url.path == "/api/documents":
                return self._json({"documents": store.documents(), "style": drafts.style(),
                                   "base": {"data": "profile/resume.json",
                                            "html": f"resumes/styles/{drafts.style()}.html",
                                            "pdf": f"resumes/styles/{drafts.style()}.pdf"}})
            if url.path == "/api/audit":
                return self._json(store.audit(int(q.get("days", 7)), q.get("decision") or None, int(q.get("limit", 300))))
            if url.path == "/api/files":
                return self._json({"files": profile_files()})
            if url.path == "/api/file":
                p = kit_path(q["path"], ("profile", "resumes"))
                return self._json({"path": q["path"], "content": p.read_bytes().decode("utf-8")})
            if url.path.startswith("/files/"):
                p = kit_path(unquote(url.path[len("/files/"):]), ("resumes",))
                ctype = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
                return self._send(200, p.read_bytes(), ctype)
            self._json({"error": "not found"}, 404)
        except (ValueError, KeyError) as e:
            self._json({"error": str(e)}, 400)
        except FileNotFoundError:
            self._json({"error": "not found"}, 404)

    def do_POST(self):
        url = urlparse(self.path)
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or "{}")
            store = Store(log=log)
            m = re.fullmatch(r"/api/jobs/(\d+)/(status|note)", url.path)
            if m and m.group(2) == "status":
                store.set_status(int(m.group(1)), body["status"], body.get("note", ""))
            elif m:
                store.add_note(int(m.group(1)), body["note"])
            elif url.path == "/api/documents/status":
                store.set_document_status(int(body["job_id"]), body["kind"], body["status"])
            elif url.path == "/api/seen/rescue":
                store.rescue(body["source"], body["source_id"], body.get("note", ""))
            elif url.path == "/api/file":
                p = kit_path(body["path"], ("profile", "resumes"))
                if p.suffix not in EDITABLE or not p.exists():
                    raise ValueError("only existing .md and .json files can be edited")
                if p.suffix == ".json":
                    json.loads(body["content"])  # refuse broken JSON
                p.write_bytes(body["content"].encode("utf-8"))  # exact bytes: no newline translation
                log("edit", f"edited {body['path']} in the app")
                if p.name == "resume.json" and p.parent.parent == KIT / "resumes":  # a draft: re-render it
                    doc = next((d for d in store.documents() if d["path"] == p.parent.relative_to(KIT).as_posix()), None)
                    if doc:
                        drafts.render(store, doc["job_id"], p.parent, doc.get("summary") or "")
            else:
                return self._json({"error": "not found"}, 404)
            self._json({"ok": True})
        except (ValueError, KeyError, json.JSONDecodeError) as e:
            log("error", f"bad request: {e}", path=self.path)
            self._json({"error": str(e)}, 400)

    def log_message(self, fmt, *args):
        if "/api/" in self.path and self.command == "POST":
            log("http", fmt % args)


if __name__ == "__main__":
    log("start", f"job search app on http://{HOST}:{PORT}")
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
