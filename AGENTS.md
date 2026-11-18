# Agent rules for this repository

You are working on a redistributable job scraper. These rules are not advice;
`bin/check.sh` and `bin/check-nlc.sh` enforce most of them.

1. **Never commit a credential.** `.env` stays gitignored. `bin/secret-scan`
   runs in the gate and fails on token shapes, owner ids and private host
   paths. If you find a secret in the tree, stop and report it.
2. **Do not post or DM without NOTIFY.** `NOTIFY=print` is the default and
   needs no key. A Discord send requires `NOTIFY=discord`; a DM additionally
   requires `ENABLE_DM=1`. Never set those on the user's behalf.
3. **Change the constraint before the code.** Filters → `filters/`. Behaviour →
   the goal's `*.schema.json` plus an ADR in `adrs/`. Invariants → a
   `nlc:rule=` marker, `rules/adopted.json` and `rules/enforced_by.json`.
   Never edit a test or a gate to make a failure disappear.
4. **Keep runtime state under data/.** `JOBKIT_DATA` decides where; nothing
   writes to the repository root.
5. **Respect the sources.** No new scheduler, no captcha solving unless the
   user set `HC_SOLVE_CAPTCHA=1`, no removing the rate limits in
   `docs/third-party.md`.
6. **Run the gates.** `bin/check.sh` (offline core) and `bin/check-nlc.sh`
   (rules). A green gate is not a release; the user ships.

## Where to start

Read `docs/agent-guide.md` (generated from `docs/tasks.json`) for a task →
files → gate map, and `adrs/README.md` for the decisions in force. The resume
lane, mobs and watchdog of the private upstream are deliberately absent; do not
re-add them without an ADR.
