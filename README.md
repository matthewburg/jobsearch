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

## How you use it: by talking to your AI

This isn't an app you click through on your own. **You work with an AI partner, and the AI does the file and tool work.** In practice:

- **You talk; it does the work.** "Lead with the AI work on the Acme resume." "Make it one page." "Why did this job score low?" "Tell me more about this company." "I applied to Acme today." You shouldn't need to edit files or run scripts. The few exceptions (like registering a background task in your own terminal) are spelled out when they come up.
- **It learns from your corrections.** When you fix a fact or a phrasing on a resume, the AI records the decision and the reason, adds a check so the old wording can't come back, fixes your base resume, and updates every existing draft. You correct something once, not once per resume.
- **Your choices tune the search.** Dismiss a job with a reason, mark one Interested, or rescue a listing it filtered out, and the next day's review takes that into account. When a pattern shows up, the AI suggests updating your targets rather than quietly drifting.
- **It explains as you go.** The AI is told to show you what you can do at the moment it's useful (marking jobs, revising drafts, checking how to apply), so you don't have to read the docs first.
- **You decide and act.** It researches and drafts. You review, apply, and reach out yourself.

## Which AI it needs

**It's built for Claude, and works best there**: the Claude desktop app (Code tab) or Claude Code, on a paid plan. Every instruction in it was written and tested with Claude.

**Any AI agent with the same abilities should work.** The instructions are plain markdown ([CLAUDE.md](CLAUDE.md), with [AGENTS.md](AGENTS.md) pointing other agents to it), and the tools are a standard MCP server. The agent needs to:

| Ability | What it's used for | Required? |
|---|---|---|
| **Work in a local folder**: read and write files and run commands (Python) | Setup, the profile, resume builds, tests | Yes |
| **Custom (local) MCP servers** over stdio | The kit's `job-finder` server: LinkedIn's public feed, company job boards, the job database, resume drafts, setup tracking | Yes |
| **Scheduled tasks / routines**: an unattended agent run in this folder on a schedule, with the same tools | The daily review and the resume-drafts task. Without this, you ask for each run by hand. | Strongly recommended |
| **Connectors** (hosted MCP integrations) for Indeed, ZipRecruiter, and Dice; Crunchbase is optional | More job sources, plus company data | Recommended. LinkedIn and company job boards work without them. |
| **Web search and fetch** | Company research, the employer's own posting, news | Recommended |
| **Push notifications** | "3 new strong fits today" | Optional |

Also: **Python 3.11+** (standard library only, nothing to install). The background collector and report launcher have Windows scripts. On Mac and Linux the steps give the equivalent commands.

## Get started

1. Clone or download this repo into a folder of your own.
2. Open a Claude session **in that folder** (the desktop app's Code tab, or `claude` in a terminal there) and say: *"Set this up for me."*

That's the whole start, even if you're a developer: don't run the scripts by hand first. Claude reads [CLAUDE.md](CLAUDE.md) and [SETUP.md](SETUP.md) and does the setup with you, checking off steps in the app as it verifies them. (With another agent, say: *"Read AGENTS.md and set this up for me."*)

Claude walks you through [SETUP.md](SETUP.md): it runs the installer, reads your resumes, interviews you about what you're looking for, and fills in your profile with you. Your profile, resumes, and job database stay on your computer; `.gitignore` keeps them out of git.

## Layout

| Path | What it is |
|---|---|
| [SETUP.md](SETUP.md) | Setup steps, for you and your Claude |
| [CLAUDE.md](CLAUDE.md) | Standing instructions the AI reads every session: how to set you up, how to work with you, and the hard rules |
| [AGENTS.md](AGENTS.md) | Pointer for AI agents other than Claude |
| [job-finder/](job-finder/README.md) | Collector, request guard, job store, report app, MCP server, and the [playbook](job-finder/PLAYBOOK.md) Claude follows |
| [resume-builder/](resume-builder/README.md) | Renders `profile/resume.json` into resume styles |
| [templates/](templates/README.md) | Blank profile files the installer copies into `profile/` |
| `profile/`, `samples/`, `job-finder/state/` | **Yours**, created on setup, never committed |

## License

MIT. See [LICENSE](LICENSE).
