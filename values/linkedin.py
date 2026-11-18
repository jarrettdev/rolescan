"""LinkedIn company page values (adrs/0008): one home for what a company page
URL looks like and how to pull a slug out of fetched HTML. Pure, no I/O."""
import re

LI_RE = re.compile(r"linkedin\.com(?:%2F|/)company(?:%2F|/)([A-Za-z0-9][A-Za-z0-9_.\-]*)")
# Bing renders result URLs as breadcrumbs: linkedin.com › company › pathai
LI_CRUMB_RE = re.compile(r"linkedin\.com\s*›\s*company\s*›\s*([A-Za-z0-9][A-Za-z0-9_.\-]*)")
COMPANY_PAGE = re.compile(r"linkedin\.com/company/[A-Za-z0-9][A-Za-z0-9_.\-]*")


def first_slug(html: str) -> str:
    m = LI_RE.search(html or "") or LI_CRUMB_RE.search(html or "")
    return m.group(1) if m else ""


def company_page(slug: str) -> str:
    return f"linkedin.com/company/{slug}"


def is_company_page(value) -> bool:
    return isinstance(value, str) and bool(COMPANY_PAGE.fullmatch(value))


def cache_key(company) -> str:
    return (company or "").strip().lower()
