#!/usr/bin/env python3
"""
hiring.cafe job scraper using SeleniumBase CDP mode.

Strategy:
  1. Load hiring.cafe, solve Cloudflare captcha (one time)
  2. For each search filter, call /api/search-jobs directly via fetch()
     from the page context (uses session cookies from step 1)
  3. Paginate through results (size=40 per page)
  4. Select rows (goals/select-listings: greenhouse/lever, view cap, dedupe)
  5. Write CSV to ~/Downloads (triggers process_stream.py)

Usage:
  xvfb-run -a python3 hc_scraper.py --dry-run
  xvfb-run -a python3 hc_scraper.py            # writes data/drop/job_listings_<ms>.csv

Third-party site: read docs/third-party.md before enabling it. Set
ENABLE_HIRING_CAFE=0 to turn it off; captcha solving is opt-in.
"""

import json
import csv
import re
import time
import sys
import os
import shutil
import tempfile
import traceback
from contextlib import contextmanager
from datetime import datetime
from urllib.parse import quote


sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "values"))
from adapters import config, paths  # noqa: E402
from scrape_csv import SCRAPE_COLUMNS, row_to_csv  # noqa: E402
from lanes import effective_configs  # noqa: E402



def _load_goal():
    """goals/select-listings (adrs/0004), loaded by path like process_stream
    loads ingest-listings: the goal dir has a hyphen."""
    import importlib.util
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "goals", "select-listings", "implementation.py")
    spec = importlib.util.spec_from_file_location("select_listings_goal", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_GOAL = _load_goal()

# ---------------------------------------------------------------------------
# Search filter configs (ported 1:1 from hc_working_multi.js)
# ---------------------------------------------------------------------------

# Search filters are data (adrs/0009): filters/active.json holds the base
# config, location presets and the filter list. Older sets live in
# filters/archive/; revert with `cp filters/archive/<name>.json filters/active.json`.
def load_filters(path=None):
    """[{"name", "config"}] built as {**base, locations, **overrides}."""
    with open(path or paths.filters_path(), encoding="utf-8") as f:
        doc = json.load(f)
    return effective_configs(doc)  # values/lanes.py, one home (adrs/0015)


SEARCH_FILTERS = None  # loaded lazily: a clone with no active.json still imports

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SCREENSHOT_DIR = str(paths.data_root() / "screenshots")


def ensure_screenshot_dir():
    os.makedirs(SCREENSHOT_DIR, exist_ok=True)


def save_screenshot(sb, name):
    try:
        fpath = os.path.join(SCREENSHOT_DIR, f"{name}.png")
        sb.cdp.save_screenshot(fpath)
        log(f"  [screenshot] {fpath}")
    except Exception as e:
        log(f"  [screenshot failed] {e}")


def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def try_solve_captcha(sb, context=""):
    """Attempt to solve captcha if present and HC_SOLVE_CAPTCHA=1 (docs/third-party.md)."""
    if not config.captcha_enabled():
        return False
    try:
        sb.solve_captcha()
        log(f"  Captcha solved {context}")
        sb.sleep(2)
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# API fetch helpers
# ---------------------------------------------------------------------------

FETCH_ATTEMPTS = 3


class FetchFailed(RuntimeError):
    """hiring.cafe gave no search data for a page, even after retries."""


def fetch_page(sb, build_id, config, page_num=0, page_size=40):
    """Fetch one page of results. Returns (hits, is_last_page).

    History of hiring.cafe's search transport:
      - pre-Apr 2026: POST /api/search-jobs (REST)
      - Apr-Jul 2026: GET /_next/data/{buildId}/index.json (Next.js data route)
      - Jul 14 2026-: SSR only. The data route returns the HTML app shell, and
        programmatic fetch() of page URLs throws (Failed to fetch) while real
        navigations pass, so we NAVIGATE to the search URL and read the
        embedded __NEXT_DATA__ out of the DOM. page/size go as URL params
        (ssrPage in the response confirms pagination); the server picks its own
        page size regardless of `size`, so trust ssrIsLastPage, not counts.
    build_id is kept in the signature for logging but is no longer used.
    """
    encoded_state = quote(json.dumps(config))
    url = (
        f"https://hiring.cafe/"
        f"?searchState={encoded_state}&page={page_num}&size={page_size}"
    )
    # A navigation sometimes lands without __NEXT_DATA__; that used to count as
    # zero jobs and silently drop the filter (2026-10-06). Retry, then fail loudly.
    pp = None
    for attempt in range(1, FETCH_ATTEMPTS + 1):
        sb.cdp.open(url)
        sb.sleep(2.5 * attempt)
        try_solve_captcha(sb, f"(page {page_num})")
        raw = sb.cdp.evaluate(
            "document.getElementById('__NEXT_DATA__') && "
            "document.getElementById('__NEXT_DATA__').textContent"
        )
        if not raw or not isinstance(raw, str):
            log(f"  [warn] No __NEXT_DATA__ after navigation (page {page_num}, attempt {attempt})")
            continue
        try:
            pp = json.loads(raw).get("props", {}).get("pageProps", {})
            break
        except (json.JSONDecodeError, TypeError) as e:
            log(f"  [warn] __NEXT_DATA__ parse failed (page {page_num}, attempt {attempt}): {e}")
    if pp is None:
        raise FetchFailed(f"no search data for page {page_num} after {FETCH_ATTEMPTS} attempts")
    if pp.get("ssrError"):
        log(f"  [warn] ssrError (page {page_num}): {pp['ssrError']}")
    return pp.get("ssrHits", []), pp.get("ssrIsLastPage", True)


def extract_build_id(sb):
    """Pull the Next.js buildId (e.g. 'KHL6pwrRx0qXfmkGIviUb') from the page.

    The buildId is part of the /_next/data/{buildId}/index.json URL and changes
    on every deploy, so it must be extracted fresh each run. First tries the
    embedded __NEXT_DATA__ script, then falls back to a regex over performance
    entries in case the script tag format changes.
    """
    raw = sb.cdp.evaluate(
        "document.getElementById('__NEXT_DATA__') && "
        "document.getElementById('__NEXT_DATA__').textContent"
    )
    if raw and isinstance(raw, str):
        try:
            bid = json.loads(raw).get("buildId")
            if bid and isinstance(bid, str):
                return bid
        except (json.JSONDecodeError, TypeError):
            pass

    entries_raw = sb.cdp.evaluate(
        "JSON.stringify(performance.getEntries().map(e => e.name))"
    )
    try:
        entries = json.loads(entries_raw) if isinstance(entries_raw, str) else []
    except (json.JSONDecodeError, TypeError):
        entries = []
    for name in entries:
        m = re.search(r"/_next/data/([^/]+)/", name)
        if m:
            return m.group(1)
    return None


# ---------------------------------------------------------------------------
# Core scraping logic
# ---------------------------------------------------------------------------

def scrape_filter(sb, filt, filter_idx, total_filters, build_id):
    """Fetch all pages of jobs for one filter via the Next.js data endpoint.

    Unlike the previous design, we no longer navigate to the filter page and
    scrape the API URL out of performance entries; the new endpoint accepts
    our partial filter config directly, so we just call it.
    """
    name = filt["name"]
    config = filt["config"]
    log(f"[Filter {filter_idx + 1}/{total_filters}] {name}")

    all_results = []
    for page_num in range(5):
        try:
            hits, is_last_page = fetch_page(sb, build_id, config, page_num=page_num)
        except FetchFailed as e:
            if page_num == 0:
                raise  # the whole filter failed; the caller logs it
            log(f"  [warn] {e}; keeping the {len(all_results)} jobs from earlier pages")
            break
        all_results.extend(hits)
        log(f"  Page {page_num}: {len(hits)} jobs (last={is_last_page})")
        if is_last_page or not hits:
            break
        sb.sleep(1)

    log(f"  Total for {name}: {len(all_results)} jobs")
    return all_results


BROWSER_TMP_PREFIX = "hc_scraper-"
BROWSER_TMP_STALE_S = 6 * 3600  # the cron runs every 4 hours (adrs/0012)


@contextmanager
def browser_tmpdir(base=None, stale_after=BROWSER_TMP_STALE_S, now=None):
    """adrs/0012: the one folder a scrape's browser writes temp files to. Chrome and chromedriver use TMPDIR,
    so it points here while the browser runs; the folder is deleted on the way out. Folders older than
    stale_after (left by runs that were killed outright) are deleted first."""
    base = base or tempfile.gettempdir()
    now = time.time() if now is None else now
    for name in os.listdir(base):
        path = os.path.join(base, name)
        try:
            if name.startswith(BROWSER_TMP_PREFIX) and os.path.isdir(path) and now - os.path.getmtime(path) > stale_after:
                shutil.rmtree(path, ignore_errors=True)
                log(f"Removed stale browser temp folder {path}")
        except OSError:
            pass
    path = tempfile.mkdtemp(prefix=BROWSER_TMP_PREFIX, dir=base)
    old = os.environ.get("TMPDIR")
    os.environ["TMPDIR"] = path
    tempfile.tempdir = None
    try:
        yield path
    finally:
        if old is None:
            os.environ.pop("TMPDIR", None)
        else:
            os.environ["TMPDIR"] = old
        tempfile.tempdir = None
        shutil.rmtree(path, ignore_errors=True)


def scrape_all_filters(filters=None, screenshots=True, per_filter=None):
    """Main entry: launch browser, handle Cloudflare, scrape each filter.
    per_filter, if given, collects {name: hits} for the dry-run report."""
    filters = SEARCH_FILTERS if filters is None else filters
    all_jobs = []
    if screenshots:
        ensure_screenshot_dir()
    shot = save_screenshot if screenshots else (lambda sb, name: None)

    log("hiring.cafe Job Scraper (SeleniumBase CDP)")
    log(f"Running {len(filters)} search filters")

    # imported here so the module (and its tests) load without a browser stack
    from seleniumbase import SB

    with browser_tmpdir():
        with SB(uc=True, test=True, locale="en") as sb:
            # Initial load to get past Cloudflare
            log("Loading hiring.cafe (Cloudflare pass)...")
            sb.activate_cdp_mode("https://hiring.cafe/")
            sb.sleep(3)
            shot(sb, "01_initial_load")

            solved = try_solve_captcha(sb, "(initial)")
            if solved:
                shot(sb, "02_after_captcha")
            else:
                log("  No captcha on initial load")

            try:
                title = sb.cdp.evaluate("document.title")
                log(f"  Page title: {title}")
            except Exception:
                pass

            shot(sb, "03_ready")

            build_id = extract_build_id(sb)
            if build_id:
                log(f"Next.js buildId: {build_id} (informational; SSR fetch does not need it)")
            else:
                log("[warn] No buildId found; continuing (SSR fetch does not need it)")

            for i, filt in enumerate(filters):
                try:
                    jobs = scrape_filter(sb, filt, i, len(filters), build_id)
                    all_jobs.extend(jobs)
                    if per_filter is not None:
                        per_filter[filt["name"]] = jobs
                    log(f"  Running total: {len(all_jobs)} jobs")
                except Exception as e:
                    log(f"  [ERROR] Filter {filt['name']} failed: {e}")
                    if per_filter is not None:
                        per_filter[filt["name"]] = None  # reported as FAILED, not as 0
                    traceback.print_exc()

                if i < len(filters) - 1:
                    sb.sleep(1)

    return all_jobs


# ---------------------------------------------------------------------------
# Post-processing: filter, map, write CSV (same logic as JS version)
# ---------------------------------------------------------------------------

def enrich(rows):
    """Fill company_linkedin on the rows select_listings chose (network I/O,
    so it lives here and not in the goal). Enrichment is off unless ENRICH=1."""
    if not config.enrichment_enabled():
        return rows
    import linkedin_lookup
    return linkedin_lookup.enrich(rows, log)


def write_csv(processed, out_dir=None):
    """Write the scrape CSV (values/scrape_csv.py) where process_stream looks."""
    out_dir = str(out_dir or (paths.data_root() / "drop"))
    os.makedirs(out_dir, exist_ok=True)
    timestamp = int(time.time() * 1000)
    filepath = os.path.join(out_dir, f"job_listings_{timestamp}.csv")

    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, quoting=csv.QUOTE_ALL)
        writer.writerow(SCRAPE_COLUMNS)
        for j in processed:
            writer.writerow(row_to_csv(j))

    log(f"Saved {len(processed)} jobs to {filepath}")
    return filepath


