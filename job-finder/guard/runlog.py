"""Readable, append-as-it-happens logging for every job-finder component.

Each event is written immediately (flushed) to two files per day:
  state/logs/YYYY-MM-DD.log    human-readable, one line per event
  state/logs/YYYY-MM-DD.jsonl  the same events as JSON, for reports and tooling

So a run can be watched while it's still going:  python -I job-finder/guard/watch.py
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

LOG_DIR = Path(__file__).resolve().parent.parent / "state" / "logs"


class RunLog:
    def __init__(self, component: str, log_dir: Path = LOG_DIR, echo: bool = True):
        self.component = component
        self.log_dir = Path(log_dir)
        self.echo = echo
        self.run_id = datetime.now().strftime("%H%M%S") + f"-{os.getpid()}"

    def __call__(self, event: str, msg: str = "", **fields) -> None:
        now = datetime.now()
        record = {
            "ts": now.isoformat(timespec="seconds"),
            "run": self.run_id,
            "component": self.component,
            "event": event,
            "msg": msg,
            **fields,
        }
        extras = " ".join(f"{k}={v}" for k, v in fields.items() if k not in ("url",))
        url = f"  {fields['url']}" if "url" in fields else ""
        line = f"{now:%H:%M:%S} [{self.component}] {event.upper():9} {msg} {extras}".rstrip() + url

        self.log_dir.mkdir(parents=True, exist_ok=True)
        day = f"{now:%Y-%m-%d}"
        with open(self.log_dir / f"{day}.log", "a", encoding="utf-8") as f:
            f.write(line + "\n")
        with open(self.log_dir / f"{day}.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
        if self.echo:
            print(line, flush=True)


def null_log(*_args, **_kwargs):
    pass
