# job-scraper-kit

A job scraper you can run for yourself: it finds new postings from employer
ATS boards and (optionally) hiring.cafe, keeps a ledger so nothing is notified
twice, and sends the matches wherever you want.

This is the find-and-notify core of a private scraper, repackaged. It does not
write resumes, does not apply for you, and ships no credentials.

## Requirements

- Python 3.12+ (3.13 tested). No Node, no database.
- Chrome or Chromium only if you enable the hiring.cafe scraper.

## Quickstart

```bash
./setup.sh          # venv, dependencies, .env from .env.example, filters/active.json
./doctor.sh         # CORE_READY, plus LIVE_READY / BROWSER_READY as optional rows
bin/run-once --fixtures fixtures/run1 --dry-run   # no network, no keys
```

`bin/run-once --fixtures fixtures/run1 --dry-run` notifies the postings that
match your filters. Edit `filters/active.json` and run it again.

## Filters

`filters/example.json` is the shipped contract; `setup.sh` copies it to
`filters/active.json`, which is yours and gitignored. See `filters/README.md`
for the shape, `blocked_companies`, `title_exclude`, and the JSON-Schema check
`./doctor.sh` runs.

Typical lanes: a role (`"Software Engineer"`), a location preset, pay floor,
years ceiling, seniority list. The default `title_exclude` drops senior titles
but keeps Graduate, New Grad and Intern shapes.

## Notify

`NOTIFY` selects the target; the default is `print`.

| Target | Keys |
|---|---|
| `print` | none |
| `webhook` | `NOTIFY_WEBHOOK_URL` |
| `discord` | `DISCORD_BOT_TOKEN`, `DISCORD_CHANNEL_ID`; DM also needs `ENABLE_DM=1` and `DM_USER_ID` |

A missing or blank key stops the run with `MISSING_SECRET: <KEY>`. Nothing
falls back to an empty token.

## Sources

- **ATS boards** (`bin/ats-poll`): public Greenhouse, Lever, Ashby, Workable,
  SmartRecruiters and Workday endpoints. A board enters the registry only after
  its API answered 200. Seed the shipped examples, then add your own:

  ```bash
  bin/ats-registry seed                 # companies.txt, verified one by one
  bin/ats-registry add greenhouse acme  # any board you know
  bin/ats-registry show
  ```

  `companies.txt` is yours to edit. A fresh clone polls only what you seed.
- **hiring.cafe** (`hc_scraper.py`): browser automation, enabled by default,
  `ENABLE_HIRING_CAFE=0` turns it off. Read `docs/third-party.md` first:
  terms, rate limits and captcha handling are your call.

No scheduler ships. Run them yourself:

```bash
bin/ats-poll                                  # one poll, writes data/drop/*.csv
xvfb-run -a python3 hc_scraper.py             # one scrape
bin/run-once                                  # ingest every batch in data/drop
```

## Layout

| Path | What |
|---|---|
| `process_stream.py`, `bin/run-once` | ingest one batch, notify matches |
| `hc_scraper.py` | hiring.cafe scrape into the drop folder |
| `bin/ats-poll`, `bin/ats-registry` | employer-board poller and its registry |
| `values/`, `domain/`, `goals/` | pure rules, nouns with private state, pure goals |
| `adapters/` | the only code that talks to the network |
| `filters/` | your saved searches |
| `data/` | ledger, registry, drop folder, caches (gitignored) |
| `docs/`, `adrs/`, `rules/` | agent map, decisions, invariants |

## Gates

```bash
bin/check.sh        # compile, secrets, doctor, tests, fixture run, clean tree
bin/check-nlc.sh    # rule coverage, rule IR, call tree (needs NLC 0.8.0)
```

## Provenance and licence

Copied from a private upstream at the commit in `SOURCE_COMMIT`; see
`PROVENANCE.md` and `MANIFEST.txt`. MIT (see `LICENSE`). Nothing here is legal
advice; see `docs/third-party.md`.
