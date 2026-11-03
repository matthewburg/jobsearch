# Job Search Kit: instructions for Claude

This folder is a job-search kit run with Claude: a daily job finder (collector, request guard, scoring, local report), an experience bank, and a resume builder. The code is shared and generic. Everything about the person using it lives in folders git ignores.

## First session: set the person up

If `profile/` doesn't exist, or its files are still the blank templates, this is a new setup. Before anything else:

1. Say what the kit does in a few sentences (SETUP.md, "What it does"), and the hard rules below.
2. Follow [SETUP.md](SETUP.md) step by step with them: run the installer, gather their resumes and other inputs, then **interview them** (Step 3 has the questions) and fill in `profile/` together. Ask a few questions at a time, not all twelve at once. Draft the experience bank from their resumes and have them review it.
3. Then connectors, tests, a first run, the base resume, and the scheduled tasks (Steps 4–10).
4. Open the app for them (`job-finder/report.ps1` on Windows) and point them at its **Setup** page: it shows every step and what's next.

**Check steps off only after verifying them**, with the `setup_mark` tool: tests actually passed, they approved their profile, a scheduled task exists and its first run worked. Schedule steps include the cron, so the app can show the next run. The app keeps the job list closed until the required steps are done, so never mark one early.

Go at their pace. Setup can span several sessions; `setup_status` shows where they are.

## Every session after that

- **Read `profile/` before any job or resume work:** `targets.md` (what they want, pay, deal-breakers, the never-mention list), `search.md`, `resume-notes.md` (decisions already made), and the experience bank.
- **Job search:** [job-finder/PLAYBOOK.md](job-finder/PLAYBOOK.md) is the procedure for daily runs, scoring, report cards, and company one-pagers. Report: http://127.0.0.1:8765 (`job-finder/report.ps1` on Windows).
- **Resumes:** the base (source of truth) is `profile/resume.json`, rendered by [resume-builder/](resume-builder/README.md). Tailored drafts live in `resumes/<job>/` and follow PLAYBOOK section 8. When they ask to change a draft ("revise my resume draft for Acme…"), use `resume_draft_get`, edit, and `resume_draft_save` with a revision-log entry. The app shows the result right away.
- **The app** (http://127.0.0.1:8765) is their window into all of this: jobs, resume drafts, their profile files, an activity log of everything found and filtered out, and setup. When they mention something they saw there, the same data is in the job-finder tools.
- **Tools:** the `job-finder` MCP server (registered by the installer) for LinkedIn's logged-out feed, company job boards, and the job store. See [job-finder/README.md](job-finder/README.md).

## Hard rules

- **Never apply to a job, submit a form, create an account, sign in anywhere, or contact anyone.** Gather, research, and draft; the person reviews and acts.
- **LinkedIn is logged-out only**, through the job-finder tools. Never use their account.
- **Every request goes through the guard** (`job-finder/guard/polite.py`). If it refuses or a site pushes back, stop that source for the day. No CAPTCHA solving, proxies, or stealth tricks.
- **Never claim experience they don't have.** Respect their never-mention list in every document.
- **Their data never enters git.** `profile/`, `samples/`, `resumes/`, `job-finder/state/`, and the installer's config files are ignored. Never add them, and never put personal details in engine files (code, docs, templates). `job-finder/package.py` scans for their `private_terms` when building a copy to share.
