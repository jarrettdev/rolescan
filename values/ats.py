"""ATS identity of a posting URL, and the shape of each ATS's public JSON
(adrs/0015). Pure: no I/O.

ats_ref() is the one Python parse of "which applicant tracking system, which
board, which job". posting_key builds its keys from it, the registry derives
boards from it, and the poller normalizes API postings into rows whose URL
parses back to the same key. An id is trusted only on the ATS's own host,
except Greenhouse's gh_jid, which is global and appears on custom domains.
"""

import re
from collections import namedtuple
from urllib.parse import parse_qsl, urlsplit

AtsRef = namedtuple("AtsRef", "ats tenant job_id site", defaults=(None,))

ATSES = ("greenhouse", "lever", "ashby", "workable", "smartrecruiters", "workday")

_GH_PATH = re.compile(r"/jobs/(\d{6,})")
_UUID = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
_LEVER_PATH = re.compile(r"^/([^/]+)/(" + _UUID + ")", re.I)
_ASHBY_PATH = re.compile(r"^/([^/]+)/(" + _UUID + ")", re.I)
_WORKABLE_PATH = re.compile(r"^/(?:([^/]+)/)?j/([0-9A-Za-z]{6,})", re.I)
_SR_PATH = re.compile(r"^/([^/]+)/(\d{6,})(?:-|/|$)")
_LOCALE = re.compile(r"^[a-z]{2}-[A-Z]{2}$")
_WD_REQ = re.compile(r"_([A-Za-z0-9-]*\d[A-Za-z0-9-]*)$")


ATS_DOMAINS = ("greenhouse.io", "lever.co", "ashbyhq.com", "workable.com", "smartrecruiters.com",
               "myworkdayjobs.com", "myworkdaysite.com")


def _on_host(host, domain):
    return host == domain or host.endswith("." + domain)


def is_ats_host(host):
    """True for a host an ATS serves (any subdomain of ATS_DOMAINS), so a
    posting on any other host is on the employer's own site."""
    host = (host or "").lower().rstrip(".")
    return any(_on_host(host, d) for d in ATS_DOMAINS)


def employer_host(url):
    """A posting URL's host when it is the employer's own site, else ''."""
    try:
        host = (urlsplit(url).hostname or "").lower() if isinstance(url, str) else ""
    except ValueError:
        return ""
    return "" if not host or is_ats_host(host) else host


def _workday(host, segments):
    """(tenant, site, req id) from a Workday posting URL, or None."""
    if _on_host(host, "myworkdayjobs.com"):
        tenant = host.split(".")[0]
        segs = [s for s in segments if not _LOCALE.match(s)]
    elif _on_host(host, "myworkdaysite.com") and len(segments) > 2 and segments[0] == "recruiting":
        tenant = segments[1]
        segs = [s for s in segments[2:] if not _LOCALE.match(s)]
    else:
        return None
    if "job" not in segs or segs.index("job") == 0:
        return None
    site = segs[0]
    tail = [s for s in segs[segs.index("job") + 1:] if s not in ("apply", "applyManually")]
    if not tail:
        return None
    m = _WD_REQ.search(tail[-1])
    if not m:
        return None
    return tenant.lower(), site, m.group(1).lower()


def ats_ref(url):
    """The ATS posting a URL points at, or None. Never raises."""
    if not isinstance(url, str) or not url.strip():
        return None
    try:
        parts = urlsplit(url.strip())
        host = (parts.hostname or "").lower()
        query = parse_qsl(parts.query, keep_blank_values=True)
    except ValueError:
        return None
    if not host:
        return None
    segments = [s for s in parts.path.split("/") if s]
    on_gh = _on_host(host, "greenhouse.io")
    gh_tenant = None
    if on_gh:
        if segments and segments[0] not in ("embed", "v1"):
            gh_tenant = segments[0].lower()
        else:
            gh_tenant = next((v.lower() for k, v in query if k == "for" and v), None)
    gh_jid = next((v for k, v in query if k == "gh_jid" and v.isdigit()), None)
    if gh_jid:
        return AtsRef("greenhouse", gh_tenant, gh_jid)
    if on_gh:
        m = _GH_PATH.search(parts.path)
        if m:
            return AtsRef("greenhouse", gh_tenant, m.group(1))
        return None
    if _on_host(host, "lever.co"):
        m = _LEVER_PATH.match(parts.path)
        return AtsRef("lever", m.group(1).lower(), m.group(2).lower()) if m else None
    if host == "jobs.ashbyhq.com":
        m = _ASHBY_PATH.match(parts.path)
        return AtsRef("ashby", m.group(1).lower(), m.group(2).lower()) if m else None
    if host == "apply.workable.com":
        m = _WORKABLE_PATH.match(parts.path)
        return AtsRef("workable", (m.group(1) or "").lower() or None, m.group(2).upper()) if m else None
    if host == "jobs.smartrecruiters.com":
        m = _SR_PATH.match(parts.path)
        return AtsRef("smartrecruiters", m.group(1), m.group(2)) if m else None
    wd = _workday(host, segments)
    if wd:
        return AtsRef("workday", wd[0], wd[2], wd[1])
    return None


# Prefixes of posting keys built from an AtsRef (values/posting_key.py)
KEY_PREFIX = {"greenhouse": "gh", "lever": "lever", "ashby": "ashby", "workable": "workable",
              "smartrecruiters": "sr", "workday": "workday"}


def ref_key(ref):
    """The posting key of an AtsRef. Workday req ids are per tenant."""
    prefix = KEY_PREFIX[ref.ats]
    if ref.ats == "workday":
        return f"{prefix}:{ref.tenant}:{ref.job_id}"
    return f"{prefix}:{ref.job_id}"


