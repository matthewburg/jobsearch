"""Watch or summarize the job-finder logs.

  python -I job-finder/guard/watch.py            follow today's log live (Ctrl+C to stop)
  python -I job-finder/guard/watch.py --summary  today's totals: requests, statuses, refusals, pushback
  python -I job-finder/guard/watch.py --day 2026-11-02 --summary
"""

import argparse
import json
import sys
import time
from collections import Counter
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from runlog import LOG_DIR  # noqa: E402


def follow(path: Path):
    print(f"following {path} (Ctrl+C to stop)\n", flush=True)
    while not path.exists():
        time.sleep(2)
    with open(path, encoding="utf-8") as f:
        while True:
            line = f.readline()
            if line:
                print(line, end="", flush=True)
            else:
                time.sleep(1)


def summary(path: Path):
    if not path.exists():
        print(f"no log for that day: {path}")
        return
    events = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    by_event = Counter(e["event"] for e in events)
    statuses = Counter((e.get("site"), e.get("status")) for e in events if e["event"] == "response")
    print(f"{path.name}: {len(events)} events across {len({e['run'] for e in events})} runs")
    print("events:   " + ", ".join(f"{k}={v}" for k, v in by_event.most_common()))
    for (site, status), n in sorted(statuses.items(), key=str):
        print(f"response: {site} {status} x{n}")
    for e in events:
        if e["event"] in ("refused", "pushback", "error"):
            print(f"{e['ts']} {e['event'].upper()} {e.get('msg', '')}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--day", default=date.today().isoformat())
    p.add_argument("--summary", action="store_true")
    a = p.parse_args()
    path = LOG_DIR / f"{a.day}.jsonl" if a.summary else LOG_DIR / f"{a.day}.log"
    try:
        summary(path) if a.summary else follow(path)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