def write_debug_json(processed):
    """Save JSON copy for debugging."""
    timestamp = int(time.time() * 1000)
    filepath = str(paths.data_root() / f"jobs_{timestamp}.json")
    with open(filepath, "w") as f:
        json.dump(processed, f, indent=2)
    log(f"Saved debug JSON to {filepath}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def _blocked():
    """Blocked companies from the filters document (adrs/0019)."""
    with open(paths.filters_path(), encoding="utf-8") as f:
        doc = json.load(f)
    return frozenset(str(c).strip().lower() for c in doc.get("blocked_companies") or [] if str(c).strip())


def _ledger_keys():
    """Posting keys already in the ledger (read-only, no lock)."""
    root = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.join(root, "domain", "ledger"))
    from ledger import Ledger
    return set(Ledger(exclusive=False).keys())


_VALUES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "values")


def _key(row):
    if _VALUES not in sys.path:
        sys.path.insert(0, _VALUES)
    from posting_key import posting_key
    try:
        return posting_key(row.get("apply_url", ""))
    except Exception:
        return ""


def dry_run_report(per_filter, known):
    """Lines for --dry-run: per filter raw / selected / new, then totals and
    the source mix of raw hits. Pure: no I/O."""
    lines = [f"{'filter':38} {'raw':>5} {'selected':>9} {'new':>5}"]
    all_raw, seen_new = [], set()
    for name, hits in per_filter.items():
        if hits is None:
            lines.append(f"{name[:38]:38} {'FAILED':>5}")
            continue
        rows = _GOAL.select_listings(hits)
        new = {_key(r) for r in rows if _key(r) and _key(r) not in known}
        seen_new |= new
        all_raw.extend(hits)
        lines.append(f"{name[:38]:38} {len(hits):>5} {len(rows):>9} {len(new):>5}")
    selected = _GOAL.select_listings(all_raw)
    lines.append(f"{'TOTAL (raw summed; rest deduped)':38} {len(all_raw):>5} {len(selected):>9} {len(seen_new):>5}")
    mix = {}
    for h in all_raw:
        if len((h.get("job_information") or {}).get("viewedByUsers") or []) >= _GOAL.VIEW_CAP:
            continue
        src = (h.get("source") or "unknown").lower()
        kind = next((k for k in ("grnhse", "lever", "ashby", "workday", "smartrecruiters", "icims") if k in src), "other")
        mix[kind] = mix.get(kind, 0) + 1
    total = sum(mix.values()) or 1
    lines.append("source mix under the view cap: " + ", ".join(f"{k} {v} ({100 * v // total}%)" for k, v in sorted(mix.items(), key=lambda kv: -kv[1])))
    return lines


