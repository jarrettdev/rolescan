# ADR 0004 - Everything that runs is gated

- Status: Accepted
- Date: 2026-10-04

## Context

The owner asked (2026-10-04) that everything that runs in this project be
part of NLC. Until now the gate covered the ledger, the resume log, the
ingest goal and process_stream's file handling. These run with no gate:

| What | How it runs |
|---|---|
| `hc_scraper.py` + `linkedin_lookup.py` | cron, every 4h, in the jobs VPN namespace |
| `process_stream.py` Discord routing | tmux `job_watch` |
| `autojob/automated-resume-optimizer` (submodule, private repo) | spawned by process_stream per batch |
| `watchdog/health.sh`, `watchdog.sh`, `restore_tmux.sh` | sentinel cron every 30 min, `@reboot` |

Mapping them turned up facts with two homes and contracts nobody checks:

- The view cap was 100 in code and "<50" in the log and docstring.
- The scrape CSV header was written in `hc_scraper.write_csv` and again in
  `integrity/parity/replay.py`, with the row mapping duplicated.
- process_stream finds resumes by parsing `Processing:`, `TEX saved to:` and
  `PDF saved to:` out of node's stdout, and node parses the `url<TAB>title`
  lines process_stream writes. Neither side tested the other.
- autojob's committed HEAD could not run: `src/extractors/index.js` imports
  two files that were never committed, and the live code had 11 modified
  files.

## Decision

- **Scrape selection is a pure goal**, `goals/select-listings`: dedupe by
  objectID, Greenhouse/Lever only, `VIEW_CAP = 100` (current behaviour),
  blocked companies, field mapping. No I/O; LinkedIn enrichment happens in
  hc_scraper after selection.
- **The scrape CSV format has one home**, `values/scrape_csv.py`
  (`SCRAPE_COLUMNS`, `row_to_csv`), used by the scraper and the replay.
  A contract test writes a CSV through the scraper's writer and ingests it.
- **The autojob boundary is gated from both sides**: the JS parser of
  `job-urls.txt` lives in `src/utils/job-urls.js` and is run against a file
  written by process_stream's writer; the stdout markers are constants in
  process_stream and the gate fails if the JS stops emitting them. autojob
  gets a real `npm test`, which `bin/check.sh` runs.
- **health.sh is tested hermetically** with a fake tmux and fixture
  directories (env overrides, defaults unchanged).
- **linkedin_lookup is tested offline** with `_fetch` stubbed.
- **Discord routing is pinned as-is** by a characterization test. Its
  substring match sends titles like "Maintenance" to the data channel; the
  fix is proposed in FINDINGS.md, not applied, because routing changes were
  not asked for.
- Every artifact above is in `.nlc/gate-scope.json`.
- CI cannot check out the private submodule without an owner-held secret,
  so CI prints `AUTOJOB:NOT_RUN`; a fresh recursive clone on the box is the
  evidence for the autojob gates.
- `requirements.txt` is the one Python dependency list.

## Not gated, by decision

- `analyze_jobs.py`, `audit_resume_titles.py`: manual, read-only analysis
  over local data; nothing schedules them.
- autojob's untracked manual tools (`manual-resume*.js`,
  `test-single-job.js`, `verify-fix.js`): kept on disk, not committed.
- The sentinel repair agent can edit, commit and push here
  (`~/code/sentinel/engine.sh`) without the NLC stamps. The pre-commit gate
  still runs on its commits. Known gap; the fix belongs in sentinel.
- Live network behaviour (hiring.cafe, Jobscan, Claude CLI, Discord).

## Consequences

A break in any running piece's contract fails `bin/check.sh`, so the
pre-commit hook, the Stop hook and the nightly run catch it. The gate cannot
tell whether a live scrape found jobs; that stays with sentinel's health
probe.
