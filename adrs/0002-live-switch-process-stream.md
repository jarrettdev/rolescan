# ADR 0002 - Live switch: process_stream decides through the ledger

- Status: Accepted
- Date: 2026-09-28

## Context

ADR 0001's goal reached parity with the frozen legacy logic on all 1,450
real scrape batches (0 violations; every suppressed notification is a
repeat, and the 7 repeats whose title or company differed are reviewed in
`fixtures/reviewed_merges.json`). An independent three-part audit then
found defects that parity alone did not show, all fixed before this switch:

- lost-posting risks in `save()` (row glued onto a last line with no
  newline, clobbering a file created after load, a column silently dropped)
  and duplicate rows from two writers;
- a false merge class the replay could not see (SPA URLs routed by
  `#/job/<id>`), because the parity spec judged repeats with the same key it
  was checking;
- rows with no URL dropped permanently;
- CI pinned to a hub tag that does not exist upstream;
- in process_stream: an exception in `process_file` kills the watchdog
  observer thread silently; `create_task` called off the loop thread; files
  that land during a restart are never processed.

## Decision

- `process_stream.process_file` keeps its name and call shape. Its body
  calls `goals/ingest-listings` inside `with Ledger(path, exclusive=True)` (an exclusive
  lock across load, record and save), saves, then hands the returned rows to
  `send_discord_notifications`. Save before DM: a crash in between loses a
  DM rather than repeating one.
- The body runs under a catch-all that logs the traceback (sentinel's
  health probe alerts on it) and leaves the file in place, so the observer
  thread survives.
- Coroutines go to the Discord loop with `run_coroutine_threadsafe` at both
  call sites (ingest and resume DM).
- A one-time startup sweep processes `job_listings_*.csv` files younger than
  12 hours; older stranded files are logged and left alone rather than
  DM'ing months-old postings.
- `process_stream.py` sits at the repo root, outside NLC gate 1's scan
  (goals/, workflows/, adapters/). The noun defends itself instead:
  read-only views and a refusing `__setattr__`.

## Verification before switching

- `bin/check.sh` CHECK:MET (full-history replay, unit tests, gate 1,
  specimen red on its `_entries` write). CI scope simulated against the
  pinned v0.2.0 hub: CHECK:MET.
- The real `process_file` path, run against a copy of the live ledger
  rewound to just before the 2026-09-26 08:05 scrape, DM'd exactly the 4
  postings production recorded for that scrape. Re-offering an already
  processed scrape DM'd nothing. A malformed batch did not raise out of
  `process_file`.

## Rollback

`git revert` the commit that carries this ADR, then restart job_watch
(`tmux kill-session -t job_watch`, then `~/code/sentinel/restore.sh`, or
recreate it with `venv/bin/python process_stream.py`). The legacy code reads
the appended ledger unchanged: same header, same `Time Posted` rendering.
After a rollback, legacy's 7-field dedup and its duplicate DMs return, and
its first write re-sorts the file; nothing is corrupted.
