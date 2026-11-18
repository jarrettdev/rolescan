# ADR 0009 - Search filters are data, and cover the owner's lanes

- Status: Accepted
- Date: 2026-10-06

## Context

The owner asked (2026-10-06) to checkpoint the search filters, then widen
them to the roles he wants: software, platform and backend engineering;
security (he holds Security+); AWS data engineering (AWS Certified Data
Engineer); AI evaluation and quality ("applying process engineering
principles to AI"); applied and forward-deployed AI; AI developer tooling;
ML platform; finance (quant and market-data tech, model risk); data
acquisition. Anywhere in the US, pay floor $85,000.

Evidence for the lanes: his NLC projects (quality gates for AI-written code,
hallucination-lab, receipts), the yield-curve port at AllianceBernstein,
his site and GitHub (scraping, market data, pipelines), and the companies
in his interview prep (Hebbia, Octus, AllianceBernstein).

The 17 old filters were Python literals in hc_scraper.py, with years of
experience 0-2, pay $65,000+, salaries required, and no AI-quality, ML
platform, finance-tech, model-risk or data-acquisition lanes.

## Decision

1. **Filters are data.** `filters/active.json` holds the base config,
   location presets and the filter list; hc_scraper builds its searches from
   it. `filters/archive/` keeps every set; the old one is
   `2026-10-06-baseline.json` (tests check it equals the code at tag
   `filters-baseline-2026-10-06`). Revert:
   `cp filters/archive/2026-10-06-baseline.json filters/active.json`.
2. **Base:** years of experience 0-3, pay $85,000+ (both pay fields), entry
   and mid level, individual contributor, US, 14-day window.
3. **Lanes:** the 17 old filters are kept (security included, at the
   owner's request). New: Software Engineer (any stack, 2 days), AWS Data
   Engineer, AI Evaluation & Quality, Applied AI / Forward Deployed, AI
   Developer Tooling, ML Platform / MLOps, Trading & Market Data, Model Risk
   & Validation, Data Acquisition / Web Data. Quant, Trading and Model Risk
   do not require a posted salary (many finance firms do not post one).
4. **Windows:** hiring.cafe honors 2, 4, 14 and 30 days; 1, 3 and 7 are
   ignored and search without an age limit (measured 2026-10-06). The niche
   lanes and the low-volume security lanes use 30 days: at 4 or 14 days they
   return almost nothing.
5. **Testing a set:** `hc_scraper.py --dry-run [--filters FILE]` runs the
   searches the way cron does and prints raw, selected and new per filter,
   writing nothing. `--limit N` caps a manual run (new and Greenhouse rows
   first). A page that comes back without search data is retried, and a
   filter that still fails is reported as FAILED, not as zero jobs (16 such
   silent drops in the cron log before this change).
6. **Resume batches** may run 150 s per job, at least 15 minutes, so a larger
   batch is not cut off.
7. **At most 25 rows per run** (MAX_ROWS_PER_RUN), new postings first and
   Greenhouse first. A filter change can make weeks of postings new at once;
   the cap spreads that catch-up over several runs instead of flooding
   Discord and the resume batch, and the 30-day windows keep the rest visible
   to the next runs. Normal runs rarely reach it.

## Measured (live dry-runs, 2026-10-06, .nlc-web/dry-*.txt)

- Old set: 383 raw, 32 selected, 1 new.
- New set: 904 raw (summed over filters), 115 selected, 75 new. The 75 are a
  one-time catch-up as the new lanes enter the ledger; with the row cap they
  arrive at most 25 per run, about three runs.
- Filters with nothing selected this run, kept as owner lanes: IAM, Cybersecurity
  Analyst (no raw hits); Cloud Engineer AWS, AI/LLM Engineer, Data Analyst,
  DevSecOps, AI Evaluation & Quality, Model Risk & Validation, Data
  Acquisition (few raw hits, none on Greenhouse/Lever under the view cap).

## Not changed (follow-ups)

- Only Greenhouse and Lever postings are selected. In the new set's raw hits
  Ashby is 11% and Workday 14%. Adding them needs ATS ids in
  values/posting_key.py first, or one posting could be DM'd twice.
- The plan's "at most 25 new" gate was set before the window behavior was
  known. Cutting windows would have emptied the niche lanes, so the gate is
  enforced per run by the row cap instead (execution audit, 2026-10-06).

## In this package (2026-11-17)

The upstream archive (`filters/archive/2026-10-06-baseline.json`) and its git tag
are not shipped. `filters/example.json` is the contract; its base is neutral
(0-5 years, no pay floor, 7-day window) because a new user has no history to
reproduce. `title_exclude`, `blocked_companies` and lane locations are read from
that document only; nothing in a goal hardcodes them (ADR 0019).
