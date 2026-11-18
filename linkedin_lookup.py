"""Find a company's LinkedIn page. hiring.cafe stopped populating
linkedin_url around Feb 2026, but it still sends the company homepage,
which nearly always links the LinkedIn page in its footer.

Strategy: cache -> homepage footer grep -> Bing / DuckDuckGo search.
Returns bare 'linkedin.com/company/<slug>' to match the historical CSV
format that process_stream.py already renders as an /people link.

The lookup itself is goals/find-linkedin and the cache is the
domain/linkedin_cache noun (adrs/0008); this module is the network side
(fetches through the jobs VPN namespace) and keeps the old call shape.

CLI: python linkedin_lookup.py "Company Name" [homepage]
"""
import importlib.util
import os
import subprocess
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "domain", "linkedin_cache"))
from linkedin_cache import LinkedinCache  # noqa: E402

# Optional fetcher: any executable that takes a URL on argv and prints the page.
# JOBKIT_FETCH=/path/to/fetch enables lookups; without it this module returns [].
FETCH = os.environ.get("JOBKIT_FETCH", "")
CACHE_PATH = os.path.join(os.environ.get("JOBKIT_DATA") or os.path.join(_HERE, "data"),
                          "linkedin_cache.json")

_spec = importlib.util.spec_from_file_location(
    "find_linkedin_goal", os.path.join(_HERE, "goals", "find-linkedin", "implementation.py"))
_goal = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_goal)

_cache = None  # the LinkedinCache noun for CACHE_PATH, built on first use


def _noun():
    global _cache
    if _cache is None:
        _cache = LinkedinCache(CACHE_PATH)
    return _cache


def _fetch(url, timeout):
    """Fetch one page through JOBKIT_FETCH; empty when unset or the fetch fails."""
    if not FETCH:
        return ""
    try:
        r = subprocess.run([FETCH, url], capture_output=True, text=True, timeout=timeout)
        return r.stdout or ""
    except (subprocess.SubprocessError, OSError):
        return ""


def find_linkedin(company, homepage=""):
    """Return 'linkedin.com/company/<slug>' or '' if not found. Hits are
    cached forever; a miss is never cached."""
    # _fetch is looked up at call time so a caller (or test) can swap it
    return _goal.find_linkedin(company, homepage, lambda url, timeout: _fetch(url, timeout), _noun())


def company_link(company, direct, homepage, log=print):
    """hiring.cafe stopped sending linkedin_url in Feb 2026; look it up
    ourselves (cached), falling back to the homepage as before."""
    if direct and "linkedin.com" in direct:
        return direct
    try:
        found = find_linkedin(company, homepage)
    except Exception as e:
        log(f"  [warn] linkedin lookup failed for {company}: {e}")
        found = ""
    return found or direct or homepage


def enrich(rows, log=print):
    """Set each row's company_linkedin from its company, its company_linkedin
    and its company_homepage, which is removed. Used by hc_scraper and
    bin/ats-poll."""
    for row in rows:
        homepage = row.pop("company_homepage", "")
        row["company_linkedin"] = company_link(row["company"], row["company_linkedin"], homepage, log)
    return rows


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    print(find_linkedin(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else ""))
