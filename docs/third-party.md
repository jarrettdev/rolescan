# Third-party sites: terms, limits, and what this software will not hide

The kit automates two kinds of sources. Neither grants you permission to use
them; you are responsible for how you run it.

## hiring.cafe (browser scrape)

`hc_scraper.py` drives a real browser to the public site, reads the JSON the
page itself requests, and pages through results. That is automation of a
third-party service.

- Check their terms and `robots.txt` before enabling it. If they forbid
  automated access, set `ENABLE_HIRING_CAFE=0` and use the ATS poller instead.
- The kit ships **no scheduler**. Run it by hand or your own cron, at a rate
  you can justify (the source ran every 4 hours).
- Built-in limits: at most 25 rows per run (`--limit`), one page at a time,
  about one request per second. Do not remove them.
- **Captcha solving is off by default.** `HC_SOLVE_CAPTCHA=1` opts in; that
  decides for you that working around an anti-bot control is acceptable, which
  is your call to make and often is not.
- Do not publish or resell their data. This tool notifies you about postings;
  it does not grant rights to the underlying listings.

## Employer ATS APIs (Greenhouse, Lever, Ashby, Workable, SmartRecruiters, Workday)

These are public board endpoints. The poller sends a fixed, anonymous project
header set, keeps one worker per host, and polls at most every 15 minutes.
Respect their rate limits and stop if you get throttled.

## No warranty

Nothing here is legal advice. If a site blocks you, that is a signal to stop,
not a puzzle to defeat.
