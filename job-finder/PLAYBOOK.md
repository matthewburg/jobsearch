# Job Finder Playbook (how Claude runs a search)

The procedure Claude follows for a daily run, written for anyone's profile. The person's details come from `../profile/`. Nothing in this file is specific to one person.

Ask Claude: *"Run the job finder per job-finder/PLAYBOOK.md."*

## Never

- Apply, submit a form, sign in, create an account, message anyone, or connect on any site.
- Use the person's LinkedIn account, or any site outside the guard's allowlist.
- Retry after the guard refuses a request or reports pushback. Stop that source for the day and say so.
- Make up a salary. If it isn't listed, estimate it and label it an estimate.

## How the daily loop works

| Part | Who | When | What |
|---|---|---|---|
| **Collect** | [collect.py](collect.py), no Claude | Daily, scheduled by the OS (`schedule-collector.ps1`), with a random start delay | One human-paced session through the guard: due LinkedIn searches (rotated), full postings for promising new listings, every watchlist job board. Everything goes into `seen`; new listings and their details wait in `listings`. |
| **Review** | Claude, as a scheduled task in the desktop app | Daily, a few hours after collection | Triage the queue, search the connectors, research, score, save. The report grows; nothing is replaced. Record a summary and send a notification. |
| **Drafts** | Claude, as a second scheduled task | Every couple of hours in the daytime | Tailored resume drafts for jobs the person marked Interested (section 8). Exits at once when there's nothing to do. |
| **Read** | You | Whenever | Open the app. Home shows the last review, drafts ready, when each schedule runs next, and charts of the intake; new jobs carry a **New** chip. |

The two halves don't need each other's timing: a review works with whatever has been collected so far, and anything it doesn't get to waits for the next one.

## Daily review (the scheduled task runs this)

**Save as you go: a review can end without warning** (usage limits, a timeout). Save each job as soon as it's scored, with `gaps` listing every piece of research not done yet (`description`, `employer_posting`, `salary`, `sentiment`, `news`, `company_profile`), each with a short `why` ("review ran short", "LinkedIn cap reached", "not on the careers site"). Remove a gap only once it's done. Never write "not checked" into a card field; a gap says it instead, and the report shows it as "Research in progress". The next review picks up whatever is left.

