# Job Search Kit

A job search you run with Claude. Every day it finds new postings, researches and scores each one against your background, and shows the results in a local report. It also keeps your experience in one place and renders it into clean, parse-safe resumes.

**It never applies, signs in, or contacts anyone.** It gathers information and drafts documents. You decide and apply yourself.

## What you get

- **A daily job finder.** A background collector reads LinkedIn's public job feed and company job boards (Greenhouse, Lever, Ashby) at a human pace, behind a strict request guard. Claude reviews what it found, searches the Indeed, ZipRecruiter, and Dice connectors, and writes a report card for each keeper: fit score, why it fits, concerns, pay against your range, resume advice, and ghost-listing checks.
- **A local app** at http://127.0.0.1:8765, your window into the whole system:
  - **Jobs:** sorting, filters, a tracker (interested → applied → interviewing), links to the employer's own posting, and a one-page company profile for the jobs you care about. Dismiss reasons tune later scoring.
  - **Documents:** a tailored resume draft for every job you mark Interested, with notes on what changed and why. To revise one, just tell Claude.
  - **Profile:** read and edit your experience bank right in the app.
  - **Activity:** everything the system found, what it kept, and what it filtered out and why. Rescue anything it shouldn't have skipped.
  - **Setup:** what's done, what's next, and when each scheduled run happens.
- **An experience bank**: your roles, accomplishments, and decisions in plain files that every resume and cover letter draws from.
- **A resume builder** with four single-column, ATS-safe styles (HTML and PDF).
- **A paper trail** of every status change, handy for unemployment work-search logs.

## Get started

You need the Claude desktop app (Code tab) or Claude Code on a paid plan, and Python 3.11+ (standard library only, nothing to install).

1. Clone or download this repo into a folder of your own.
2. Open a Claude session **in that folder** (the desktop app's Code tab, or `claude` in a terminal there) and say: *"Set this up for me."*

That's the whole start, even if you're a developer: don't run the scripts by hand first. Claude reads [CLAUDE.md](CLAUDE.md) and [SETUP.md](SETUP.md) and does the setup with you, checking off steps in the app as it verifies them.

Claude walks you through [SETUP.md](SETUP.md): it runs the installer, reads your resumes, interviews you about what you're looking for, and fills in your profile with you. Your profile, resumes, and job database stay on your computer; `.gitignore` keeps them out of git.

## Layout

| Path | What it is |
|---|---|
| [SETUP.md](SETUP.md) | Setup steps, for you and your Claude |
| [CLAUDE.md](CLAUDE.md) | Standing instructions Claude reads every session |
| [job-finder/](job-finder/README.md) | Collector, request guard, job store, report app, MCP server, and the [playbook](job-finder/PLAYBOOK.md) Claude follows |
| [resume-builder/](resume-builder/README.md) | Renders `profile/resume.json` into resume styles |
| [templates/](templates/README.md) | Blank profile files the installer copies into `profile/` |
| `profile/`, `samples/`, `job-finder/state/` | **Yours**, created on setup, never committed |
