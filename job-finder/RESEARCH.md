# Job Finder: Source Research & Architecture Options

Researched 2026-10-30. Nothing is built yet. Goal: a robust, mostly automated system that collects postings (title, company, link, full description, comp, location/remote), lets Claude curate them against `../profile/targets.md`, and produces a daily summary that we tune over time.

## Key insight: "local" is mostly already true
- Anything Claude Code runs through **Bash / PowerShell / Playwright runs on your own machine, from your IP**: `curl`, Python scripts, a headless browser. Only the built-in `WebFetch` / `WebSearch` tools go out through Anthropic's infrastructure, and those are the ones that get "no AI bots" blocks (e.g. Cloudflare's default AI-crawler setting).
- So the plan is sound: **collectors run locally on a schedule, write files, and Claude reads the files.** No Anthropic IPs ever touch the job sites.

---

## Tier 1: Official MCP connectors (no build; available in the Claude connector directory)

| Source | Connector | Tools | Notes |
|---|---|---|---|
| **Indeed** | Official, beta (`mcp.indeed.com`) | `search_jobs`, `get_job_details` (+ resume and company data per Indeed docs) | Sign in with an Indeed account. Returns full descriptions, salary, apply URLs, company ratings. [docs](https://docs.indeed.com/mcp/) |
| **ZipRecruiter** | Official (`api.ziprecruiter.com/mcp`) | `search_jobs` | May ask for a (free) ZipRecruiter sign-in |
| **Dice** | Official (`mcp.dice.com`) | `search_jobs` | Tech-focused. Reportedly **no sign-in required**. |
| ~~LinkedIn~~ | Only "LinkedIn Hiring Pro" (for *posting* jobs) | — | **No official job-search connector.** |

- **Pros:** sanctioned, structured, zero maintenance, works today. Usable interactively *and* from a scheduled Claude task.
- **Cons:** each covers only its own board. Rate limits are undocumented. Indeed is still beta.
- **Cost:** all free for job seekers. Indeed needs a free Indeed account. Connectors require a paid Claude plan.
- **Action:** connect these three first. They cover a big share of the market for free.

## Tier 2: Public JSON endpoints (plain HTTP, no browser needed)

Best for a **target-company watchlist**: the most reliable, freshest data, straight from the source.

| Source | Endpoint | Notes |
|---|---|---|
| **Greenhouse** | `boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true` | Documented public API |
| **Lever** | `api.lever.co/v0/postings/{slug}?mode=json` | Returns a bare array; `createdAt` in ms |
| **Ashby** | `api.ashbyhq.com/posting-api/job-board/{slug}?includeCompensation=true` | Includes remote flag and comp |
| **Workday** | `POST {tenant}.wd{N}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs` (JSON body: limit/offset/searchText) | Undocumented but widely used. Many large companies use Workday. Retry on 429. |
| **SmartRecruiters / Workable** | Public widget endpoints exist | Workable's are intended for the employer's own site |
| **Recruitee** | Requires the employer's token from Feb 2027 | Skip |
| **Adzuna** | Free API key, ~1,000 calls/mo | Aggregator, US coverage, salary data |
| **USAJOBS** | Free API key | Federal roles (if the government track comes back) |
| **HN "Who is Hiring"** | Algolia HN API, monthly thread (1st of the month) | Startup/tech roles, often small companies. **A good fit for "smaller company, hands-on"** |
| Remotive / The Muse / Jooble | Free / key-gated | Thin coverage. Optional extras. |

- A 404 from an ATS board means "not hosted there," which is different from "no jobs."

## Tier 3: Local headless browser (for JS-heavy or protected sites)

For sites with no connector and no API: **LinkedIn, Wellfound, Built In, Glassdoor, Otta/Welcome to the Jungle, arbitrary company career pages.**

**Options, roughly from least to most build:**
1. **JobSpy** (`python-jobspy`, open source, ~4k★): one `scrape_jobs()` call across LinkedIn, Indeed, Glassdoor, ZipRecruiter, and Google Jobs → a normalized table. MCP wrappers exist (`jobspy-mcp`). It uses plain HTTP, not a browser, so LinkedIn throttles it quickly. A quick win to evaluate before building anything.
2. **Microsoft Playwright MCP** (`npx @playwright/mcp`): an off-the-shelf local browser that Claude drives. Supports `--headless` and a **persistent profile** (`--user-data-dir`), so sites see your real logged-in session. Good for ad-hoc browsing. Too chatty and token-heavy for bulk collection.
3. **Our own small "fetch page" service plus an MCP** (the preferred design): a local Playwright worker with one persistent browser profile, exposed as MCP tools like `fetch_page(url) → clean text + links` and `search_site(site, query) → postings`. It returns *extracted text*, not screenshots, so it's fast and cheap, and the same worker powers the scheduled collectors. A general local scraping service could share the same worker.
4. *(Avoid)* Claude in Chrome / computer use for collection: slow and cumbersome. Keep it for one-off manual tasks.

**Site notes:**
- **LinkedIn:** no API. A **public guest endpoint** works without login (`/jobs-guest/jobs/api/seeMoreJobPostings/search?keywords=…&location=…&start=0`, 25 per page; detail at `/jobs-guest/jobs/api/jobPosting/{id}`). It returns HTML fragments and throttles with 429 after roughly 50–100 rapid requests. **LinkedIn's ToS prohibit automated access, and they ban accounts.** Recommendation: use the guest endpoint (no account at risk) at a gentle daily volume, and/or parse **LinkedIn job alert emails**. **Never automate the logged-in main account.**
- **Wellfound:** **skipped**. It also uses DataDome bot protection. General rule: skip any site that fights us. **No CAPTCHA-solving or evasion tooling.**
- **Glassdoor:** heavy anti-bot. JobSpy covers it partially. Low priority, since Indeed/ZipRecruiter overlap.
- **Built In:** regional tech boards (incl. Built In Seattle and remote). Worth a test fetch.

**Ground rules for Tier 3:** read-only, low frequency (once a day), human-like pacing, respect blocks (if a site challenges us, switch that source to email alerts rather than escalating), and never auto-apply.

### LinkedIn risk, in more detail (researched 2026-10-30)
- **What LinkedIn actually goes after** (from its lawsuits and public statements): commercial scrapers running **fake accounts at scale** (Proxycurl was sued in Jan 2025 over hundreds of thousands of fake accounts and shut down mid-2025; ProAPIs was sued in Oct 2025 over 1M+ fake accounts), plus outreach automation (mass connection requests and messages).
- **What gets real accounts restricted** (vendor reports, no official thresholds): **unusual page-view velocity** (e.g. "viewed too many profiles"), sudden spikes in activity, browser automation extensions, shared/VPN IPs. LinkedIn says randomized delays don't fool its detection. It usually escalates in steps: friction → ID check → temporary restriction → ban.
- **This use case** (read job postings once a day, no applying, no messaging, no profile views) is far from what they target. **The risk isn't zero, though:** the terms ban *any* automated access, and detection works on behavior, not intent. During a job search the main account is too valuable to gamble with.
- **So:**
  1. The **logged-out guest endpoint** carries no account risk. The worst case is a temporary IP throttle (429). Keep it to a few dozen requests a day.
  2. **Job alert emails** are fully sanctioned.
  3. If logged-in access ever matters (e.g. "who do I know at this company"), do that by hand.
  4. **Never** automate the logged-in account.
- Sources: [LinkedIn legal action (2025)](https://news.linkedin.com/2025/linkedin-takes-legal-action-to-defend-member-privacy) · [ProAPIs suit](https://cybermaterial.com/linkedin-sues-proapis-over-fake-accounts) · [ban triggers (vendor)](https://getsales.io/resources/the-linkedin-ban-triggers-checklist/) · [safety 2026 (vendor)](https://grinfi.io/leadgen-school/linkedin-account-safety-2026-what-actually-triggers-bans)

## Tier 4: Email job alerts (low risk, decent coverage)
- LinkedIn, Wellfound, Built In, Otta, and Google all send saved-search alert emails. Point them at a dedicated inbox or label and parse them daily. This sidesteps bot protection entirely. Needs a mail connector or IMAP access (TBD).

---

## Proposed architecture (to discuss)

```
                ┌─ Tier 1: Indeed / ZipRecruiter / Dice MCP (called by the Claude review task)
Daily schedule ─┼─ Tier 2: ATS watchlist + Adzuna + HN (Python, local HTTP)
(Task Scheduler)├─ Tier 3: local Playwright worker → LinkedIn guest, Built In, career pages
                └─ Tier 4: alert-email parser
                        │
                        ▼
          normalize → SQLite (dedupe by URL/company+title, track first-seen, snapshot postings)
                        │
                        ▼
   Claude review (scheduled task): score each new posting against targets.md
   → "strong / maybe / skip" + one-line reason, salary, remote, red flags
                        │
                        ▼
   Daily report (markdown in Obsidian and/or an artifact page) → you mark interest
   → feedback tunes the scoring → shortlisted roles flow into the tracker
     (which also produces the weekly work-search log)
```

**Build order suggestion:** (1) connect the Tier 1 connectors and run a few manual searches to *see what roles exist*; (2) Tier 2 watchlist script + SQLite; (3) Claude review + daily report; (4) Tier 3 Playwright worker for LinkedIn and the rest; (5) email alerts.

## Open questions
- Which titles/keywords to search, given the "see what exists" phase? (Start broad: the target titles plus adjacent ones.)
- Remote only, or also local hybrid/onsite?
- A target-company list for the ATS watchlist?
- Build the Playwright worker standalone in `job-finder/`, or as the web-scraper-service?
- Report destination: Obsidian markdown, an artifact page, or email/phone notification?
- An inbox for alert emails (a dedicated Gmail?)

## Sources
- [Indeed MCP docs](https://docs.indeed.com/mcp/) · Claude connector directory (Indeed, ZipRecruiter, Dice)
- [JobSpy MCP server](https://github.com/borgius/jobspy-mcp-server) · [python-jobspy](https://pypi.org/project/python-jobspy/1.1.45) · [stickerdaniel/linkedin-mcp-server](https://github.com/stickerdaniel/linkedin-mcp-server) (uses your LinkedIn cookie, so the account is at risk)
- [Greenhouse/Lever/Ashby/Workable endpoints](https://dev.to/neverempty/greenhouse-lever-ashby-workable-4-job-apis-1-dangerous-bug-5b5h) · [Workday JSON API](https://dev.to/udaninn/workday-job-boards-have-a-json-api-too-its-just-better-hidden-23fl)
- [LinkedIn guest endpoint (2026)](https://dev.to/agenthustler/how-to-scrape-linkedin-job-listings-in-2026-public-data-without-login-5094)
- [Free jobs APIs overview](https://jobspipe.dev/free-jobs-api) · [Adzuna](https://public-api.org/api/850/adzuna)
- [Wellfound uses DataDome](https://securityboulevard.com/2025/08/33-less-bot-traffic-lower-costs-how-wellfound-gains-time-tranquility-with-datadome/)
- [Playwright MCP flags (mirror)](https://archestra.ai/mcp-catalog/microsoft__playwright-mcp)
- [HN Who is Hiring via Algolia](https://www.ctaio.dev/en/job-portals/hacker-news-who-is-hiring/)
