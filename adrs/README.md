# ADRs in this package

Included (they govern shipped behaviour):

| ADR | Subject |
|---|---|
| 0001 | the ledger: one posting, one notification |
| 0002 | process_stream as the ingest entry point |
| 0004 | everything that runs is gated |
| 0008 | full adoption, phase 1 (goals and purity) |
| 0009 | search filters are data |
| 0012 | browser temp files per run |
| 0015 | ATS-direct registry and poller |
| 0018 | packaging, provenance and the secrets boundary |
| 0019 | filters are user configuration |
| 0020 | the public core is canonical |
| 0021 | NLC scope in this package |

## Not in this package

The private job_scraper's resume lane is absent, and with it these ADRs:
0003 (resume log), 0005 (resume content rules), 0006 (skills section),
0010 (regenerate sent resumes), 0011 (no resume DMs for internships),
0013 (autojob browser profile), 0014 (resume audit and mobs),
0016 (req screen before generation), 0017 (outcome log).

Keeping them here would tell an agent to maintain code that does not exist.