1. Do section 1 (read the profile, `guard_status`, past dismiss reasons). Then `review_queue` and check `recent_runs`: did the collector run, and did it stop early (cap, cooldown, pushback)? Note it for the summary.
2. **Finish what the person marked.** `jobs_incomplete` lists open jobs with gaps, marked jobs (interested and later) first. Fill every gap on the marked ones now, one-pager included (section 7). They asked to know more. An `apply_details` gap means `apply_check` hasn't run: call it (read-only) so the card shows whether a cover letter is asked for, the answers to have ready, and any instructions (time zone, assessment, portfolio). If the form can't be read (Ashby, Workday, LinkedIn) and you learn something by reading the posting or form page, pass it as `notes`.
3. **Connector searches** (these can't run in the background): Indeed, ZipRecruiter, and Dice, 2–3 searches each from `search.md`, posted in the last few days. Call `seen_check` on each result list and treat the new ones like queue items.
4. **Triage every item** (section 3 below). Each one ends up either:
   - `job_save` (merging into an existing job when `job_id` is set), or
   - `seen_skip` with a reason.
5. **Research, score, and write cards** for the keepers (sections 4–6). For every keeper, look for the employer's own posting (section 4). If a promising LinkedIn item has no description and the employer's posting can't be found, use `linkedin_posting` while the guard allows (the collector leaves a small reserve).
6. **One-pagers** (section 7) for new jobs scoring 60 or more, if the company doesn't have a current one (`company_get`).
7. **Backfill with what's left.** Work down `jobs_incomplete` (highest score first) until the review has done a reasonable day's work.
8. `review_done` with a two-or-three-sentence summary and counts: `{reviewed, saved, skipped, connector_searches, backfilled, one_pagers, still_incomplete, top: [job ids]}`.
9. **One notification** (PushNotification, under 200 characters): new strong fits and the top one, e.g. "Job report: 3 new strong fits. Top: Principal PM at Acme (82)". Send it on a quiet day too, so you know it ran.

If the queue is longer than one review can handle well, do the newest first, leave the rest unreviewed for tomorrow, and say how many are waiting.

## 1. Before collecting

- Read `../profile/targets.md` (level, roles, pay, company preferences, deal-breakers) and `../profile/search.md` (searches, title net, locations, watchlist, noise).
- Skim the experience bank (`../profile/roles/`, `bullet-bank.md`, `personal-projects.md`) so the fit reasoning is concrete.
- `guard_status`: see how many LinkedIn and job-board requests are left today.
- `jobs_list`: know what's already in the store. Read the **dismissed reasons** and **interested** picks. They're the person's taste and should shift today's scoring.

## 2. Collect: a wide net, fetched once

*The background collector does this every day. The rules below are what it follows, and what to follow for a manual run.*

**Wide net, precise afterward.** It's better to fetch too much than to miss a good job because a search didn't use its exact title. The sites match loosely, the title net is broad, and Claude does the real matching when scoring. The constraint is the **request budget**, not fuzziness, so spend requests on *new* listings:

- **Every listing is remembered.** `linkedin_search` and `ats_jobs` mark each result `seen` / `job_id` automatically. Call `seen_check` right after every connector search (Indeed, ZipRecruiter, Dice). Don't fetch details for, or re-review, anything already seen unless something changed (a new source, pay now listed).
- **Rotate searches.** Run the first three searches in `search.md` every run. Rotate the rest so each one runs at least every 3 days. Check the log (`log_tail`, or the `seen` events) for which ran last.
- **Backfill once, then go daily.** On the first run use `posted_within_days` 30. After that use 2: one day of overlap, and almost everything returned is new.
- **Page when it pays.** If more than half of a page is new, fetch the next page (`start` += 10) for that search.
- **Full postings only for promising new cards.** Search cards already give title, company, location, date, and sometimes pay. That's enough to triage most listings.

| Source | Budget per run (test mode: LinkedIn 6/day) | Budget per run (normal: LinkedIn 40/day) |
|---|---|---|
| LinkedIn `linkedin_search` | 2 searches | 8–12 searches, including second pages |
| LinkedIn `linkedin_posting` | up to 4 | up to ~25 |
| Indeed, ZipRecruiter, Dice connectors | 2–3 searches each | 3–5 searches each |
| Company boards (`ats_jobs`) | every watchlist company (one request each; the board cap is 10/day) | same |

`seen_stats` shows new listings per source per day. If a source keeps returning mostly-seen listings, add searches or a location. If it returns many new ones, page deeper. Mention a thin day in the wrap-up.

## 3. Triage

- **Skip, and record it:** clearly wrong field (a pharmacist for a product search), wrong level by two or more steps, a deal-breaker. Call `seen_skip` with a short reason, so later runs don't spend effort on it again.
- **When in doubt, keep it.** Save borderline jobs with a low score so the person can see why they rank low (e.g. pay just under the floor, an unusual title for the right work, an unverifiable company).
- **Already in the store** (`job_id` set): don't resurface it unless a new source adds information (pay, an earlier posting date). `job_save` merges duplicates automatically.

## 4. Research each candidate

- **The employer's own posting** (every keeper). Job boards repost; the company's careers page is the real thing, often has the full description, and its absence is a ghost-listing signal.
  - If the company is on Greenhouse, Lever, or Ashby, `ats_jobs` with its board slug, a title keyword, and `include_description`.
  - Otherwise web search `"<company>" careers "<title>"`, then fetch the posting. Many careers sites (Workday, iCIMS, custom) need JavaScript; save the URL even when the text can't be read.
  - Save it as a source: `{source: "company", source_id: <its job id, or the URL>, url}`. The report shows it first, as "Company posting".
  - Use its description when it beats what the board gave you, and re-score if it changes the picture (for example a search-card-only score).
  - Not found: a gap `employer_posting` with why (it may be closed or recruiter-only).
- **Board links must open the job.** Save the posting's own URL, never a search-results URL. If a connector only gives a search link or a short-lived redirect, still save it (the report labels it "search results") and find the employer's posting.
- **The posting:** full description, salary, posted date, applicant count, deadline, workplace (remote / hybrid / onsite).
- **The company:**
  - what it does
  - size and stage
  - funding or ownership
  - recent news, layoffs, and WARN notices
  - employee sentiment
- **Where to look:**
  - Indeed `get_company_data`
  - Crunchbase (pass specific `field_ids`; the free tier is metered)
  - Dice `get_company`
  - web search
- **Weigh sentiment with care:** reviews skew toward unhappy people.
- **Ghost-listing checks:**
  - earliest posting date across sources (45+ days is stale)
  - reposts
  - a far-off or missing deadline
  - a company that can't be verified
  - a recruiter listing with no named client
- **Note data problems** in `company_info.data_notes`, e.g. a connector returning another company's description.

## 5. Score (0–100)

| Part | Weight | What to judge |
|---|---|---|
| Role and level | 30 | Title and scope versus the target level. Flag over-leveling (VP at a big company) and under-leveling. |
| Background match | 25 | Domain, skills, and accomplishments the person can actually claim, from the experience bank. |
| Pay | 15 | Apply the rules in `targets.md`: below floor is a strong negative unless the fit is exceptional; in range is neutral to positive. |
| Company | 15 | Size, stage, sentiment, mission, stability, against the stated preferences. |
| What lights them up | 10 | Builder, hobby, and "loves this" signals from the profile (e.g. AI tooling, hands-on work). |
| Listing health | −15 to +5 | Penalize stale, ghost, or unverifiable listings. A small bonus for fresh postings with few applicants. |

Labels (the report colors use the same bands):
- **70+: Strong** (green; counted as "strong fits")
- **45–69: Worth a look** or **Stretch** (amber)
- **Under 45: Weak** (red)

## 6. Write the report card and save it

Call `job_save` with:

- **Basics:**
  - `title`, `company`, `location`, `workplace`, `employment_type`
  - `salary_min`, `salary_max`, `salary_text`
  - `posted_on`, `applicants`
  - `description` (the snapshot; postings disappear)
- **`sources`:** one entry per site that listed it: `{source, source_id, url, posted_on}`.
- **`analysis`:**
  - `score`, `fit`
  - `lean`: which way the role leans and which background it draws on, e.g. "Senior IC · Fintech"
  - `summary`: two or three plain sentences on what the job really is
  - `why[]` and `concerns[]`: specific and honest, in second person ("your fintech background carries over")
  - `level`: one line on level fit
  - `resume`: "General" or "Tailored", plus what to lead with and what to downplay
  - `ai_forward`: true if the company or role is meaningfully AI-driven
- **`company_info`:** `what`, `size`, `funding`, `sentiment`, `news`, `website`, `data_notes` (which sources were used). This is the short version on the card; the one-pager (section 7) is the long one.
- **`flags`:** `[{level: "red" | "yellow", text}]` for ghost signals, vague pay, or data problems. Missing research is a gap, not a flag.
- **`gaps`:** `[{what, why}]` for research still to do, or `[]` when the card is complete. See "Save as you go".

Writing rules:
- Plain language and short sentences.
- No hype.
- Never claim experience the person doesn't have. Say "only claim it if you have real examples."
- Respect the "never mention" list in `targets.md`.

## 7. Company one-pagers

The card is a quick gut check. The one-pager is for when the person wants to keep reading: what the company is, what it sells, how it's doing, and how they'd fit. One per company, shared by every job there, opened from the card's "Company one-pager" button.

- **When:** every company with a job the person marked (interested or later), and every new job scoring 60+. Refresh one older than 30 days. `jobs_incomplete` lists the missing and stale ones.
- **Recruiter listing with no named client:** write a short one-pager about the recruiter that says the client is unknown, and put the job's questions to the recruiter in `questions`.
- **Reuse first:** `company_get` before researching. If `../profile/context/<company>.md` exists (the person's own notes), build from it; it wins where sources disagree.
- **Save with `company_save`:**
  - `tagline`: one line, what they do
  - `website`, `careers`
  - `overview`: 3–4 sentences on what they make, for whom, and how they make money
  - `sections`: `[{heading, text?, bullets[]?}]`, usually these:
    - **Products:** each main product, what it does, who uses it
    - **Customers and market:** segments, notable customers, main competitors, where they win
    - **Business:** size, stage, ownership or funding, revenue if known, growth or shrinking
    - **Leadership and product org:** CEO, head of product, how product is organized, AI direction
    - **Culture and sentiment:** remote policy, review themes (with the skew caveat), layoffs
  - `news`: `[{date, text, url}]`, the last 12 months, newest first
  - `for_you`: how the person's background connects, what to lead with, the real risks
  - `questions`: sharp questions for a recruiter screen or interview
  - `sources`: `[{title, url}]`
- **Rules:** facts over adjectives, dated where it matters. Label estimates and third-party numbers. Aim for about one screen of reading, not a report. Same writing rules as section 6.

## 8. Tailored resume drafts

When the person marks a job **Interested**, they get a tailored resume draft to start from. The resume-drafts scheduled task runs this every couple of hours; the person can also ask for one directly ("Draft a resume for Acme – Director of Product").

**The task:**
1. `drafts_pending`. If it's empty, stop right away: no research, no notification.
2. For each job (up to 3 a run, oldest mark first), write the draft as below and save it with `resume_draft_save`.
3. One PushNotification (under 200 characters): "Resume drafts ready: Acme Director of Product, Globex Group PM". None on an empty run.

**Read first, every time:**
- `../profile/resume.json`: the **base resume, the source of truth**. A draft is this, tailored; never a rewrite from scratch.
- `../profile/resume-notes.md`: decisions already made about wording, framing, and what to leave out. **Start with its "Current rules" list.** They apply to every draft.
- `../profile/resume-rules.json`: phrasings corrected once that must not come back. `resume_draft_save` checks the draft against them and the page limit. **If it returns `warnings`, fix every one and save again.**
- `../profile/targets.md` (title framing, the never-mention list) and the experience bank (`roles/`, `bullet-bank.md`, `personal-projects.md`) for material that isn't on the base resume.
- The job: posting, analysis (`why`, `concerns`, `resume` advice), and the company one-pager if there is one (`company_get`).

**How to tailor:**
- **Headline and summary:** speak to this role's core ask in its own vocabulary, using only true claims.
- **Bullets:** reorder so the most relevant come first; swap in better-matched bullets from the bullet bank; reword to mirror the posting's terms where they honestly fit. Cut what doesn't serve this role.
- **Skills:** lead with the ones the posting asks for that the person actually has.
- **Keep:** the same length as the base (usually one to two pages), the same structure, dates, and titles. Never change a title, date, or number.
- **Never invent** experience, metrics, tools, or domains. If the posting wants something the person lacks, don't paper over it: note it.

**`notes` (markdown), what the person reads first:**
- `## What I emphasized` and `## What I cut or downplayed`: a few bullets each, with why.
- `## Gaps against the posting`: requirements the resume can't honestly cover, and how to handle each (cover letter, interview story, or skip).
- `## How to apply`: from the job's `apply_info` (run `apply_check` first if it's missing). Say where to apply, whether a cover letter is required, optional, or not asked, the answers to prepare (salary expectations: suggest a figure inside the posted range that fits `targets.md`), and any caveat such as a time zone or an assessment. If a cover letter is **required**, say so in the push notification too.
- `## Questions for you`: anything you'd need from them to make it stronger (a metric, whether they've done X).
- `## Revision log`: dated entries, starting with "Drafted from the base resume."