def limit_rows(rows, n, known):
    """At most n rows for a manual run: new postings first, Greenhouse first."""
    def rank(r):
        k = _key(r)
        return (k in known or not k, not k.startswith("gh:"))
    return sorted(rows, key=rank)[:n]


# At most this many rows per cron run, new postings first (adrs/0009): a filter
# change can make weeks of postings new at once, and this spreads that
# catch-up over several runs instead of flooding Discord and the resume batch.
CANDIDATES_DIR = str(paths.data_root() / "ats_candidates")
CANDIDATES_KEEP_S = 30 * 86400


def write_board_candidates(raw_jobs, out_dir=CANDIDATES_DIR, now=None):
    """Every raw hit's apply URL, one per line, for bin/ats-registry to find
    Ashby, Workday, SmartRecruiters and Workable boards that selection drops
    (adrs/0015). Cron runs this as root, so files are written world-readable.
    Files older than 30 days are deleted first. Never raises: a failure here
    must not stop the scrape."""
    try:
        now = time.time() if now is None else now
        os.makedirs(out_dir, exist_ok=True)
        for name in os.listdir(out_dir):
            path = os.path.join(out_dir, name)
            if name.endswith(".txt") and now - os.path.getmtime(path) > CANDIDATES_KEEP_S:
                os.remove(path)
        urls = sorted({str(j.get("apply_url") or "").strip() for j in raw_jobs if isinstance(j, dict)} - {""})
        if not urls:
            return None
        path = os.path.join(out_dir, f"{int(now * 1000)}.txt")
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(urls) + "\n")
        os.chmod(path, 0o644)
        return path
    except Exception as e:  # never into the scrape
        log(f"Board candidates not written: {e}")
        return None


