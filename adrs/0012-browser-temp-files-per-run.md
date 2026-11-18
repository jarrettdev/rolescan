# ADR 0012 - Each scrape keeps its browser temp files in one folder and deletes it

- Status: Accepted
- Date: 2026-10-16

## Context

The cron runs hc_scraper.py as root in the jobs VPN namespace every 4 hours.
SeleniumBase CDP mode drops chromedriver, which is what deletes Chrome's
temporary profile, so every run left a /tmp/.org.chromium.Chromium.* folder:
191 of them from 2026-09-16 to 2026-10-16 on the scraper box (owner found
/tmp at 49G with the disk at 97%). A local repro on about:blank leaves one.
These folders are a few KB each: the 36 GB was autojob's Puppeteer profiles in
the snap Chromium's private /tmp (ADR 0013), not this leak.

## Decision

1. `browser_tmpdir()` in hc_scraper.py is the one home for where a scrape's
   browser writes temp files: a fresh folder named `hc_scraper-*` under the
   system temp dir, set as TMPDIR for Chrome and chromedriver while the
   browser runs.
2. The folder is deleted when the scrape ends, on success, on an exception
   and on Ctrl-C. There is no signal handler: a run ended by SIGTERM, SIGHUP
   or SIGKILL leaves its folder behind.
3. So each run first deletes `hc_scraper-*` folders older than 6 hours (the
   cron runs every 4). Age is the folder's own mtime, so a single run lasting
   over 6 hours could lose its live profile to the next run; runs take minutes.

## Consequences

/tmp stops growing by one profile per run. The 190 folders already left were
removed by hand (owner, 2026-10-16). Space used elsewhere in /tmp is not this
ADR's concern.

## Check

tests/test_browser_tmpdir.py: the folder is the TMPDIR inside, is gone after a
normal exit and after an exception, TMPDIR is restored, and a stale folder is
swept while a fresh one is kept.
