# ADR 0001 - Ledger noun: one posting, one DM

- Status: Accepted
- Date: 2026-09-28

## Context

`processed_jobs.csv` is the ledger of every job DM'd to the owner. It drives
Discord notifications, resume generation (one resume per new Greenhouse
posting, billed to the Claude subscription), and downstream readers
(recruiter-scout reads it as "companies known to be hiring").

`process_stream.process_file` decided whether a scraped row was new by a
`unique_id` concatenating seven mutable fields: Title, Company, Location,
Salary, Job Type, Industry, Scraped URL. The scrape source's enrichment is
unstable between runs (company blank then filled, titles reworded, salary
added), so one posting gets a new identity and is DM'd, and a resume
regenerated, again.

Measured on the live ledger 2026-09-28: 3,318 rows, 3,261 distinct postings
by ATS job id (every row carries one). 57 duplicate DMs. The rule "one
posting, one DM" existed only as intent.

The same code rewrote the whole file each batch after a non-stable sort and
`drop_duplicates(keep='last')`, so row order was not guaranteed chronological
and a crash mid-write could truncate the ledger.

## Decision

- **Noun `ledger`** (`domain/ledger/`). State: posting key -> first row seen,
  private, exposed read-only. Posting key: `gh:<id>` (Greenhouse, from the
  `gh_jid` parameter or a greenhouse.io `/jobs/<id>` path, host-independent),
  `lever:<uuid>` (jobs.lever.co), otherwise `url:<normalized url>` (scheme,
  lowercased host, path without trailing slash, query parameters sorted,
  fragment dropped). The query is kept for generic URLs because some career
  sites identify a posting by it; a wrong merge would hide a job, which is
  worse than a duplicate DM.
  - `record(row) -> bool` is the only mutation. It refuses a row with no URL
    (`UnkeyedListing`), returns False and changes nothing for a key already
    present, otherwise adds the row and queues it for persistence.
  - No verb edits or removes an entry.
  - `save()` appends queued rows to the CSV under the existing header. It
    never rewrites existing rows.
  - Loading keeps the first row per key and reports how many historical
    duplicates the file holds. The file on disk is not rewritten.
- **Goal `ingest-listings`** (`goals/ingest-listings/`): the pure part of
  `process_file`, ported and disclosed as a port. Adds the timestamp columns,
  applies the seniority title filter, calls `ledger.record` per row, returns
  the rows to notify. Writes no ledger fields.
- **Parity oracle**: legacy decision logic frozen verbatim in
  `integrity/legacy/process_file_legacy.py`. Replaying real scrape batches in
  order, the goal's notifications must be a subset of legacy's, and every
  legacy notification the goal drops must be (a) a posting key the goal
  already notified, or (b) a row with no URL. Anything else fails the gate.
- **Not nouns**: a scraped batch (immutable input value); the LinkedIn cache
  (derivable from the web); resume artifacts (outputs); search filter config
  (no state machine); recruiter-scout's seen-cache (other repo).

## Consequences

- A re-posted role under a new ATS id is still notified. Only an identical
  id is suppressed. Field drift on a known posting no longer triggers a DM
  or a resume.
- The ledger is append-only from this change on; the 57 historical duplicate
  rows stay on disk as history and are collapsed on load.
- The seniority filter still has two homes: the hiring.cafe `jobTitleQuery`
  per search filter (server-side prefilter) and this goal (the authority).
  Not unified here.
- Switching `process_stream` to the goal happens only after parity holds
  (ADR 0002).
