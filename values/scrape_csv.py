"""The scrape CSV format (adrs/0004): the one home for its header and for how
a selected row becomes a CSV line. hc_scraper writes it, process_stream and
goals/ingest-listings read it, integrity/parity/replay.py rebuilds it."""

SCRAPE_COLUMNS = [
    "Title", "Company", "Location", "Salary", "Time Posted",
    "Years of Experience", "Description", "Tech Stack", "Requirements",
    "Company LinkedIn", "Scraped URL", "Job Type", "Industry",
]


def row_to_csv(row):
    """A select-listings row (snake_case keys) as CSV values in SCRAPE_COLUMNS order."""
    g = row.get
    return [
        g("title", ""), g("company", ""), g("location", ""), f"${g('salary', '')}",
        g("time_posted", ""), g("yoe", ""), g("description", ""), g("tech_stack", ""),
        g("requirements", ""), g("company_linkedin", ""), g("apply_url", ""),
        g("job_type", ""), g("industry", ""),
    ]
