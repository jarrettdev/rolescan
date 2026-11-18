"""Posting identity: a pure value, the one definition of "same job" (adrs/0001).

Not a noun: it holds no state. The ledger noun and the ingest goal both
import it from here so the definition has one home.

Wrong merges hide a job, which is worse than a duplicate DM, so every rule
here errs toward keeping postings apart: ATS ids (Greenhouse, Lever, Ashby,
Workable, SmartRecruiters, Workday; parsed in values/ats.py, adrs/0015) are
trusted only on real ATS hosts or via gh_jid (Greenhouse ids are global), generic URLs keep their
query and fragment (SPA career sites route by #/job/<id>), and a row with no
usable URL falls back to legacy's seven-field identity instead of vanishing.
"""

import sys
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ats import ats_ref, ref_key  # noqa: E402  (the one ATS parse, adrs/0015)
# the identity legacy process_file used; kept only for rows without a URL
LEGACY_FIELDS = ("Title", "Company", "Location", "Salary", "Job Type", "Industry", "Scraped URL")


class UnkeyedListing(ValueError):
    """A URL with no usable posting identity."""


def posting_key(url: object) -> str:
    """Stable identity of a posting from its URL: the ATS job id when there is one."""
    if not isinstance(url, str) or not url.strip() or url.strip().lower() in ("nan", "undefined", "null"):
        raise UnkeyedListing(f"no posting URL: {url!r}")
    try:
        parts = urlsplit(url.strip())
        host = (parts.hostname or "").lower()
        query = parse_qsl(parts.query, keep_blank_values=True)
    except ValueError as e:  # e.g. "Invalid IPv6 URL"
        raise UnkeyedListing(f"malformed posting URL {url!r}: {e}") from e
    if not host:
        raise UnkeyedListing(f"posting URL has no host: {url!r}")
    ref = ats_ref(url)
    if ref:
        return ref_key(ref)
    path = parts.path.rstrip("/")
    q = f"?{urlencode(sorted(query))}" if query else ""
    frag = f"#{parts.fragment}" if parts.fragment else ""
    return f"url:{parts.scheme.lower()}://{host}{path}{q}{frag}"


def listing_key(row) -> str:
    """Identity of a scraped row: its posting key, or legacy's seven-field
    identity when the row has no usable URL (so it is still notified once)."""
    try:
        return posting_key(row.get("Scraped URL"))
    except UnkeyedListing:
        return "legacy:" + "_".join(str(row.get(c)) for c in LEGACY_FIELDS)
