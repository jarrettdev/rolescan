# Contributing

## Before code

This repo is constraint-first (NLC, `CHARTER.md`). Change the intent, then the
code:

- a behaviour change: update the relevant ADR in `adrs/` and the goal's
  `input.schema.json` / `output.schema.json` / `failure.schema.json`;
- a rule change: edit `rules/adopted.json` (and `rules/enforced_by.json`),
  keep the `nlc:rule=` marker on the code that enforces it;
- a filter or preference: `filters/` only, never code.

## Gates

```bash
./setup.sh && ./doctor.sh     # once
bin/check.sh                  # offline core gate (secrets, tests, fixture run)
bin/check-nlc.sh              # rules, rule IR, call tree
```

Both must pass. `bin/check.sh` fails on a dirty tree, so commit before running
it when you want a clean signal.

## Adding a source

1. Produce rows in the scrape CSV shape (`values/scrape_csv.py`).
2. Select with a pure goal under `goals/` (no I/O) and an adapter for I/O.
3. Write the CSV into `JOBKIT_DATA/drop/` with the
   `job_listings_<epoch_ms>.csv` name.
4. Add a fixture under `fixtures/` and a test under `tests/`.

## Adding a notify target

`adapters/notify.py` owns delivery. Add the target to `TARGETS` and `REQUIRED`
in `adapters/config.py`, return one `{ok, target, error}` per posting, and
never touch the network when `dry_run` is set.
