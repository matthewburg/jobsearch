# Profile (experience bank)

The source of truth. The job finder scores against it, and every resume and cover letter is drafted from it. **Too much detail is good:** tailoring means choosing what to leave out.

| File | What goes in it | Who fills it | Read by |
|---|---|---|---|
| `targets.md` | Level, roles, company preferences, location, **pay rules**, deal-breakers, things never to mention | Claude interviews you | Job finder scoring; resume framing |
| `search.md` | Search keywords, locations, LinkedIn filters, **company watchlist** (job-board slugs), noise to skip | You plus Claude | Job finder collection |
| `about.md` | Who you are, how you work, your own summary | Interview | Summaries, cover letters |
| `roles/<company>.md` | One file per job: titles, dates, scope, accomplishments | Claude drafts from your resumes; you correct | Resumes, fit reasoning |
| `resume.json` | Your base resume content (JSON Resume format). The sample is a made-up person. | Claude drafts from `roles/` and `bullet-bank.md`; you approve | `resume-builder` (every style and tailored version) |
| `resume-notes.md` | Every correction you make while reviewing resumes, with your reasoning, so it's applied next time | Claude, as you review | All resume and cover-letter drafting |
| `bullet-bank.md` | Every accomplishment from every past resume, de-duplicated, tagged by source | Claude mines `samples/` | Resumes |
| `personal-projects.md` | Side projects, hobbies, builder work | You | Fit reasoning ("what lights you up") |
| `linkedin-current.md` | Pasted text of your LinkedIn profile | You | Consistency checks |
| `skills.md` *(optional)* | Tools, languages, platforms, domains, with how recent and how deep | Interview | Resumes, fit |
| `references.md` *(optional, private)* | Who could serve as a reference | You | You only |

For each accomplishment, capture: **situation → what you did → result (numbers wherever possible) → skills it shows → which kinds of roles it's relevant to.**
