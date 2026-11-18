"""The network side of the ATS-direct source (adrs/0015): one polite HTTP
client and a fetcher per ATS. Parsing and normalizing are pure and live in
values/ats.py; this module only moves bytes.

Every request carries the same two headers and nothing that identifies a
person. Bodies are cached with their ETag and re-sent as If-None-Match, so an
unchanged board costs a 304 with no body. Requests to one host are at least
FLOOR_S apart, a host that answers 429 (or 5xx three times) is left alone for
the rest of the run, and a run stops making requests after its wall budget. Nothing here
raises on a network failure: callers get status 0.
"""

import gzip
import hashlib
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request
from collections import namedtuple
from pathlib import Path
from urllib.parse import quote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "values"))
import ats as V  # noqa: E402  (values/ats.py)

# nlc:rule=R-ats-requests-anonymous  # nlc:obligation=every request to an ATS API carries exactly the fixed project headers: no name, email, handle or contact
USER_AGENT = "job_scraper-ats-poller/1.0 (low-rate reader of public job board APIs)"
HEADERS = {"User-Agent": USER_AGENT, "Accept": "application/json", "Accept-Encoding": "gzip"}
FLOOR_S = 0.5
HOST_5XX_LIMIT = 3  # 5xx answers from one host in a run before it is left alone
TIMEOUT_S = 15
BUDGET_S = 720
CACHE_DIR = Path(os.environ.get("JOBKIT_DATA") or ROOT / "data") / ".cache" / "ats"

Response = namedtuple("Response", "status body etag from_cache location", defaults=(None, None, False, None))

# API bases, overridable so tests can point them at a local server
BASES = {
    "greenhouse": "https://boards-api.greenhouse.io",
    "greenhouse_embed": "https://boards.greenhouse.io",
    "lever": "https://api.lever.co",
    "ashby": "https://api.ashbyhq.com",
    "workable": "https://apply.workable.com",
    "smartrecruiters": "https://api.smartrecruiters.com",
    "workday": None,  # per tenant: https://<host>
}


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


class Client:
    """Thread-safe: callers run one worker per host."""

    def __init__(self, cache_dir=CACHE_DIR, floor_s=FLOOR_S, timeout_s=TIMEOUT_S, budget_s=BUDGET_S,
                 clock=time.monotonic, sleep=time.sleep):
        self.cache_dir = Path(cache_dir)
        self.floor_s, self.timeout_s, self.budget_s = floor_s, timeout_s, budget_s
        self.clock, self.sleep = clock, sleep
        self.started = clock()
        self._last = {}
        self._host_locks = {}
        self._mu = threading.Lock()
        self.backed_off = set()
        self._5xx = {}
        self.stats = {"requests": 0, "ok": 0, "not_modified": 0, "failed": 0, "skipped": 0}

    def _count(self, k):
        with self._mu:
            self.stats[k] += 1

    def _host_lock(self, host):
        with self._mu:
            return self._host_locks.setdefault(host, threading.Lock())

    def _cache_path(self, url):
        return self.cache_dir / (hashlib.sha1(url.encode()).hexdigest() + ".json")

    def _read_cache(self, url):
        try:
            return json.loads(self._cache_path(url).read_text())
        except (OSError, ValueError):
            return None

    def _write_cache(self, url, etag, body):
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            tmp = self._cache_path(url).with_suffix(f".{os.getpid()}.tmp")
            tmp.write_text(json.dumps({"etag": etag, "body": body}))
            tmp.replace(self._cache_path(url))
        except OSError:
            pass

    def out_of_budget(self):
        return self.clock() - self.started > self.budget_s

    def _send(self, url, data=None, extra=None, follow=True):
        host = (urlsplit(url).hostname or "").lower()
        if host in self.backed_off or self.out_of_budget():
            self._count("skipped")
            return Response(0)
        with self._host_lock(host):
            wait = self.floor_s - (self.clock() - self._last.get(host, -1e9))
            if wait > 0:
                self.sleep(wait)
            self._last[host] = self.clock()
            headers = dict(HEADERS, **(extra or {}))
            req = urllib.request.Request(url, data=data, headers=headers, method="POST" if data is not None else "GET")
            opener = urllib.request.build_opener() if follow else urllib.request.build_opener(_NoRedirect)
            self._count("requests")
            try:
                with opener.open(req, timeout=self.timeout_s) as r:
                    raw = r.read()
                    if r.headers.get("Content-Encoding") == "gzip":
                        raw = gzip.decompress(raw)
                    return Response(r.status, raw.decode("utf-8", "replace"), r.headers.get("ETag"))
            except urllib.error.HTTPError as e:
                # 429 means slow down: leave the host alone now. A 5xx may be
                # one oversized board timing out at the gateway, so only a
                # host that keeps answering 5xx is left alone
                with self._mu:
                    if e.code >= 500:
                        self._5xx[host] = self._5xx.get(host, 0) + 1
                    if e.code == 429 or self._5xx.get(host, 0) >= HOST_5XX_LIMIT:
                        self.backed_off.add(host)
                return Response(e.code, None, None, False, e.headers.get("Location") if e.headers else None)
            except (urllib.error.URLError, OSError, ValueError):
                return Response(0)

    def get(self, url):
        """GET with the ETag cache. 304 returns the cached body."""
        cached = self._read_cache(url)
        extra = {"If-None-Match": cached["etag"]} if cached and cached.get("etag") else None
        r = self._send(url, extra=extra)
        if r.status == 304 and cached:
            self._count("not_modified")
            return Response(200, cached["body"], cached["etag"], True)
        if r.status == 200:
            self._count("ok")
            if r.etag:
                self._write_cache(url, r.etag, r.body)
        else:
            self._count("failed")
        return r

    def post_json(self, url, body):
        r = self._send(url, data=json.dumps(body).encode(), extra={"Content-Type": "application/json"})
        self._count("ok" if r.status == 200 else "failed")
        return r

    def location(self, url):
        """GET without following redirects: (status, Location header)."""
        r = self._send(url, follow=False)
        return r.status, r.location


