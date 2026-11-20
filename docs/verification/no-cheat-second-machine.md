# No-cheat run: second machine

Machine: `scraper@100.112.87.59` — Ubuntu 24.04.3 LTS, x86_64, `python3` 3.12.3,
no Docker, Chromium at `/usr/bin/chromium` (not exercised).

Conditions: fresh `HOME=/tmp/rolescan-nocheat-home`, fresh clone of the pushed
branch, **no** venv, **no** `.env`, **no** filters, **no** keys, nothing copied
from any other checkout.

```console
$ git clone --branch wip/v0.2.0 https://github.com/jarrettdev/rolescan.git
$ python3 rolescan.py setup --no-input
setup: interpreter /usr/bin/python3 (3.12)
setup: wrote .env from .env.example (fill your keys when you need to notify)
setup: wrote filters/active.json from filters/example.json (edit your searches)
setup: lanes=4 locations=2
setup: ok — next: ./doctor.sh
rc=0

$ python3 rolescan.py doctor --json
CORE_READY True  LIVE True  BROWSER False
rc=0

$ ./bin/ats-registry seed
ATS_REGISTRY_SEED: added=5 known=0 failed=0
rc=0

$ ./bin/personas
persona    rows  matches
data       2     rows=5 matched=2 notified=2 repeats=0 dry_run=True
intern     1     rows=5 matched=1 notified=1 repeats=0 dry_run=True
new-grad   1     rows=5 matched=1 notified=1 repeats=0 dry_run=True
swe        1     rows=5 matched=1 notified=1 repeats=0 dry_run=True
PERSONAS:MET (csvs in data/results)
rc=0

$ ./bin/check.sh | tail -3
== TREE
TREE:MET
CHECK:MET
rc=0

$ git status --porcelain
(no output)
```

Two bugs this run caught and fixed before release: a bare `python3 rolescan.py`
used the system interpreter instead of the venv (no pandas), and the HTTP
client's `cache_dir` argument shadowed the helper of the same name, breaking
`registry seed`.

Not exercised here: Docker (not installed on this machine) and native Windows
(no Windows host; WSL2 is the documented path).
