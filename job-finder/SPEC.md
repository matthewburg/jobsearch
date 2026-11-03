# Job Finder: What It Should Do

The outcome that matters is the **daily report**. Sources are interchangeable plumbing. "You" below means the person whose search it is; their details live in `../profile/`.

## Hard rule
**Nothing in this system ever applies to a job, submits a form, creates an account, or contacts anyone.** It gathers information and drafts documents. You review everything and apply yourself.

## Visibility rule
Every component logs what it's doing as it happens, in a readable daily log plus JSON, so runs can be watched live and debugged afterward. See [README.md](README.md#logging-and-visibility-a-rule-for-every-component).

## Personal settings stay in the profile
Pay band, stale age, test mode, keywords, locations, and the company watchlist live in `../profile/` (`settings.json`, `search.md`, `targets.md`), never in code. Anything new that's specific to a person goes there too. See [README.md](README.md#your-settings).

## Local MCP service
The `job-finder` MCP server ([mcp/server.py](mcp/server.py)), registered by `install.py`. See the README for its tools. Same guard, logs, and caps as the scripts.

## The full pipeline (stages, each one validated before moving on)
1. **Collect → report card:** a daily report of candidate jobs (below). Procedure: [PLAYBOOK.md](PLAYBOOK.md).
2. **Pick:** you mark the jobs you like.
3. **Tailor:** each pick kicks off drafts of a **bespoke resume and cover letter** from the experience bank, using a base format and styling agreed on first.
4. **Review:** you review and edit the drafts, then **apply manually**.
5. **Record:** the tracker logs the date, job, posting snapshot, exact documents sent, and how you applied. That gives a complete paper trail for unemployment **work-search logs** (rules vary by state).

## Document tooling (no Microsoft Word needed)
- **Source of truth:** resumes as structured content plus an HTML/CSS template. Render to **PDF** (headless Chrome) and **DOCX** (when an application wants Word). Both come from the same source and regenerate on demand.
- **Viewing and light edits:** Google Docs (free) opens and exports DOCX/PDF. LibreOffice is an optional fallback.
- Format and styling get decided before any tailoring starts.

## Accounts
See [../SETUP.md](../SETUP.md#step-4-connect-the-job-sites). Short version: a free Indeed account; ZipRecruiter and Dice need none; Crunchbase is optional (free); LinkedIn and company job boards need nothing. You do connector sign-ins in the Claude app. Claude never creates accounts or signs in.

## Outcome
Every day, a report you can open showing **a handful or more** of strong candidate jobs, whatever source they came from. Quality over quantity. This is **not** a thousand-posts-a-day pipeline.

## Per-job report card
- **Match score**, with *why* it matches and why it doesn't
- **Which way it leans:** e.g. leadership vs. senior IC vs. technical. Which of your backgrounds it draws on (experience, hobbyist/builder side, domain)
- **Level and title fit** against your targets
- **Salary range** when posted (or estimated, clearly labeled), against your pay band
- **Location / remote / hybrid**
- **Company profile:**
  - what they do, what they stand for, website
  - size and stage (startup / growth / enterprise)
  - funding or ownership if relevant
  - **what employees say** (ratings and reviews)
  - recent news
- **Red flags:** reposted or ghost listings, vague pay, mismatch signals
- Links to the posting and the apply page, plus a **saved snapshot** of the description (postings disappear)

## Tracking
- Each job carries a status: new → interested → applying → applied → interviewing → offer/rejected/ghosted, or **dismissed** (with a reason, which feeds the tuning).
- Never resurface jobs already reviewed or applied to. Dedupe across sources.
- Applied jobs link to the exact resume and cover letter sent.
- Feeds the weekly work-search log.

## Tuning over time
- Your reactions (interested / dismissed + reason) teach the scoring which companies and roles you lean toward.
- Preferences to learn: company **size**, culture and employee sentiment, and fit with your **hobbyist/builder background** even where your formal background is weaker.
- Patterns get proposed as edits to `targets.md` / `search.md`, so the profile stays the source of truth.

## Company data sources (sanctioned first)
- **Indeed connector:** company ratings, reviews, compensation, culture, management (a sanctioned stand-in for Glassdoor)
- **Dice connector** `get_company`: tech company profiles
- **Crunchbase connector** (free tier): funding, stage, investors, headcount, news. Request specific fields; it's metered.
- **Free red-flag checks:** state **WARN notices** and layoff trackers (recent layoffs), **SEC EDGAR** for public companies (free API)
- Company website and careers page (local fetch)
- Web search for recent news, funding, size, and employee sentiment (Reddit, Blind, news), **weighed with a grain of salt**: reviews skew toward unhappy people
- **Skipped:**
  - Glassdoor: heavy anti-bot, and automating a login is too close to working around their protections
  - CB Insights, D&B Hoovers, HG Insights: enterprise-priced

## Collection etiquette (applies to every scraped source, especially LinkedIn)
Principle: **behave like one person checking job sites once a day**, because that's what this is.
- **Low volume:** a few searches plus a few dozen posting pages per site per day, max.
- **One natural session a day, not a cron heartbeat:**
  - start time varies day to day
  - a few searches, open the postings that look relevant, real (varied) time on each page, pauses between pages, then done for the day
- **Read-only:** no applying, messaging, connecting, or profile viewing.
- **LinkedIn logged-out only.** Never a personal account.
- **If a site pushes back** (429s, challenges, CAPTCHAs), back off and switch that source to email alerts. No CAPTCHA solving, fingerprint spoofing, or proxy rotation.
- Honest note: natural pacing is about **courtesy and modest volume**. It isn't meant to disguise anything, and LinkedIn says randomized delays don't fool its detection anyway. **Low volume is what actually keeps this safe.**

## What the LinkedIn logged-out feed gives (and doesn't)
- **Gives:** search by keyword and location, with filters for date posted, remote/hybrid/onsite, experience level, and job type. Each posting gives title, company, location, posted date, the **full description**, seniority, employment type, often the applicant count, and the salary when the employer lists it.
- **Doesn't give:** your network ("who do I know there"), Easy Apply, personalized recommendations, InMail/recruiter features, or premium insights.

## Job alert emails (planned)
- On LinkedIn (and Indeed, ZipRecruiter, Built In, …) you **save a search**, and the site emails you new matching postings.
- Plan: send the alerts to an inbox or label → the collector parses the job links each morning → they go into the same pipeline.
- **Why it's good:** fully sanctioned, uses the site's own personalization, and nothing is scraped.
- **Needs:** a way to read that inbox (a mail connector or IMAP). To be decided.
