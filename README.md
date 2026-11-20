# rolescan

Watches company hiring pages for new openings, keeps a list of what it has
already seen, and tells you when something matches the searches you set. It
does not apply for you, does not write resumes, and sends nothing anywhere
except the alerts you choose.

Platform install (Linux, macOS, WSL2, Docker): [`docs/INSTALL.md`](docs/INSTALL.md).
Built with [Natural Language Compiler](https://github.com/Zygotic-AI/Natural-Language-Compiler)
(NLC 0.8.0): the rules, filters and gates are written down, so a model can read
them and stay inside them. See `AGENTS.md`.

## Start here: one prompt

Paste this into Claude Code, Codex, Cursor, or any assistant that can read the
repo. It runs the setup, shows you the output, then asks you the four things it
needs to customise the filters. Nothing is sent anywhere until you say so.

```text
I just cloned this repo (rolescan). Get it running end to end, then set it up for me.

1. Read AGENTS.md, CLAUDE.md (or llms.txt if you have no file access), README.md
   and docs/agent-guide.md first. Follow their rules: no secrets in git, no posting
   or DMing without asking me, change filters rather than code.
2. Run ./setup.sh, ./doctor.sh and bin/run-once --fixtures fixtures/run1 --dry-run.
   Show me what each printed and stop if anything is not CORE_READY.
3. Ask me these four things, then edit filters/active.json only. Leave
   filters/example.json alone: it is the contract the gate pins.
   - role titles or keywords to watch for
   - locations (cities, states, or "remote US")
   - minimum base pay
   - maximum years of experience
   Also ask whether internships and new-grad roles should be included, and which
   titles or companies to exclude.
4. Re-run ./doctor.sh and bin/run-once --fixtures fixtures/run1 --dry-run and show
   me which sample roles now match, and which of my requested roles would not match
   the sample batch yet (and why).
5. Run bin/ats-registry seed, then bin/ats-registry show, and tell me how to add a
   company board I care about.
6. Ask me where alerts should go: terminal, webhook, or Discord. Only after I answer,
   update .env, confirm with ./doctor.sh --json, and stop before sending a test message.
7. Print the two lines I should put in cron. Do not add a scheduler yourself.
   If a gate mentions a missing NLC hub or a missing browser, tell me what to
   install; do not invent a workaround or edit the gate.
```

If you are on chatgpt.com with no file access, paste `llms.txt` and the output of
`./doctor.sh --json` instead; it can interpret errors but cannot run commands.

## What you need

- Python 3.12+ and a terminal. Nothing else for the default path.
- Optional: Chrome/Chromium, if you also want the hiring.cafe source.
- Optional: a Discord bot token or a webhook URL, if you want alerts there
  instead of your terminal.

## Two minutes to a first run

```bash
git clone https://github.com/jarrettdev/rolescan.git
cd rolescan
./setup.sh        # venv, dependencies, .env, filters/active.json
./doctor.sh       # prints CORE_READY when it can run offline
bin/run-once --fixtures fixtures/run1 --dry-run
```

That last command prints the sample roles it would have pinged you about. No
keys, no network, no state written.

Four test users are included, so you can see the whole path in a few seconds
and get files back instead of scrolling a terminal:

```bash
bin/personas
cat data/results/intern.csv
```

```
persona    rows  matches
data       2     rows=5 matched=2 ...
intern     1     rows=5 matched=1 ...
new-grad   1     rows=5 matched=1 ...
swe        1     rows=5 matched=1 ...
PERSONAS:MET (csvs in .../data/results)
```

Each persona is an ordinary filters document in `filters/personas/` (intern,
new-grad, swe, data). Copy one to `filters/active.json` as a starting point, or
edit it in place to see how a change moves the CSV.

## Point it at the roles you want

Two files, both plain JSON/text:

| File | What it controls |
|---|---|
| `filters/active.json` | your searches: role titles, locations, pay floor, years, titles to skip, companies to block |
| `companies.txt` | the company boards to poll (`<ats> <company>`, e.g. `greenhouse stripe`) |

`setup.sh` copies `filters/example.json` to `filters/active.json` on first run.
That file is yours (gitignored); the example stays as the documented contract.
`./doctor.sh` validates it and names the exact field when it is wrong.

Seed the company boards once:

```bash
bin/ats-registry seed                 # verifies every line in companies.txt
bin/ats-registry add greenhouse acme  # or add one you know
bin/ats-registry show                 # what you poll
```

Add a search by appending to `filters/active.json`:

```json
{"name": "New grad and internships", "location": "US",
 "overrides": {
   "jobTitleQuery": "Intern OR Internship OR \"New Grad\" OR Graduate",
   "technologyKeywordsQuery": "Python OR SQL",
   "searchQuery": ""}}
```

`title_exclude` at the bottom of the file keeps senior titles out by default
and leaves Graduate/New Grad/Intern shapes alone. The pay floor and the years
ceiling apply to both the company boards and the ingest step; hourly pay is not
a yearly figure, so a floor never rejects an internship that only quotes an
hourly rate. `filters/README.md` has the field-by-field table.

## Choose where alerts go

| `NOTIFY` | Keys you need |
|---|---|
| `print` (default) | none |
| `webhook` | `NOTIFY_WEBHOOK_URL` |
| `discord` | `DISCORD_BOT_TOKEN`, `DISCORD_CHANNEL_ID`; a DM also needs `ENABLE_DM=1` and `DM_USER_ID` |

Put them in `.env` (created by setup, gitignored for good reason). A blank or
missing key stops the run with `MISSING_SECRET: <KEY>` instead of posting
something broken.

## Run it

No scheduler ships: run the two steps yourself, from cron or a timer.

```bash
bin/ats-poll     # read the company boards once; writes data/drop/*.csv
bin/run-once     # ingest what is waiting and notify
```

```cron
*/30 * * * * cd ~/rolescan && ./bin/ats-poll   >> ~/rolescan-data/poll.log 2>&1
*/15 * * * * cd ~/rolescan && ./bin/run-once   >> ~/rolescan-data/run.log  2>&1
```

The hiring.cafe source is browser automation and is opt-in by policy, not just
by flag: read `docs/third-party.md` first, then
`xvfb-run -a python3 hc_scraper.py`. `ENABLE_HIRING_CAFE=0` turns it off.

## Use your AI assistant to drive it

The repo tells a model what it may do: `AGENTS.md` is the rules, `CLAUDE.md` is
the same for Claude Code, `llms.txt` is a compact brief you can paste into
ChatGPT or any chat. `docs/tasks.json` maps a task to the files and the gate.

Prompts that work, verbatim:

- **First setup**: "Read AGENTS.md and README.md, then run `./setup.sh`,
  `./doctor.sh`, and `bin/run-once --fixtures fixtures/run1 --dry-run`. Show me
  the output and tell me if anything is missing."
- **Your searches**: "Using `filters/active.json` and `filters/schema.json`, add
  a lane for new-grad and internship software roles in the US. Run `./doctor.sh`
  and the fixture run, and show me which sample roles now match. Leave
  `filters/example.json` alone: it is the contract the gate pins."
- **Alerts**: "Switch `NOTIFY` to discord. Ask me for the bot token and channel
  id, write them to `.env`, and confirm with `./doctor.sh --json`. Do not send a
  test message without asking me."
- **Add an employer**: "Add `greenhouse <company>` with `bin/ats-registry add`,
  then show me `bin/ats-registry show`."
- **Something failed**: "Run `bin/check.sh`, read the failing gate, and fix the
  constraint that caused it. Do not edit tests, gates, or the check to make it
  green."
- **ChatGPT with no file access**: paste `llms.txt` plus the output of
  `./doctor.sh --json` and ask for the next step. It cannot run commands for
  you, but it can interpret the errors.

## When it looks broken

| Symptom | Cause and fix |
|---|---|
| `MISSING_SECRET: X` | that key is absent or blank in `.env`; `./doctor.sh` names it |
| `CORE_NOT_READY` | run `./setup.sh`; doctor lists what is missing |
| `matched=0` | filters too narrow for the batch you ran. Company-board postings must be newer than 72 h, and your lane's title/tech queries must both hit; pay, years and `dateFetchedPastNDays` only steer the hiring.cafe search |
| `NOTHING_TO_DO` (exit 2) | nothing is waiting in `data/drop`; run `bin/ats-poll` or the scraper first |
| Discord `403` | bad token, wrong channel, or the bot cannot post there |
| browser `WARN` | run `./setup.sh --browser` and install Chrome, or ignore it and use the boards |

## How it is built

| Path | What |
|---|---|
| `process_stream.py`, `bin/run-once` | ingest one batch, notify matches |
| `hc_scraper.py` | hiring.cafe scrape into the drop folder |
| `bin/ats-poll`, `bin/ats-registry` | company-board poller and its registry |
| `values/`, `domain/`, `goals/` | pure rules, nouns with private state, pure goals |
| `adapters/` | the only code that talks to the network |
| `data/` | ledger, registry, drop folder, caches (gitignored) |

Gates: `bin/check.sh` (offline: compile, secrets, doctor, tests, fixture run,
clean tree) and `bin/check-nlc.sh` (rules, rule IR, call tree). The second needs
the NLC hub 0.8.0: `curl -fsSL https://raw.githubusercontent.com/Zygotic-AI/Natural-Language-Compiler/main/scripts/install.sh | NLC_VERSION=0.8.0 bash`.
`AGENTS.md` has the rules a contributor or an agent must follow. `setup.sh`
takes no prompts; `--no-input` exists for scripts.

## Provenance and licence

Copied from a private upstream at the commit in `SOURCE_COMMIT`; see
`PROVENANCE.md` and `MANIFEST.txt`. MIT (see `LICENSE`). Third-party sites,
limits and captcha policy: `docs/third-party.md`.
