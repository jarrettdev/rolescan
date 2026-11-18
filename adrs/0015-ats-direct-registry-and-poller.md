# ADR 0015 - The employer's ATS is a source: a board registry, a poller, and extraction by ATS id

- Status: Accepted
- Date: 2026-10-24
- Amends: ADR 0001 (posting keys for four more ATSs), ADR 0004 (autojob extracts by ATS id)
- Plan: .nlc-web/plan-edge.json (memo ~/notes/jobscraper-edge-plan.md, Days 1-14)

## Context

The owner, 2026-10-23: "lets implement this: ~/notes/jobscraper-edge-plan.md".
The memo's first play is to treat the employer's applicant tracking system
(ATS) as the source and hiring.cafe as the fallback. hiring.cafe is scraped
six times a day through a browser in the jobs VPN namespace. The same reqs
are public JSON on the ATS itself.

Checked from this box on 2026-10-24:

- Greenhouse `boards-api.greenhouse.io/v1/boards/{token}/jobs[/{id}]`, Lever
  `api.lever.co/v0/postings/{company}?mode=json` and Ashby
  `api.ashbyhq.com/posting-api/job-board/{org}` all answer 304 to
  `If-None-Match` with the ETag they sent, so an unchanged board costs no
  body. Gzip shrinks Roblox's 269-job Greenhouse list to 24 KB. Workday's
  `/wday/cxs/{tenant}/{site}/jobs` answers a JSON POST (nvidia: 2,000 jobs,
  newest first).
- The Greenhouse list carries `first_published`, `updated_at`,
  `requisition_id` and `internal_job_id` without the description.
- `boards.greenhouse.io/embed/job_app?token={id}` redirects to
  `...?for={board}&token={id}`, so a bare Greenhouse job id yields its board
  token.
- On a rebranded board the canonical `job-boards.greenhouse.io/{board}/jobs/{id}`
  302s back to the custom domain (roblox, qualtrics, formlabs). So no page
  route can fix those postings. The API serves them.

The history holds 755 Greenhouse boards, 246 custom domains carrying
`gh_jid`, and 213 Lever boards (processed_jobs.csv plus the jobs_*.json
archive). Ashby, Workday, SmartRecruiters and Workable never reach the
archive, because selection keeps only Greenhouse and Lever.

The failure that started this: autojob routes by hostname, so
`careers.roblox.com/jobs/8283707?gh_jid=8283707` fails with "Unsupported job
platform" (Roblox x2 and Qualtrics in the live pane, 2026-10-23/24).

## Decision

1. **ATS identity has one home per language.** `values/ats.py` parses a
   posting URL into `(ats, tenant, job_id)` for Greenhouse, Lever, Ashby,
   Workable, SmartRecruiters and Workday. `values/posting_key.py` gains
   keys for the four new ATSs, built from the same parse. Wrong merges still
   hide a job, so a key is an ATS id only on that ATS's own host.
   autojob's `src/extractors/greenhouse-api.js` is the Node side of the
   Greenhouse id rule. A contract test runs it on the Python fixtures and
   requires the same ids.
2. **autojob extracts by ATS id, not by hostname.** A URL carrying a
   Greenhouse id (a `gh_jid` on any host, or a greenhouse.io `/jobs/<id>`
   path) is read from the boards API. The board token comes from the URL or
   the embed redirect.
   - A posting is dead only when its token was verified and the job then
     404s. In Node the only verified token comes from a greenhouse.io URL
     (its path, or the `for=` of an embed URL on that host).
     In Python a registry board for the URL's host also counts
     (`adapters/ats.greenhouse_facts`).
   - The embed redirect 404s for a closed id and for a bogus id alike
     (measured 2026-10-24). So on a custom domain a 404 cannot tell "closed"
     from Optiver's stale `gh_jid`. That case, a token failure, a network
     error, and an API title for which `titlesDiverge` (src/utils/titles.js) is true
     all fall back to the page route in Node and fail open in Python.
3. **The board registry is a noun.** `domain/ats_registry` owns
   `ats_registry.jsonl` (append-only, gitignored).
   - `add_board` takes a board only after its public API answered 200.
   - `mark_emitted` records each posting the poller handed on, once, with
     its detection time, first-published time and lane.
   - `bin/ats-registry build` derives candidates through the pure goal
     `build-ats-registry` from processed_jobs.csv, the jobs_*.json archive
     and hc_scraper's raw-hit candidate files. hc_scraper now writes the
     apply URLs of every raw hit, so Ashby, Workday, SmartRecruiters and
     Workable boards enter the registry as hiring.cafe surfaces them.