# --- public JSON shapes, one normalizer per ATS --------------------------------
# Each returns dicts with: ats, tenant, job_id, url, title, location, company,
# first_published, updated_at, text (may be empty when the list has no body),
# internal_id. Times are ISO 8601 strings or None. Malformed entries are skipped.

def _iso_ms(ms):
    from datetime import datetime, timezone
    try:
        return datetime.fromtimestamp(int(ms) / 1000, tz=timezone.utc).isoformat(timespec="seconds")
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def _strip_html(html):
    import html as _html
    # Greenhouse sends its HTML escaped once (&lt;p&gt;), so unescape before stripping tags
    text = _html.unescape(html or "")
    text = re.sub(r"<br\s*/?>|</p>|</li>|</h\d>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = _html.unescape(text)
    return re.sub(r"[ \t\r\f\v]+", " ", re.sub(r"\n\s*\n+", "\n", text)).strip()


def _posting(ats, tenant, job_id, url, title, location, company, first_published, updated_at, text, internal_id=None):
    return dict(ats=ats, tenant=tenant, job_id=str(job_id), url=url, title=(title or "").strip(),
                location=(location or "").strip(), company=(company or "").strip(),
                first_published=first_published, updated_at=updated_at, text=text or "",
                internal_id=None if internal_id is None else str(internal_id))


def greenhouse_postings(token, body):
    out = []
    for j in (body or {}).get("jobs") or []:
        try:
            out.append(greenhouse_job(token, j))
        except (KeyError, TypeError, AttributeError):
            continue
    return out


def greenhouse_job(token, j):
    """One boards-api job (list item or /jobs/{id}) as a posting."""
    return _posting("greenhouse", token, j["id"], j.get("absolute_url") or f"https://job-boards.greenhouse.io/{token}/jobs/{j['id']}",
                    j.get("title"), (j.get("location") or {}).get("name"), j.get("company_name"),
                    j.get("first_published"), j.get("updated_at"), _strip_html(j.get("content")),
                    j.get("internal_job_id"))


def lever_postings(company, body):
    out = []
    for j in body if isinstance(body, list) else []:
        try:
            cats = j.get("categories") or {}
            text = "\n".join(filter(None, [j.get("descriptionPlain"), *[
                (l.get("text") or "") + "\n" + _strip_html(l.get("content")) for l in j.get("lists") or []],
                j.get("additionalPlain")]))
            out.append(_posting("lever", company, j["id"], j.get("hostedUrl") or f"https://jobs.lever.co/{company}/{j['id']}",
                                j.get("text"), cats.get("location"), company, _iso_ms(j.get("createdAt")),
                                _iso_ms(j.get("updatedAt") or j.get("createdAt")), text))
        except (KeyError, TypeError, AttributeError):
            continue
    return out


def ashby_postings(org, body):
    out = []
    for j in (body or {}).get("jobs") or []:
        try:
            if j.get("isListed") is False:
                continue
            loc = j.get("location") or ""
            if j.get("isRemote") and "remote" not in loc.lower():
                loc = f"{loc} (Remote)".strip()
            comp = (j.get("compensation") or {}).get("compensationTierSummary") or ""
            text = "\n".join(filter(None, [j.get("descriptionPlain") or _strip_html(j.get("descriptionHtml")), comp]))
            out.append(_posting("ashby", org, j["id"], j.get("jobUrl") or f"https://jobs.ashbyhq.com/{org}/{j['id']}",
                                j.get("title"), loc, org, j.get("publishedAt"), j.get("updatedAt") or j.get("publishedAt"), text))
        except (KeyError, TypeError, AttributeError):
            continue
    return out


def workable_postings(sub, body):
    out = []
    for j in (body or {}).get("jobs") or []:
        try:
            code = j["shortcode"]
            loc = ", ".join(filter(None, [j.get("city"), j.get("state"), j.get("country")]))
            if j.get("telecommuting"):
                loc = f"{loc} (Remote)".strip()
            out.append(_posting("workable", sub, str(code).upper(), f"https://apply.workable.com/{sub}/j/{code}/",
                                j.get("title"), loc, (body or {}).get("name") or sub, j.get("published_on") or j.get("created_at"),
                                j.get("published_on") or j.get("created_at"), _strip_html(j.get("description"))))
        except (KeyError, TypeError, AttributeError):
            continue
    return out


def smartrecruiters_postings(company, body):
    out = []
    for j in (body or {}).get("content") or []:
        try:
            loc = j.get("location") or {}
            where = ", ".join(filter(None, [loc.get("city"), loc.get("region"), (loc.get("country") or "").upper()]))
            if loc.get("remote"):
                where = f"{where} (Remote)".strip()
            out.append(_posting("smartrecruiters", company, j["id"], f"https://jobs.smartrecruiters.com/{company}/{j['id']}",
                                j.get("name"), where, (j.get("company") or {}).get("name") or company,
                                j.get("releasedDate"), j.get("releasedDate"), ""))
        except (KeyError, TypeError, AttributeError):
            continue
    return out


def workday_postings(host, tenant, site, body):
    """Workday cxs search results. The list has no description and no dates,
    only 'Posted Today' style text; postings without a req id are skipped."""
    out = []
    for j in (body or {}).get("jobPostings") or []:
        try:
            path = j["externalPath"]
            url = f"https://{host}/{site}{path}"
            ref = ats_ref(url)
            if not ref:
                continue
            out.append(_posting("workday", tenant, ref.job_id, url, j.get("title"), j.get("locationsText"),
                                tenant, None, None, ""))
            out[-1]["posted_text"] = j.get("postedOn") or ""
        except (KeyError, TypeError, AttributeError):
            continue
    return out
