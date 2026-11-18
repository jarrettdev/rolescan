# rolescan — read this first

`AGENTS.md` holds the rules you must follow (no credentials, no posting without
NOTIFY, change the constraint before the code, state under `data/`, run the
gates). This file exists because Claude Code reads `CLAUDE.md` by convention.

Start here, in order:

1. `AGENTS.md` — the six hard rules and where to begin.
2. `docs/agent-guide.md` — task → files → gate map, generated from `docs/tasks.json`.
3. `adrs/README.md` — decisions in force; ADR 0018 (secrets), 0019 (filters),
   0021 (NLC scope).
4. `README.md` — quickstart, notify targets, sources.

Commands: `./setup.sh`, `./doctor.sh`, `bin/run-once --fixtures fixtures/run1 --dry-run`,
`bin/check.sh`, `bin/check-nlc.sh`. Ask before posting to Discord or enabling the
browser scrape.
