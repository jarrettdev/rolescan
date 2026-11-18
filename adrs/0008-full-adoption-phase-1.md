# ADR 0008 - Full adoption, phase 1: rules, facts, the LinkedIn cache, the autojob adapter

- Status: Accepted
- Date: 2026-10-06

## Context

The nlc-adopt standard (skill ADR 0001, owner 2026-10-05) counts an adoption
as done only when every stateful thing is a noun written by goals, the real
invariants are adopted rules, facts are recorded, and ship-check is green but
for the human signature. The fullness report on 2026-10-06 showed this repo
at 2 nouns, 2 goals, 0 rules, 0 facts. Its invariants (ADRs 0001-0006, RCA
0001-0002) were enforced by tests but never adopted as rules, and
`linkedin_cache.json` was written by `linkedin_lookup.py` with no noun.

## Decision

1. **Rules.** The invariants already enforced by tests become adopted rules
   with markers, each naming the gate that enforces it: goals never write
   noun fields; one posting, one DM; the ledger is append-only; one resume
   outcome per posting; scrape selection is pure; the autojob boundary holds
   both ways; the skills section is bounded and dash-free; the resume title
   is the role only; the LinkedIn cache holds hits only.
2. **Facts.** Durable operating facts go in knowledge/facts.json with a source
   and a check date (runtime, view cap, one-page cap, routing quirk, sign-off).
3. **Noun `linkedin_cache`** owns `linkedin_cache.json`: lowercased company
   key to `linkedin.com/company/<slug>`, hits only. **Goal `find-linkedin`**
   is its only writer; `linkedin_lookup.find_linkedin` keeps its call shape
   as a shim, and network fetches stay in it (the adapter side).
4. **`adapters/autojob.py`** holds the Python side of the autojob boundary
   (job-urls writer, stdout markers). process_stream imports from it; the
   cross-language rules carry their markers there and are enforced by the
   Python gates that run the Node code (tests/test_autojob_contract.py,
   autojob npm test).

## Not nouns yet (phase 2, recorded as gaps)

- autojob's output records (`watch/keywords_*.json`, `batch-results-*.json`,
  `resume_*.tex`, PDFs): written by Node; they need Python nouns guarding
  that data, read by health.sh and the analysis scripts.
- The scrape batch handoff (`~/Downloads/job_listings_*.csv`), the
  `jobs_*.json` parity archive, and `job-urls.txt`.
- Resume delivery in process_stream calls the ResumeLog verbs directly; it
  should become a goal.
These touch the live pipeline more deeply and are left for a separate change.

## Notes from the audits (2026-10-06)

- Markers: rule-emit placed the goal markers; the five domain and adapter
  markers were printed by `rule-marker` and inserted by a script at their
  sites, with obligation text copied from rules/adopted.json. The adapter
  markers for the Node rules are labels for gates that run the Node code.
- rule-emit puts a goal's markers at the top of the module's first function
  (in ingest-listings that is `_parse_time_posted`, not the record loop).
- LinkedinCache drops entries that are not hits or not lowercased keys when
  it loads, where the old module served them as is. The live cache had none
  (381 entries, 2026-10-06).
- The cache is root-owned because cron writes it. Writes go through a
  unique temp file; concurrent writers can still lose each other's update,
  as before the port.
- Still open beyond the phase 2 nouns: the ledger's raw read/write (UC20),
  and gate 1 does not see `object.__setattr__` writes from a goal (hub).