`summary`: one line for the card, e.g. "Leads with platform and admin tooling; AI policy work moved up."

**Revisions happen in conversation.** When the person asks for a change ("lead with the AI work", "make it one page"), read the draft (`resume_draft_get`), change it, and save it again with `resume_draft_save`, adding a revision-log entry. A correction to a fact or a phrasing applies everywhere: record it in `resume-notes.md` (dated entry plus the "Current rules" list), add a checked rule to `resume-rules.json` when it's a reusable phrase, fix the base resume, then run `python -I resume-builder/check.py` and fix every draft it flags. Tailoring choices for one job stay in that draft's notes.

## 9. Wrap up

- Tell the person:
  - how many listings came back, how many were new, and how many were saved vs. skipped
  - the top 3 with scores
  - anything odd (pushback, a layout change, empty sources)
- Point them to the report (http://127.0.0.1:8765).
- `log_tail` or `guard/watch.py --summary` shows what the run did.

## The learning loop

- **Dismiss reasons and interested picks are the training signal.** Read them before every run (step 1).
- **Rescues are the other half.** The app's Activity page lists every listing the review filtered out, with its reason. When the person rescues one, it comes back in `review_queue` with their note: save and score it, and let the note loosen whatever rule skipped it.
- When a pattern shows up (e.g. "too big a company" three times), suggest updating `targets.md` or `search.md` instead of quietly drifting. The profile files stay the source of truth.
