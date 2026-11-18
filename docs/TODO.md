# TODO

## Recruiter profiles (tabled 2026-11-17)

Not collected today. The kit resolves a company's LinkedIn page only, and even
that is off by default (`ENRICH=0`, `JOBKIT_FETCH` unset). No recruiter, hiring
manager or "people to message" data is fetched, stored or shipped.

When this gets picked up, the shape to follow is the upstream private lane:
`recruiter-scout` builds a `people-master.csv` keyed by company (public
profiles, one data/eng leader plus recruiters where known), and the daily queue
attaches one people reply per posting. If it lands here it needs:

- a noun for the people cache (hits only, never misses), and a goal with
  input/output/failure schemas;
- an explicit opt-in, because the data is personal and third-party;
- a provenance note in `docs/third-party.md` and an ADR on what may be stored;
- a fixture company with fake profiles so the gate stays offline.

Nothing else waits on it: filters, alerts and the ledger work without people.
