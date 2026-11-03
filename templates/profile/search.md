# Search Settings

What the job finder searches for on each run. Change it any time; the next run picks it up.

**The approach is a wide net.** The job sites match loosely, Claude reads every title and description when it scores, and the database remembers what's already been seen. So it's better to fetch too much than to miss a good job over wording.

## Searches
Sent to the job sites as-is. Sites match loosely, so title variants overlap; each search costs one request per page, so they're rotated: the first three run every day and the rest take turns. List every title variant you'd want, most important first:
- _(e.g. Director of Product)_
- _(e.g. Principal Product Manager)_
- _(e.g. Group Product Manager)_

## Title net
Used where *we* do the matching (company job boards, triage of connector results). A title is kept if it contains **any** of these words, in any case, ignoring punctuation, with plurals allowed. Keep it broad: one core word (like "product" or "engineer") catches most variants.
- _(e.g. product)_

## Locations
- _(e.g. Denver, Colorado, United States)_
- _(e.g. United States (remote only))_

## LinkedIn filters
- **Posted within:** _(e.g. 30 days on the first run, then 2 days)_
- **Workplace:** _(remote / hybrid / onsite, or any)_

## Company watchlist (job boards)
Companies whose own job board gets checked each run (one request per company). The platform and slug are in the company's careers-page link, e.g. `boards.greenhouse.io/<slug>`, `jobs.lever.co/<slug>`, `jobs.ashbyhq.com/<slug>`. If you don't know them, list the company and Claude will find them.

| Company | Platform | Slug | Why |
|---|---|---|---|
| _(e.g. Acme)_ | greenhouse | _(acme)_ | _( )_ |

## Skip
Only obvious noise. When in doubt, keep it and let scoring decide.
- **Companies:** _( )_
- **Title words that mean noise:** _(e.g. "intern", "pharmacist")_