MAX_ROWS_PER_RUN = 25


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description="hiring.cafe scraper (cron runs it with no flags)")
    ap.add_argument("--dry-run", action="store_true", help="scrape and report per filter; write nothing")
    ap.add_argument("--filters", default=None, help="filter set (default: JOBKIT_FILTERS, else filters/active.json, else the example)")
    ap.add_argument("--limit", type=int, default=MAX_ROWS_PER_RUN,
                    help=f"keep at most N rows, new and Greenhouse first (default {MAX_ROWS_PER_RUN})")
    a = ap.parse_args(argv)
    filters = load_filters(a.filters)
    if not config.hiring_cafe_enabled():
        log("ENABLE_HIRING_CAFE=0: hiring.cafe scraping is disabled; nothing to do")
        return
    per_filter = {} if a.dry_run else None
    try:
        all_jobs = scrape_all_filters(filters, screenshots=not a.dry_run, per_filter=per_filter)
    except Exception as e:
        log(f"FATAL: Scraper failed: {e}")
        traceback.print_exc()
        sys.exit(1)

    log("=" * 60)
    log(f"Total raw jobs scraped: {len(all_jobs)}")
    log("=" * 60)

    if a.dry_run:
        for line in dry_run_report(per_filter, _ledger_keys()):
            print(line, flush=True)
        log("Dry run: nothing written")
        return

    write_board_candidates(all_jobs)

    if not all_jobs:
        log("No jobs captured")
        sys.exit(0)

    selected = _GOAL.select_listings(all_jobs, blocked_companies=_blocked())
    if a.limit and len(selected) > a.limit:
        selected = limit_rows(selected, a.limit, _ledger_keys())
        log(f"Row cap {a.limit}: keeping {len(selected)} rows (new and Greenhouse first; the rest come next run)")
    processed = enrich(selected)
    log(f"After filtering (greenhouse/lever, <{_GOAL.VIEW_CAP} views, deduped): {len(processed)} jobs")

    if processed:
        write_csv(processed)
        write_debug_json(processed)

    log("Done!")


if __name__ == "__main__":
    main()
