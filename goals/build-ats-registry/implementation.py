"""Goal build-ats-registry (adrs/0015): candidate employer boards from posting
URLs. Pure: no I/O. bin/ats-registry reads the URLs (ledger, jobs_*.json
archive, hc_scraper's raw-hit candidate files), verifies each candidate
against its public API through adapters/ats.py, and adds only verified ones
through the AtsRegistry noun's verbs.
"""

import re
import sys
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "values"))
from ats import ats_ref  # noqa: E402

# a Greenhouse custom domain gets this many sample postings for the embed
# redirect: the first may have closed since it was scraped
MAX_HOST_SAMPLES = 3
# host labels that never name the employer
_GENERIC_LABELS = {"www", "careers", "career", "jobs", "job", "apply", "app", "boards", "join", "work", "about", "com",
                   "co", "io", "ai", "net", "org", "us", "tv", "inc"}


def _slug(s):
    return re.sub(r"[^a-z0-9]", "", str(s or "").lower())


def board_guesses(host, company):
    """Greenhouse board tokens to try for a custom domain whose embed
    redirect failed, most likely first: the company name, its first word,
    and the domain's own name (abnormal.ai -> abnormal). A guess is used only
    after its board's job list shows jobs on this exact host (bin/ats-registry)."""
    words = re.findall(r"[a-z0-9]+", str(company or "").lower())
    labels = [l for l in (host or "").lower().split(".") if l and l not in _GENERIC_LABELS]
    out = []
    for g in (_slug(company), words[0] if words else "", labels[-1] if labels else ""):
        if len(g) >= 3 and g not in out and g != "nan":
            out.append(g)
    return out


def build_ats_registry(urls, companies=None):
    """Posting URLs in, candidate boards out.

    Returns {"boards": {(ats, tenant): {ats, tenant, sample_url[, site, host]}},
    "gh_hosts": {host: [sample urls]}, "ignored": n}. A Greenhouse posting
    on a custom domain names no board, so its host becomes a candidate with
    up to MAX_HOST_SAMPLES sample URLs; every other ATS URL names its board.
    URLs that are not ATS postings are counted in "ignored". companies maps
    a URL to the listing's company; "host_companies" collects them per
    custom host, so one fronting several employers (an aggregator) is never
    mapped to a single board."""
    # nlc:rule=R-goal-no-noun-write
    boards, gh_hosts, host_companies, ignored = {}, {}, {}, 0
    companies = companies or {}
    for url in urls:
        ref = ats_ref(url)
        if not ref:
            ignored += 1
            continue
        host = (urlsplit(url).hostname or "").lower()
        if ref.ats == "greenhouse" and not ref.tenant:
            samples = gh_hosts.setdefault(host, [])
            if len(samples) < MAX_HOST_SAMPLES and url not in samples:
                samples.append(url)
            co = str(companies.get(url) or "").strip()
            if co and co.lower() != "nan":
                host_companies.setdefault(host, set()).add(co)
            continue
        key = (ref.ats, ref.tenant)
        if key in boards:
            continue
        entry = {"ats": ref.ats, "tenant": ref.tenant, "sample_url": url}
        if ref.ats == "workday":
            entry.update(site=ref.site, host=host)
        boards[key] = entry
    return {"boards": boards, "gh_hosts": gh_hosts, "ignored": ignored,
            "host_companies": {h: sorted(c) for h, c in host_companies.items()}}
