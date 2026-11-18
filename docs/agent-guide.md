# Agent guide

Generated from `docs/tasks.json` by `bin/docs-check --write`. Do not edit by hand.

Read `AGENTS.md` first: its rules override anything here.

| Task | Files | Gate | Fixture |
|---|---|---|---|
| **filters**: Change which jobs are selected: roles, locations, pay, blocked companies, titles | `filters/example.json`, `filters/schema.json`, `filters/README.md`, `filters/active.json` | `doctor.sh` | `fixtures/run1` |
| **notify**: Change where matches go: print, webhook, Discord channel or DM | `adapters/notify.py`, `adapters/config.py`, `.env.example` | `bin/check.sh` | `tests/test_notify.py` |
| **ingest**: Change how a scraped batch becomes notifications (dedupe, title exclusion, lane matching) | `process_stream.py`, `goals/ingest-listings/implementation.py`, `domain/ledger/ledger.py` | `bin/check.sh` | `fixtures/run1` |
| **sources**: Add or change a job source (scraper or ATS board poller) | `hc_scraper.py`, `bin/ats-poll`, `bin/ats-registry`, `companies.txt`, `adapters/ats.py`, `goals/select-listings/implementation.py` | `bin/check.sh` | `tests/test_ats_poll.py` |
| **rules**: Add or retire an invariant: rule marker, adopted list, enforcement entry | `rules/adopted.json`, `rules/enforced_by.json`, `adrs/` | `bin/check-nlc.sh` | `rules/adopted.json` |
| **release**: Cut a release: provenance, manifest, tarball | `MANIFEST.txt`, `PROVENANCE.md`, `SOURCE_COMMIT` | `bin/check.sh` | `MANIFEST.txt` |
| **personas**: Check the whole path with no keys: four test users write CSV results from the fixtures | `bin/personas`, `filters/personas`, `process_stream.py` | `bin/check.sh` | `fixtures/run1` |

## Loop

1. Read the ADR or schema that governs the change (see `adrs/README.md`).
2. Edit the constraint, then the code it generates.
3. Run the task's gate, then `bin/check.sh`.
4. If the gate fails, fix the constraint, not the check.

## Where things live

- `process_stream.py` ingests one batch and notifies; `bin/run-once` wraps it.
- `adapters/` is the only place that talks to the outside world.
- `values/` holds pure rules (lanes, posting keys, CSV shape).
- `domain/` holds nouns with private state (`ledger`, `ats_registry`, `linkedin_cache`).
- `goals/` holds pure goal functions with input/output/failure schemas.
