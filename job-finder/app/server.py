"""Local job report app: http://127.0.0.1:8765

Serves the report page and a tiny JSON API over the SQLite store. Local only
(binds 127.0.0.1). Every request and status change is logged.

  python -I job-finder/app/server.py
"""

import json
import re
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent / "store"))
sys.path.insert(0, str(ROOT.parent / "guard"))
from db import PROFILE_MIN_SCORE, STATUSES, Store  # noqa: E402
from runlog import RunLog  # noqa: E402
from settings import load as load_settings  # noqa: E402

HOST, PORT = "127.0.0.1", 8765
log = RunLog("report-app")


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self._send(200, (ROOT / "report.html").read_bytes(), "text/html")
        elif self.path == "/api/jobs":
            self._send(200, json.dumps({"jobs": Store(log=log).jobs(), "statuses": STATUSES}))
        elif self.path == "/api/companies":
            self._send(200, json.dumps({"companies": Store(log=log).companies()}))
        elif self.path == "/api/runs":
            store = Store(log=log)
            self._send(200, json.dumps({"runs": store.runs(10),
                                        "unreviewed": store.review_queue(limit=0)["unreviewed"]}))
        elif self.path == "/api/settings":
            s = load_settings()
            self._send(200, json.dumps({"pay": s["pay"], "stale_days": s["stale_days"],
                                        "profile_min_score": PROFILE_MIN_SCORE}))
        else:
            self._send(404, json.dumps({"error": "not found"}))

    def do_POST(self):
        m = re.fullmatch(r"/api/jobs/(\d+)/(status|note)", self.path)
        if not m:
            return self._send(404, json.dumps({"error": "not found"}))
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or "{}")
            store = Store(log=log)
            if m.group(2) == "status":
                store.set_status(int(m.group(1)), body["status"], body.get("note", ""))
            else:
                store.add_note(int(m.group(1)), body["note"])
            self._send(200, json.dumps({"ok": True}))
        except (ValueError, KeyError) as e:
            log("error", f"bad request: {e}", path=self.path)
            self._send(400, json.dumps({"error": str(e)}))

    def log_message(self, fmt, *args):
        if "/api/" in self.path and self.command == "POST":
            log("http", fmt % args)


if __name__ == "__main__":
    log("start", f"report app on http://{HOST}:{PORT}")
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
