"""Load a JSON list of reviewed jobs into the store (dedupes as it goes).

  python -I job-finder/store/load_seed.py job-finder/state/seed-2026-10-31-test.json
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "guard"))
from db import Store  # noqa: E402
from runlog import RunLog  # noqa: E402


def main(path):
    log = RunLog("load-seed")
    store = Store(log=log)
    jobs = json.loads(Path(path).read_text(encoding="utf-8"))
    log("start", f"loading {len(jobs)} records from {Path(path).name}")
    new = merged = 0
    for job in jobs:
        _, is_new = store.upsert(job)
        new += is_new
        merged += not is_new
    log("done", "", records=len(jobs), new=new, merged=merged)


if __name__ == "__main__":
    main(sys.argv[1])