4. **The poller feeds the existing ingest path.** `bin/ats-poll` runs from
   the scraper's crontab every 15 minutes under a flock. It writes at most one
   `job_listings_<ms>.csv` per run into ~/Downloads, in the scrape CSV format
   (values/scrape_csv.py). So process_stream, the ledger (one posting, one DM)
   and resume generation handle it unchanged.
   - Selection is the pure goal `select-ats-postings`. A posting must match
     a lane in filters/active.json. `values/lanes.py` is the one evaluator of
     the lanes' `jobTitleQuery` and `technologyKeywordsQuery`, and the one
     place a lane's effective config (base plus overrides) is computed.
   - From that config the posting must also meet the lane's years ceiling
     (`roleYoeRange`) and pay floor (`minCompensationLowEnd`). It must state
     pay when the lane sets `restrictJobsToTransparentSalaries`.
   - It must have a US location, a company outside select-listings'
     `BLOCKED_COMPANIES` (loaded from that goal), and a first-published time
     within 72 hours.
   - Postings already in the ledger or already emitted never come back.
   - The fit also needs the lane's `searchQuery` (all its words, honouring
     OR), hiring.cafe's own relevance query.
   - Only lanes whose title query names a role are used
     (`values/lanes.positive`). A lane of NOT clauses alone (Python Data,
     Python AWS, Security+, Software Engineer) matches nearly any title.
     hiring.cafe narrows those with semantic search, and a local word match
     cannot, so they stay with the hiring.cafe scrape. Measured on the first
     live dry run: uncapped picks fell from 81, mostly noise, to 11 in 72
     hours.
   - Newest first, at most 8 rows per run and 40 per UTC day, at most 2 per
     company per run, and one per company and title. A posting is marked
     emitted only after its CSV is written.
   - The poller stands down while `batch-process.js` or `bin/regen-resumes`
     runs. It also stands down from 25 minutes before to 15 minutes after
     each hiring.cafe cron hour (adapters/regen.CRON_HOURS, one home in code; the scraper's crontab is the authority it copies), wrapping midnight around hour 0, so a
     poller batch (up to 20 minutes) does not overlap the scrape's batch.
     process_stream does not serialize batches, which is unchanged here.
   - regen refuses to start while a batch runs, but it checks only at its
     start. A regen started between a poller CSV landing and its batch
     spawning can still overlap that batch. That window is a few seconds.
     ADR 0010 §4 holds otherwise.
   - If the full-history replay forces the four new posting keys to be
     reverted (an unreviewed identity merge), the poller emits Greenhouse and
     Lever rows only.
   - Custom Greenhouse domains are also learned from the boards' own job
     lists. A job on a registered board whose `absolute_url` is on another
     host shows that the host fronts the board, because the list answered
     200. That host then counts as verified for a closed verdict (§2).
     Dry runs learn nothing.
   - Every run that exits 0 touches a liveness stamp, a stand-down included.
     watchdog/health.sh alerts when the stamp exists and is older than 60
     minutes, which means the cron or the script has stopped. health.sh is
     sentinel's probe and an alert starts a repair, so a normal stand-down
     must never trip it. The time of the last emission is read from the
     registry's emitted records, not from the stamp.
5. **Requests are anonymous and polite** (`adapters/ats.py`).
   - One fixed header set with the user agent
     `job_scraper-ats-poller/1.0 (low-rate reader of public job board APIs)`.
     No name, email, handle or contact header.
   - Conditional GETs with cached bodies, gzip, and a 15 s timeout.
   - One worker per host, at least 0.5 s apart. A host that answers 429, or
     answers 5xx three times, is left alone for the rest of the run. One 5xx
     fails only that board: on the first live run, a single 504 from one
     oversized Lever board otherwise cost all 180 Lever boards. A run stops
     at a 12-minute budget.
   - `get()` for every ATS, plus `post_json()` for Workday's search
     endpoint.
   - The poller runs on the host network. This departs from the box's habit
     of using the VPN namespace for scrapes. These are public APIs that do
     not block, and the memo's point is no browser and no VPN churn.

## Amendment 2026-10-24: poller rows carry a tech stack and a company link

Poller rows first went out with a blank Tech Stack and Company LinkedIn, and
the channel post showed `nan` for them. Now:

- `values/tech_terms.py` picks the technology names a posting's text
  mentions. It is its own home and does not reuse autojob's
  `data/taxonomy.json`. That file is resume-skill vocabulary that includes
  practices such as documentation and trading, and it lives in a private
  submodule that CI does not check out.
- `to_row` sends the posting's own host as the company homepage when that
  host is not an ATS domain (`values/ats.is_ats_host`).
- `bin/ats-poll` fills the company link with the same lookup, cache and
  homepage fallback that hiring.cafe rows use, now `linkedin_lookup.enrich`.
  It starts no lookup after 760 s into a run (runs take about 460 s, a cache
  miss up to 65 s, and the cron interval is 900 s). Rows past that point,
  and every row in a dry run, keep the homepage.

## Not done here

- Freshness ranking of the hiring.cafe rows (memo Days 15-45), careers
  subdomain discovery from CT logs, Common Crawl or search queries, and
  Recruitee/Teamtailor.
- Resume generation for non-Greenhouse postings. The poller's Lever, Ashby,
  Workday, SmartRecruiters and Workable rows reach the channel only, as
  Lever rows do today.

## Consequences

- Rebranded Greenhouse boards generate like any other Greenhouse posting,
  and a closed req fails fast instead of spending a browser run.
- A posting can now reach the channel minutes after it is published. Volume
  is bounded by the caps. If the poller is lost, the next hiring.cafe scrape
  still finds the same reqs.
- The poller's requests come from the box's own IP. A board that ever blocks
  it is skipped per run and reported. Moving it into the VPN namespace is a
  one-line cron change.

## Check

- `tests/test_ats_values.py`, `tests/test_ats_client.py` (local HTTP
  server), `domain/ats_registry/tests`, the goal tests,
  `tests/test_ats_registry_build.py`, `tests/test_lanes.py`,
  `tests/test_ats_poll.py`.
- autojob `tests/greenhouse-api.test.mjs` with a stubbed fetch, and the
  id-agreement case in `tests/test_autojob_contract.py`.
- The full-history parity replay stays MET with the new keys.
- Rules R-route-by-ats-id, R-registry-verified-once, R-ats-requests-anonymous
  and R-poll-caps each fail on a planted violation (integrity/gates/rule_plants.py).