def _json(r):
    if r.status != 200 or not r.body:
        return None
    try:
        return json.loads(r.body)
    except ValueError:
        return None


# --- Greenhouse: token resolution and facts for one posting (adrs/0015 A10) --

def greenhouse_token(url, client, hosts=None):
    """(token, verified) for a Greenhouse posting URL. Verified tokens come
    from a greenhouse.io path or a registry host; an embed-redirect token is
    unverified until the API job's absolute_url shows the same host."""
    ref = V.ats_ref(url)
    if not ref or ref.ats != "greenhouse":
        return None, False
    if ref.tenant:
        return ref.tenant, True
    host = (urlsplit(url).hostname or "").lower()
    if hosts and host in hosts:
        return hosts[host], True
    status, loc = client.location(f"{BASES['greenhouse_embed']}/embed/job_app?token={ref.job_id}")
    if status in (301, 302, 303, 307, 308) and loc:
        from urllib.parse import parse_qs
        board = (parse_qs(urlsplit(loc).query).get("for") or [None])[0]
        return (board.lower() if board else None), False
    return None, False


def greenhouse_facts(url, client, hosts=None):
    """What the boards API says about one posting. status is 'open',
    'closed' (404 with a verified token) or 'unknown' (anything else)."""
    unknown = {"status": "unknown", "token": None}
    ref = V.ats_ref(url)
    if not ref or ref.ats != "greenhouse":
        return unknown
    token, verified = greenhouse_token(url, client, hosts)
    if not token:
        return unknown
    r = client.get(f"{BASES['greenhouse']}/v1/boards/{quote(token)}/jobs/{ref.job_id}")
    if r.status == 404:
        return {"status": "closed", "token": token} if verified else dict(unknown, token=token)
    job = _json(r)
    if not job:
        return dict(unknown, token=token)
    if not verified:
        api_host = (urlsplit(job.get("absolute_url") or "").hostname or "").lower()
        if api_host != (urlsplit(url).hostname or "").lower():
            return dict(unknown, token=token)  # a stale gh_jid pointing at another board
    p = V.greenhouse_job(token, job)
    return dict(status="open", token=token, internal_job_id=p["internal_id"], first_published=p["first_published"],
                updated_at=p["updated_at"], company_name=p["company"], title=p["title"], text=p["text"],
                absolute_url=p["url"])


# --- board lists, one per ATS --------------------------------------------------

