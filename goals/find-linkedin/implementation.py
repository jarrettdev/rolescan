"""Goal find-linkedin (adrs/0008): a company's LinkedIn page, from the cache or
by looking it up. Ported from linkedin_lookup.find_linkedin (frozen at
integrity/legacy/linkedin_lookup_legacy.py), disclosed in emit-manifest.json.

The LinkedinCache noun owns the cache; this goal changes it only through
remember(). Network access is injected as `fetch(url, timeout) -> html`, so
the goal does no I/O of its own: linkedin_lookup supplies the VPN fetch.
"""

import sys
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "values"))
from linkedin import company_page, first_slug  # noqa: E402

SEARCH_ENGINES = ("https://www.bing.com/search?q={q}", "https://html.duckduckgo.com/html/?q={q}")


def find_linkedin(company, homepage, fetch, cache) -> str:
    """'linkedin.com/company/<slug>' or '' if not found. Only a hit is cached;
    a miss may be a rate-limited search engine."""
    # nlc:rule=R-goal-no-noun-write
    # nlc:rule=R-linkedin-cache-hits-only  # nlc:obligation=linkedin_cache.json holds only hits: lowercased company keys mapped to linkedin.com/company/<slug>; a miss is never cached
    company = (company or "").strip()
    if not company:
        return ""
    hit = cache.get(company)
    if hit:
        return hit

    slug = ""
    homepage = (homepage or "").strip()
    if homepage and "linkedin.com" not in homepage:
        slug = first_slug(fetch(homepage if homepage.startswith("http") else f"https://{homepage}", 25))
    if not slug:
        # first search hit on the quoted name, no verification (as before the port)
        q = quote(f'"{company}" linkedin.com/company')
        for engine in SEARCH_ENGINES:
            slug = first_slug(fetch(engine.format(q=q), 20))
            if slug:
                break

    if not slug:
        return ""
    page = company_page(slug)
    cache.remember(company, page)
    return page
