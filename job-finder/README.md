# Job Finder

What it should do: [SPEC.md](SPEC.md). How Claude runs a search and scores jobs: [PLAYBOOK.md](PLAYBOOK.md). Source research: [RESEARCH.md](RESEARCH.md). Setting it up: [../SETUP.md](../SETUP.md).

## Your settings

The code reads two files in the kit's `profile/` folder, via [guard/settings.py](guard/settings.py):
- **`profile/settings.json`:** pay band (`floor`, `target_low`, `target_high`), `stale_days`, `test_mode`, and `private_terms` (words that must never appear in a shared copy).
- **`profile/search.md`:** keywords and locations (also read by Claude).

Missing files fall back to safe defaults: test mode on, no pay band. Run `python -I job-finder/guard/settings.py` to see what's loaded.

## The daily loop

Two halves, on separate schedules. See [PLAYBOOK.md](PLAYBOOK.md#how-the-daily-loop-works).

- **Collect, in the background:** [collect.py](collect.py), started daily by Windows Task Scheduler ([schedule-collector.ps1](schedule-collector.ps1); cron on Mac/Linux). No Claude involved.
  - Each day is one browsing session: a random start delay (up to 2 h), then due LinkedIn searches, postings for new listings that pass the title net, and the watchlist boards at random points in between.
  - Every request goes through the guard.
  - Searches rotate:
    - The first `daily_searches` run every day; the rest run every `rotate_days`.
    - Pages go deeper only while they come back mostly new.
    - The look-back window widens automatically after a gap (computer off, missed days).
  - Weekends are lighter. A small LinkedIn reserve is left for the review.
  - All of these knobs live in `profile/settings.json` under `collector`.
  - Results go into `seen`, and new listings with their details go into `listings`.
  - Each run is recorded in `runs`, and finishes in about 10 min in test mode or about an hour in normal mode.
- **Review, by Claude:** a scheduled task in the Claude desktop app runs the playbook's daily review:
  - triage the queue, search the connectors, research, score, and save;
  - record a summary with `review_done`;
  - send one notification.
  - The report only grows. New jobs get a **New** chip, and a banner shows the last review and collection.

```bash
python -I job-finder/collect.py --plan
```

```bash
python -I job-finder/collect.py --now
```

The first shows today's plan (no network); the second runs a collection right away instead of waiting for the schedule.

**Test mode limits it:** 6 LinkedIn requests a day means only about 2 searches and 3 postings, so the rotation can't cover every search. Normal mode (40/day) covers most of it daily.

## Install and share

```bash
python -I job-finder/install.py --dry-run
```

`install.py` creates `profile/` and `samples/` from `templates/`, copying missing files only. It also registers the MCP server in `.mcp.json` and the report preview in `.claude/launch.json`, with absolute paths to wherever this kit lives. Pass `--project DIR` when Claude sessions open in a different folder. Other entries in those files are left alone.

```bash
python -I job-finder/package.py --out ../job-search-kit --zip
```

`package.py` copies only the engine (no `profile/`, `samples/`, or `state/`) into a new folder. It then scans every file for your home folder path and your `private_terms`. Any match stops it, removes the copy, and lists the hits.

## The guard

[guard/polite.py](guard/polite.py). **Every** network request from any collector, plain HTTP or headless browser, goes through `Guard.permit()` / `Guard.fetch()`. The guard decides *when* a request may happen, so a bug or loop in a collector can't hammer a site.

| Rule | How it's enforced |
|---|---|
| Logged-out only | `fetch()` has no cookie jar. Any `Cookie` / `Authorization` header is refused. Logged-in LinkedIn pages aren't on the allowlist. |
| Read-only | GET only. Login, apply, checkpoint, account, messaging, and profile (`/in/`) paths are refused on every site. |
| Known sites only | Per-site host and path allowlist (LinkedIn guest endpoints, Greenhouse, Lever, Ashby). Anything else is refused. |
| One at a time | A cross-process file lock, so only one request is ever in flight, even with several scripts running. |
| Human pacing | Randomized waits between requests (LinkedIn 25–90 s), a 15% chance of an extra 1–3 min "reading" pause, and a 4 s global minimum gap. |
| Low volume | Per-site hourly and daily caps (LinkedIn 15/h, 40/day). **Test mode (`test_mode` in settings, on by default) caps LinkedIn at 6/day.** Caps persist across runs in `state/guard_state.json`. |
| Daytime only | No requests between 10 pm and 7 am. |
| Back off | A 429 / 999 / 403 / 401, a CAPTCHA, or a login wall puts that site in cooldown (LinkedIn 48 h) and refuses everything to it until then. Only small pages (real challenge pages) are scanned in full for challenge words; normal pages only have their `<title>` checked, so a security job description can't trigger a false cooldown. |

Not done, on purpose: no proxy rotation, no user-agent rotation (one fixed, ordinary browser identity), no CAPTCHA solving, no fingerprint tricks.

```bash
python -I job-finder/guard/test_polite.py
```

```bash
python -I job-finder/guard/test_settings.py
```

```bash
python -I job-finder/store/test_store.py
```

```bash
python -I job-finder/guard/polite.py
```

```bash
python -I job-finder/tests/live_linkedin_smoke.py
```

These are, in order: offline guard tests (fake clock, no network); offline settings tests; offline seen-tracking and title-net tests; today's counts, caps, and cooldowns; and a live check (1 search plus 1 posting, using the first keyword and location in `search.md`).

## Logging and visibility (a rule for every component)

Everything logs what it's doing **as it happens**, so a run can be checked while it's still going. It goes through [guard/runlog.py](guard/runlog.py) (`RunLog("component-name")`). Each event is flushed immediately to:
- `state/logs/YYYY-MM-DD.log`: human-readable, one line per event
- `state/logs/YYYY-MM-DD.jsonl`: the same events as JSON, for summaries and the daily report

The guard logs every **waiting** period, **request**, **response** (status, bytes, ms), **refused** request (and why), **pushback** / cooldown, and network **error**. Collectors log what they **parsed** (counts), **warn** when a page looks different than expected (layout changes), and log **start** / **done** / **stopped**.

```bash
python -I job-finder/guard/watch.py
```

```bash
python -I job-finder/guard/watch.py --summary
```

The first follows today's log live; the second shows today's totals, statuses, refusals, and pushback.

## Job store and report app

- **[store/db.py](store/db.py):** SQLite at `state/jobs.db`.
  - One row per real job, deduped by normalized company + title. "Acme Tech" vs. "Acme Technology Inc." merge correctly.
  - Every source that listed it is kept, along with the **earliest posting date** any source reports (the ghost-listing signal).
  - Every status change and note is kept in `events`: the work-search paper trail.
  - **`seen`:** every listing any search ever returned, saved or not, with first/last seen, days seen, and the triage decision. Search results come back marked new or already seen (matched by source id, or by company + title across sites), so each day's effort goes to new listings. That's what lets the net be wide.
  - **Wide net:** searches are broad and rotated, the title net is loose (`ats.title_matches`: any word, any case, plurals OK), and Claude does the precise matching when scoring. See [PLAYBOOK.md](PLAYBOOK.md#2-collect-a-wide-net-fetched-once).
- **[app/server.py](app/server.py) + [app/report.html](app/report.html):** a local report at http://127.0.0.1:8765 (localhost only). `GET /api/jobs` and `/api/settings`; `POST` status and notes.
  - **Header:**
    - stat strip: to review, strong fits, pay in target, applied
    - views: New / Interested / Applied / Closed / Dismissed / All
    - search
    - sort: best fit, highest pay by midpoint, newest, company
    - filters: remote, pay ≥ floor, hide stale, AI-forward
    - Sort and filters are remembered per browser.
  - **Cards:**
    - score ring
    - pay panel with a range bar against your target band and floor, colored by pay fit (both from `profile/settings.json`)
    - why it fits / concerns
    - resume advice, level fit, company profile, sources, and history under one expander
  - **Links:** the employer's own posting first ("Company posting"), else a "Find on company site" search; job-board links follow, one per URL, with search-results links labeled.
  - **Research in progress:** a chip and a "Still to research" list when a card has gaps. The next review fills them in.
  - **Company one-pager:** a fuller company page (products, market, business, leadership, culture, news, fit, questions), written for every job you mark Interested and for new jobs scoring 60+.
  - **Buttons:** Interested, Mark applied, Dismiss (asks for a reason, which feeds tuning), Reset.
  - Light and dark mode. The header unpins on phones.
- **[store/load_seed.py](store/load_seed.py):** loads a JSON batch of reviewed jobs.

```bash
powershell -ExecutionPolicy Bypass -File job-finder\report.ps1        # Windows: start in the background if needed + open
powershell -ExecutionPolicy Bypass -File job-finder\report.ps1 -Stop  # stop it
python -I job-finder/app/server.py                                     # any OS, in the foreground
```

Only the report page needs this server; the collector, the review, and the MCP tools use the database directly.

## MCP server

[mcp/server.py](mcp/server.py): a stdlib-only stdio MCP server, registered as `job-finder` by `install.py`. Claude Code asks you to approve it the first time a new session starts in the project folder. It logs to the same daily log (components `mcp`, `guard`, `store`). It never writes to stdout except the protocol.

| Tool | What it does |
|---|---|
| `guard_status` | Today's counts, caps, cooldowns |
| `linkedin_search` | Logged-out guest search, ~10 results (paced: can take minutes) |
| `linkedin_posting` | Full posting: description, salary, applicants (paced) |
| `ats_jobs` | A company's Greenhouse / Lever / Ashby board (one request for the whole board). Titles are filtered loosely by the title net in `search.md`; descriptions only when asked. |
| `seen_check` | Record connector results (Indeed / ZipRecruiter / Dice) as seen and mark what's new |
| `seen_skip` | Record triaged-out listings with a reason, so they're never reviewed again |
| `seen_stats` | New listings per source per day: is the net wide enough? |
| `review_queue` | The daily review's starting point: unreviewed listings with collected details, plus recent runs |
| `review_done` | Record the review's summary and counts (shown in the report banner) |
| `jobs_list` | Store contents, filtered by status / score (descriptions left out by default) |
| `job_save` | Insert or merge a reviewed job (deduped), with `gaps` for research still to do |
| `jobs_incomplete` | Open jobs with gaps or a missing/stale company one-pager, marked jobs first, then by score |
| `company_get` / `company_save` | Read or write a company one-pager (shown from the card's "Company one-pager" button) |
| `job_set_status` | Update the local tracker (never applies anywhere) |
| `log_tail` | The last N lines of today's log |

Collector modules shared by the MCP server and scripts: [collectors/linkedin.py](collectors/linkedin.py), [collectors/ats.py](collectors/ats.py).

## Source quality (from testing, 2026-10-31)
| Source | Quality | Notes |
|---|---|---|
| LinkedIn guest | **Best** | Relevant results, posting date, applicant counts, full descriptions with salary. No pushback at test volumes. |
| Company job boards | **Great** | Finds roles the job sites miss. Needs a watchlist in `search.md`. |
| Indeed connector | Mixed | Good details and salary. Search relevance is loose (a food-science job for "Director of Product"). Company data is excellent, but one lookup mixed in another company's description. |
| ZipRecruiter connector | Mixed | 5 results per call, loose relevance (a pharmacist for "Director of PM"). Has salary and days-ago. Apply links are short-lived redirects. |
| Dice connector | Weak for PM | Mostly contract and recruiter listings. Filter to direct hire + full-time. Better for engineering roles. |
| Crunchbase (free) | **Great** | Funding, headcount, growth trend, layoffs, launches. Metered monthly; one full profile costs a lot of context, so request specific fields. |

## Headless browser

Use plain HTTP wherever it works (the LinkedIn guest feed does). Playwright is a fallback only, and isn't installed. If it's needed:
- real installed Chrome (`channel="chrome"`)
- a visible window (it can sit minimized or off to the side)
- a dedicated, non-persistent profile; never a logged-in one
- no stealth plugins, and no hiding `navigator.webdriver`
- every page load goes through `Guard.permit()`
