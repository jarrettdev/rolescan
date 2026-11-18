# Charter

This package uses Boundary-Based Programming / Natural Language Compiler (NLC).

- Compiler: NLC **0.8.0** (pinned in `.nlc/lock.json`, launcher `./nlc`).
- SSOT for the method: https://github.com/Zygotic-AI/Natural-Language-Compiler/blob/main/CHARTER.md
- Rules in force: `rules/adopted.json`; how each is enforced: `rules/enforced_by.json`.
- This package is *not* the private job_scraper. The resume-generation lane, mobs and
  watchdog are deliberately absent; see `adrs/README.md`.

Change code by changing the constraint that generates it: update the goal's
input/output/failure schema or the ADR, then the implementation, then run
`bin/check.sh` and `bin/check-nlc.sh`.