def list_board(client, board):
    """Postings on one registry board, or None when the request failed."""
    ats, t = board["ats"], board["tenant"]
    if ats == "greenhouse":
        # content=true: one request carries every description, so Greenhouse
        # needs no detail requests; the ETag makes an unchanged board a 304
        body = _json(client.get(f"{BASES['greenhouse']}/v1/boards/{quote(t)}/jobs?content=true"))
        return None if body is None else V.greenhouse_postings(t, body)
    if ats == "lever":
        body = _json(client.get(f"{BASES['lever']}/v0/postings/{quote(t)}?mode=json"))
        return None if body is None else V.lever_postings(t, body)
    if ats == "ashby":
        body = _json(client.get(f"{BASES['ashby']}/posting-api/job-board/{quote(t)}?includeCompensation=true"))
        return None if body is None else V.ashby_postings(t, body)
    if ats == "workable":
        body = _json(client.get(f"{BASES['workable']}/api/v1/widget/accounts/{quote(t)}"))
        return None if body is None else V.workable_postings(t, body)
    if ats == "smartrecruiters":
        body = _json(client.get(f"{BASES['smartrecruiters']}/v1/companies/{quote(t)}/postings?limit=100"))
        return None if body is None else V.smartrecruiters_postings(t, body)
    if ats == "workday":
        base = BASES["workday"] or f"https://{board['host']}"
        body = _json(client.post_json(f"{base}/wday/cxs/{quote(t)}/{quote(board['site'])}/jobs",
                                      {"appliedFacets": {}, "limit": 20, "offset": 0, "searchText": ""}))
        return None if body is None else V.workday_postings(board["host"], t, board["site"], body)
    return None


def fill_detail(client, board, posting):
    """Add text (and dates the list lacks) to one posting, in place. Returns
    False when the detail request failed; the posting is then left as is."""
    ats, t = board["ats"], board["tenant"]
    if ats == "smartrecruiters":
        job = _json(client.get(f"{BASES['smartrecruiters']}/v1/companies/{quote(t)}/postings/{posting['job_id']}"))
        if not job:
            return False
        sections = ((job.get("jobAd") or {}).get("sections") or {})
        posting["text"] = "\n".join(V._strip_html((s or {}).get("text")) for s in sections.values() if isinstance(s, dict))
        return True
    if ats == "workday":
        base = BASES["workday"] or f"https://{board['host']}"
        path = urlsplit(posting["url"]).path.split(f"/{board['site']}", 1)[-1]
        job = _json(client.get(f"{base}/wday/cxs/{quote(t)}/{quote(board['site'])}{path}"))
        info = (job or {}).get("jobPostingInfo") or {}
        if not info:
            return False
        posting["text"] = V._strip_html(info.get("jobDescription"))
        if info.get("startDate"):
            posting["first_published"] = posting["updated_at"] = f"{info['startDate']}T00:00:00+00:00"
        return True
    return True  # greenhouse (content=true), lever, ashby and workable lists carry the description


# --- registry verification (bin/ats-registry, adrs/0015) ---------------------

def verify_board(client, entry):
    """200 when the board's public API answers for it with postings data,
    else the failing status (0 for no answer). SmartRecruiters answers 200
    with zero postings for any name, so a board there needs one posting."""
    ats, t = entry["ats"], entry["tenant"]
    if ats == "greenhouse":
        r = client.get(f"{BASES['greenhouse']}/v1/boards/{quote(t)}")
        return 200 if r.status == 200 and isinstance(_json(r), dict) else (r.status or 0)
    if ats == "workday":
        base = BASES["workday"] or f"https://{entry['host']}"
        r = client.post_json(f"{base}/wday/cxs/{quote(t)}/{quote(entry['site'])}/jobs",
                             {"appliedFacets": {}, "limit": 1, "offset": 0, "searchText": ""})
        body = _json(r)
        return 200 if isinstance(body, dict) and "jobPostings" in body else (r.status if r.status != 200 else 404)
    if ats == "smartrecruiters":
        r = client.get(f"{BASES['smartrecruiters']}/v1/companies/{quote(t)}/postings?limit=1")
        body = _json(r)
        return 200 if isinstance(body, dict) and (body.get("totalFound") or 0) > 0 else (r.status if r.status != 200 else 404)
    postings = list_board(client, entry)
    return 200 if postings is not None else 404


def resolve_host(client, host, samples):
    """The Greenhouse board behind a custom domain, or None: the embed
    redirect names a board and that board's API job shows this host."""
    for url in samples:
        token, _ = greenhouse_token(url, client)
        if not token:
            continue
        ref = V.ats_ref(url)
        job = _json(client.get(f"{BASES['greenhouse']}/v1/boards/{quote(token)}/jobs/{ref.job_id}"))
        if job and (urlsplit(job.get("absolute_url") or "").hostname or "").lower() == host:
            return token
    return None
