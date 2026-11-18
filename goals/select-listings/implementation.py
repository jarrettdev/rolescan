"""Goal select-listings: pick and shape the hiring.cafe hits worth a scrape row.

Ported from hc_scraper.process_jobs (adrs/0004). Pure: no I/O. LinkedIn
enrichment needs the network, so hc_scraper does it after selection, on the
same rows in the same order; each row carries the raw company LinkedIn URL
and homepage for that step.
"""

import re

# hiring.cafe counts viewers per posting; past this many the posting is stale.
VIEW_CAP = 100
SOURCES = ("grnhse", "lever")
BLOCKED_COMPANIES = frozenset({"spacex", "esri"})


def select_listings(raw_jobs, blocked_companies=BLOCKED_COMPANIES):
    """hiring.cafe /api/search-jobs hits in, scrape rows out (scrape order).

    A hit missing nested dicts is read as empty; nothing here raises on a
    malformed hit."""
    # nlc:rule=R-goal-no-noun-write
    # nlc:rule=R-selection-pure  # nlc:obligation=scrape selection is pure: select_listings imports nothing that does I/O; enrichment happens after it
    seen_ids = set()
    rows = []
    for job in raw_jobs:
        # the same posting comes back from several search filters
        obj_id = job.get("objectID", "")
        if obj_id in seen_ids:
            continue
        seen_ids.add(obj_id)

        source = job.get("source") or ""
        if not any(s in source for s in SOURCES):
            continue

        ji = job.get("job_information") or {}
        if len(ji.get("viewedByUsers") or []) >= VIEW_CAP:
            continue

        ecd = job.get("enriched_company_data") or {}
        v5 = job.get("v5_processed_job_data") or {}
        company = ecd.get("name", "") or v5.get("company_name", "")
        if company.strip().lower() in blocked_companies:
            continue

        rows.append({
            "title": ji.get("title", ""),
            "company": company,
            "location": v5.get("formatted_workplace_location", ""),
            "salary": v5.get("yearly_min_compensation", "Not listed"),
            "time_posted": "0h",
            "yoe": v5.get("min_industry_and_role_yoe", ""),
            "description": re.sub(r"<[^>]*>", "", ji.get("description", ""))[:500],
            "tech_stack": ", ".join(v5.get("technical_tools", [])),
            "requirements": v5.get("requirements_summary", ""),
            "company_linkedin": ecd.get("linkedin_url", ""),
            "company_homepage": ecd.get("homepage_uri", ""),
            "apply_url": job.get("apply_url", ""),
            "job_type": ", ".join(v5.get("commitment", [])),
            "industry": v5.get("job_category", ""),
        })
    return rows
