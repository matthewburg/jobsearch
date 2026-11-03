# Job Search Kit: Setup Guide

**For someone who wants to run this for their own job search, and for their Claude.** Open a Claude session in the kit folder and say: *"Read SETUP.md and set this up for me."* Claude walks through the steps below, asks the questions, and fills in the files with you.

**For Claude:** the app's Setup page (http://127.0.0.1:8765/#setup, once the installer has run) shows these steps. Record each one with the `setup_mark` tool **only after you've verified it**: tests passed, the person approved their profile, a scheduled task exists and its first run worked. For schedule steps, include the schedule (`label`, `kind`, `task`, `cron`) so the app can show when it runs next. Some steps the app also checks itself (the installer ran, a first review exists, the Windows collector task is registered). The job list stays closed until the required steps are done.

Status: in daily use on a real search. What isn't done yet is in [Still to build](#still-to-build).

## What it does

1. **Finds jobs every day.** It searches the LinkedIn logged-out job feed, the Indeed / ZipRecruiter / Dice connectors, and the public job boards of companies you name.
2. **Researches and scores them** against your profile. Claude reads each posting, looks up the company, checks for ghost listings, and writes a report card: score, why it fits, concerns, pay versus your range, and resume advice.
3. **Shows a local report** (http://127.0.0.1:8765) with sorting, filters, and a tracker (interested → applied → interviewing …). Dismissing a job asks for a reason, and the reasons tune later scoring.
4. **Keeps a paper trail** of every status change, which you can use for unemployment work-search logs.
5. *(In progress)* **Drafts tailored resumes and cover letters** from your experience bank, in your voice.

## Hard rules (these stay, whoever runs it)

- **It never applies to a job, submits a form, creates an account, signs in anywhere, or contacts anyone.** It gathers information and drafts documents. You review everything and apply yourself.
- **LinkedIn is logged-out only.** Never connect your LinkedIn account to any automation; it's too valuable during a job search.
- **Every request goes through the guard** ([job-finder/guard/polite.py](job-finder/guard/polite.py)): human pacing, small daily caps, daytime only, and it backs off for days if a site pushes back. No CAPTCHA solving, proxy rotation, or stealth tricks.
- **Everything personal stays on your computer.** Your profile, resumes, and job database are never shared with the kit.

## The engine vs. your data

| Path | What it is | Whose |
|---|---|---|
| `job-finder/guard/`, `collectors/`, `store/`, `app/`, `mcp/`, `tests/` | The code: pacing guard, logging, LinkedIn and job-board collectors, SQLite store, report app, MCP server | Engine (shared) |
| `job-finder/PLAYBOOK.md` | How Claude runs a daily search and scores jobs | Engine |
| `job-finder/install.py`, `package.py` | Set up on a new computer; build a clean shareable copy | Engine |
| `templates/` | Blank profile and samples files to copy and fill in | Engine |
| `resume-builder/` | Renders resume content in parse-safe styles to HTML and PDF | Engine |
| `SETUP.md` (this file) | Setup steps | Engine |
| `profile/` | Your experience bank: targets, roles, accomplishments, skills, plus `settings.json` (pay band, test mode) and `search.md` (keywords, watchlist) | **Yours** |
| `samples/` | Your past resumes, cover letters, recommendations | **Yours** |
| `job-finder/state/` | Your job database, logs, and guard counters. Starts empty. | **Yours** |
| `resumes/`, `cover-letters/`, `tracker/` | Generated documents and your application history | **Yours** |
| Plans, unemployment notes | Your schedule and state-specific admin | **Yours** |

To share the kit, don't copy folders by hand. Run `package.py` (see [Sharing a copy](#sharing-a-copy)): it copies only the engine and checks for anything private.

## What you need

- **Claude** desktop app (Code tab) or Claude Code, on a paid plan (connectors need one).
- **Python 3.11+.** Standard library only, so there's nothing to `pip install`. Tested on Python 3.14 / Windows 11.
- **Accounts:** a free Indeed account, plus an optional free Crunchbase account. Nothing else. See [Connectors](#step-4-connect-the-job-sites).

## Step 1: Get the kit

Clone the repo (or download and unzip it) into a folder of your own, e.g. `Documents/job-search/`. Your own files go in that same folder; `.gitignore` keeps them out of git, so you can still pull kit updates later.

## Step 2: Run the installer

From the kit folder:

```bash
python -I job-finder/install.py
```

It:
- checks Python;
- creates `profile/` and `samples/` from the templates (it never overwrites a file you've filled in) and an empty `job-finder/state/`;
- registers the local MCP server (`.mcp.json`) and the report preview (`.claude/launch.json`) with this computer's paths.

If you open Claude sessions in a different folder than the kit, add `--project <that folder>`. Use `--dry-run` to see the changes first.

Each profile file says what goes in it and how Claude uses it. The guide is [templates/profile/README.md](templates/profile/README.md).

## Step 3: Gather your inputs

**Drop these files in (Claude reads them):**

| Input | Where it goes | Why |
|---|---|---|
| **Your current resume** (PDF or DOCX) | `samples/` | Claude mines it into `profile/roles/` and `profile/bullet-bank.md`. |
| Older resumes and versions tuned for different roles | `samples/` | More raw accomplishments. Bullets that were cut often come back. |
| Past cover letters | `samples/cover-letters/` | **The best source for your voice.** Claude drafts new letters to sound like these. |
| Your LinkedIn profile (copy-paste the text, or LinkedIn's "Save to PDF") | `profile/linkedin-current.md` | Current headline, about section, titles. |
| Recommendations, reviews, kudos | `samples/recommendations/` | Quotable proof, plus how others describe you. |
| Personal or side projects | `profile/personal-projects.md` | Builder signals that formal history may not show. |

**Then Claude interviews you** to fill in [targets.md](templates/profile/targets.md), [search.md](templates/profile/search.md), and [settings.json](templates/profile/settings.json) (your pay band in numbers, plus private terms). The questions:

1. What's the **highest level** you want, and the lowest you'd take? Manager vs. senior IC?
2. Which **titles** fit, and which adjacent directions are you open to?
3. Which **domains and industries** do you bring? Any to avoid?
4. What **size and stage** of company? Startup, growth, enterprise?
5. Where do you live, what do resumes list, and do you want **remote, hybrid, or onsite**?
6. **Pay:** what did you make, what's realistic, and what's your floor? Does the floor drop for a great fit, or for a specific company?
7. **Deal-breakers** (industries, travel, on-call, relocation…)?
8. What kind of work **lights you up**, beyond your formal background? (Hobbies and side builds count: they're often where the best-fit roles hide.)
9. **Anything never to mention**: a gap, a short stint, a confidential customer. Claude keeps these out of every document.
10. **Title or framing decisions**: e.g. which of two titles to show for a role. Write these down once so every resume is consistent.
11. Which **companies** would you love to work for? (They become the job-board watchlist.)
12. Which words should **never** show up if you share this kit later (your last name, employers, email)? They go in `private_terms`.

Claude then drafts `profile/roles/*.md` and `profile/bullet-bank.md` from your resumes, and you review them. **Too much detail is good.** Tailoring means choosing what to leave out.

## Step 4: Connect the job sites

In the Claude app: **Settings → Connectors**, then search the directory for each one. You sign in yourself. Claude never creates accounts or signs in for you.

| Connector | What Claude uses it for | Account? | Notes |
|---|---|---|---|
| **Indeed** | Job search, full job details, **company data** (ratings, reviews, size, pay, culture) | **Free Indeed account.** It may ask for a resume to finish your profile. You can keep it private and change it later. | The best company data. Search relevance is loose, so expect some noise. |
| **ZipRecruiter** | Job search | **None** for the connector. A ZipRecruiter account isn't needed and its profile setup doesn't matter. | 5 results per call, loose relevance. Apply links are short-lived redirects. |
| **Dice** | Job search, job details, company profiles | **None** | Strong for engineering and tech roles. Mostly contract and recruiter listings for product roles: filter to direct-hire, full-time. |
| **Crunchbase** (optional) | Funding, stage, headcount, growth, layoffs, news | Free Crunchbase account | The free tier has a monthly data budget. Claude should request specific fields, not full profiles. |

Built into the kit's local MCP server, so **no account or connector is needed** for these:

| Source | How |
|---|---|
| **LinkedIn** | The public logged-out job feed: search plus full postings with salary and applicant counts. The best source in testing. Paced and capped by the guard. |
| **Company job boards**: Greenhouse, Lever, Ashby | Their public job-board APIs. Finds roles the big sites miss. List companies in `profile/search.md`. |

**Considered and skipped:**
- **Glassdoor:** heavy anti-bot measures, and automating a logged-in account is too close to working around their protections. Claude uses web search for employee sentiment instead (Reddit, Blind, news), weighed with a grain of salt.
- **Enterprise data tools** (CB Insights, D&B Hoovers): too expensive.
- **Third-party LinkedIn MCP servers** that use your login cookie: they put your account at risk.

## Step 5: Turn on the local MCP server

Start a new Claude session in the project folder and approve `job-finder` when asked. (Step 2 registered it.) Claude now has the job-finder tools: LinkedIn search and postings, company job boards, seen-tracking, the review queue, the job store (including research gaps and company one-pagers), and the log. See [job-finder/README.md](job-finder/README.md#mcp-server).

## Step 6: Check your settings

```bash
python -I job-finder/guard/settings.py
```

It shows what the code will use: your pay band, stale age, test mode, private terms, and the keywords and locations from `search.md`. The report's pay colors and range bar come from the pay band.

## Step 7: Test before the first real run

```bash
python -I job-finder/guard/test_polite.py
```

```bash
python -I job-finder/guard/test_settings.py
```

```bash
python -I job-finder/guard/polite.py
```

```bash
python -I job-finder/tests/live_linkedin_smoke.py
```

These are, in order: offline guard tests (no network); offline settings tests; today's request counts, caps, and cooldowns; and a live check (1 LinkedIn search plus 1 posting, a minute or so apart, using your first keyword and location). Watch any run as it happens with `python -I job-finder/guard/watch.py`.

## Step 8: First run

Ask Claude: *"Run the job finder per job-finder/PLAYBOOK.md."* Then open the report. On Windows:

```bash
powershell -ExecutionPolicy Bypass -File job-finder\report.ps1
```

This starts the report server in the background (no window) if it isn't already running and opens http://127.0.0.1:8765. The server keeps running until you log off or restart; `-Stop` stops it. On Mac/Linux, run `python3 -I job-finder/app/server.py` and open the URL. In the Claude desktop app, the "job-report" preview (also set up by the installer) opens it in the browser pane, but that copy stops when the session's preview closes.

Only the report page needs the server. The collector, the daily review, and the MCP tools write to the database directly, so they work whether or not the server is running.

**Leave test mode on** (`"test_mode": true` in `profile/settings.json`: LinkedIn capped at 6 requests a day) for the first few days, until the logs look healthy.

## Step 9: Turn on the daily loop

Once a manual run looks right:

1. **Background collection.** In your own PowerShell window (not through Claude), from the kit folder:

   ```bash
   powershell -ExecutionPolicy Bypass -File job-finder/schedule-collector.ps1 -Time 07:00
   ```

   It registers a daily Windows task that runs `collect.py` as you, with no window, plus a random start delay. On Mac/Linux, use the cron line in that script instead. Try `python -I job-finder/collect.py --plan` to see what a day's collection will do.

2. **Daily review by Claude.** In the Claude desktop app, ask Claude to create a scheduled task for the daily review. It's a task running in the kit folder each day a few hours after collection, with the prompt *"Run the daily review in job-finder/PLAYBOOK.md."* Use "Run now" once to approve its tools. Scheduled tasks run while the app is open; a missed one runs when the app next opens.

3. **Resume drafts by Claude.** A second scheduled task, every two hours in the daytime (for example cron `0 8-20/2 * * *`), with the prompt *"Run the resume-drafts task in job-finder/PLAYBOOK.md section 8."* It drafts a tailored resume for each job you mark Interested, and exits at once when there's nothing to do. Needs Step 10 first.

Claude records each schedule with `setup_mark` (including its cron), so the app's status line shows when the next collection, review, and drafts run happen.

Then the app fills in every day. New jobs carry a **New** chip, and the status line shows the latest review summary and how many resume drafts are ready.

## Step 10: Pick a resume style

Ask Claude to draft `profile/resume.json` from your experience bank. Then build the gallery:

```bash
python -I resume-builder/build.py
```

It renders your content in every style (Modern, Executive, Classic, Builder) as HTML and PDF, plus `resumes/styles/index.html` to compare them side by side. All styles are single-column and parse-safe. Pick one (it goes in `profile/settings.json` as `resume_style`), settle the content decisions with Claude (headline, summary, title framing, projects, page count), and that becomes the base every tailored resume starts from. Details, and what to expect from generated resumes: [resume-builder/README.md](resume-builder/README.md).

## Sharing a copy

If you change the engine and want to share your version:

```bash
python -I job-finder/package.py --out ../job-search-kit --zip
```

It builds a copy of only the engine (and a zip), and scans every file for your home folder path and your `private_terms` first. If anything matches, it writes nothing and lists the lines to fix. Point `--out` at a git repo from an earlier run and it refreshes that repo in place, ready to commit. Unemployment rules differ by state, so the kit carries no state-specific notes.

## Still to build

- [ ] **Resume DOCX output and tailoring command** (PDF styles are built), then cover letters.
- [ ] **Job alert emails** as a source (needs a mail connector).
- [ ] **A test with a second person's profile**, to catch assumptions that only fit one search.
