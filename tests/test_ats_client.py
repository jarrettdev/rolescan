"""adapters/ats.py against a local HTTP server (adrs/0015): exact headers,
ETag cache and 304, gzip, per-host floor, backoff on 429/5xx, timeout, run
budget, POST, manual redirects, and Greenhouse facts per A10 (closed only with
a verified token; a stale gh_jid is unknown, not closed)."""
import gzip
import json
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from adapters import ats as A  # noqa: E402

SEEN = []
JOB = {"id": 8283707, "title": "Software Engineer, Reliability", "company_name": "Roblox", "internal_job_id": 40933,
       "absolute_url": "https://careers.roblox.com/jobs/8283707?gh_jid=8283707", "location": {"name": "San Mateo, CA"},
       "first_published": "2026-10-23T13:53:14-04:00", "updated_at": "2026-10-23T14:00:00-04:00", "content": "&lt;p&gt;Go&lt;/p&gt;"}
ROUTES = {
    "/v1/boards/roblox/jobs/8283707": (200, JOB),
    "/v1/boards/acme/jobs/5555555": (200, dict(JOB, id=5555555, absolute_url="https://job-boards.greenhouse.io/acme/jobs/5555555")),
    "/embed/job_app?token=8283707": (301, "/embed/job_app?for=roblox&token=8283707"),
    "/embed/job_app?token=5555555": (301, "/embed/job_app?for=acme&token=5555555"),
}


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _reply(self, code, body=b"", headers=()):
        self.send_response(code)
        for k, v in headers:
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        SEEN.append((self.command, self.path, dict(self.headers)))
        p = self.path
        if p == "/etag":
            if self.headers.get("If-None-Match") == '"v1"':
                return self._reply(304)
            body = gzip.compress(json.dumps({"jobs": [1]}).encode())
            return self._reply(200, body, [("ETag", '"v1"'), ("Content-Encoding", "gzip")])
        if p in ("/429", "/500"):
            return self._reply(int(p[1:]))
        if p == "/slow":
            time.sleep(1.5)
            return self._reply(200, b"{}")
        if p in ROUTES:
            code, val = ROUTES[p]
            if code == 301:
                return self._reply(301, b"", [("Location", val)])
            return self._reply(code, json.dumps(val).encode(), [("ETag", '"j"')])
        return self._reply(404)

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(n)
        SEEN.append((self.command, self.path, dict(self.headers)))
        self._reply(200, json.dumps({"echo": json.loads(body)}).encode())


SRV = ThreadingHTTPServer(("127.0.0.1", 0), H)
threading.Thread(target=SRV.serve_forever, daemon=True).start()
BASE = f"http://127.0.0.1:{SRV.server_address[1]}"
A.BASES.update(greenhouse=BASE, greenhouse_embed=BASE)


def client(**kw):
    return A.Client(cache_dir=tempfile.mkdtemp(), floor_s=kw.pop("floor_s", 0), **kw)


def test_headers_are_exactly_the_project_set():
    SEEN.clear()
    client().get(f"{BASE}/etag")
    h = {k.lower(): v for k, v in SEEN[0][2].items()}
    sent = {k for k in h if k not in ("host", "connection")}
    assert sent == {"user-agent", "accept", "accept-encoding"}, sent
    assert h["user-agent"] == A.USER_AGENT == "job_scraper-ats-poller/1.0 (low-rate reader of public job board APIs)"
    assert set(A.HEADERS) == {"User-Agent", "Accept", "Accept-Encoding"}


def test_etag_cache_and_gzip():
    c = client()
    r1 = c.get(f"{BASE}/etag")
    assert r1.status == 200 and json.loads(r1.body) == {"jobs": [1]} and not r1.from_cache
    SEEN.clear()
    r2 = c.get(f"{BASE}/etag")
    assert SEEN[0][2].get("If-None-Match") == '"v1"'
    assert r2.status == 200 and r2.from_cache and json.loads(r2.body) == {"jobs": [1]}
    assert c.stats["not_modified"] == 1 and c.stats["ok"] == 1


def test_per_host_floor():
    c = client(floor_s=0.3)
    t0 = time.monotonic()
    for _ in range(3):
        c.get(f"{BASE}/nothing")
    assert time.monotonic() - t0 >= 0.6, "three requests to one host must be at least 0.3 s apart"


def test_backoff_on_429_and_repeated_5xx():
    c = client()
    assert c.get(f"{BASE}/429").status == 429
    SEEN.clear()
    assert c.get(f"{BASE}/etag").status == 0, "429: a backed-off host gets no more requests"
    assert SEEN == [] and c.stats["skipped"] == 1
    c = client()
    assert c.get(f"{BASE}/500").status == 500 and c.get(f"{BASE}/500").status == 500
    assert c.get(f"{BASE}/etag").status == 200, "two 5xx (one slow board) do not cost the host"
    assert c.get(f"{BASE}/500").status == 500
    SEEN.clear()
    assert c.get(f"{BASE}/etag").status == 0 and SEEN == [], "a third 5xx leaves the host alone"
    assert A.HOST_5XX_LIMIT == 3


def test_timeout_and_budget_never_raise():
    assert client(timeout_s=0.5).get(f"{BASE}/slow").status == 0
    now = [0.0]
    c = client(budget_s=10, clock=lambda: now[0], sleep=lambda s: None)
    assert c.get(f"{BASE}/etag").status == 200
    now[0] = 11
    SEEN.clear()
    assert c.get(f"{BASE}/etag").status == 0 and SEEN == []
    assert client().get("http://127.0.0.1:1/refused").status == 0


def test_post_json_and_manual_redirect():
    c = client()
    r = c.post_json(f"{BASE}/wday/cxs/x/y/jobs", {"limit": 20})
    assert r.status == 200 and json.loads(r.body) == {"echo": {"limit": 20}}
    assert c.location(f"{BASE}/embed/job_app?token=8283707") == (301, "/embed/job_app?for=roblox&token=8283707")


def test_facts_rebranded_board_open():
    f = A.greenhouse_facts("https://careers.roblox.com/jobs/8283707?gh_jid=8283707", client())
    assert f["status"] == "open" and f["token"] == "roblox" and f["internal_job_id"] == "40933" and f["text"] == "Go", f


def test_facts_stale_gh_jid_is_unknown_not_closed():
    # embed names a board, but the API job lives on another host: not this posting
    assert A.greenhouse_facts("https://optiver.com/careers/5555555?gh_jid=5555555", client())["status"] == "unknown"
    # embed 404 (closed or bogus, indistinguishable): unknown
    assert A.greenhouse_facts("https://example.com/careers?gh_jid=9999999", client())["status"] == "unknown"


def test_facts_closed_needs_a_verified_token():
    assert A.greenhouse_facts("https://job-boards.greenhouse.io/couriernewsroom/jobs/4464497009", client())["status"] == "closed"
    hosts = {"careers.example.com": "example"}
    assert A.greenhouse_facts("https://careers.example.com/x?gh_jid=1234567", client(), hosts)["status"] == "closed"
    assert A.greenhouse_facts("https://careers.other.com/x?gh_jid=1234567", client())["status"] == "unknown"
    assert A.greenhouse_facts("https://jobs.lever.co/a/240d459b-696d-43eb-8497-fab3e56ecd9b", client())["status"] == "unknown"


def test_list_board_greenhouse_shapes_postings():
    ROUTES["/v1/boards/roblox/jobs?content=true"] = (200, {"jobs": [JOB]})
    got = A.list_board(client(), {"ats": "greenhouse", "tenant": "roblox"})
    assert len(got) == 1 and got[0]["job_id"] == "8283707" and got[0]["text"] == "Go"
    assert A.list_board(client(), {"ats": "greenhouse", "tenant": "missing"}) is None




def test_cache_lives_under_the_data_root():
    from pathlib import Path
    import adapters.ats as A
    cache = A.cache_dir()
    assert "data" in Path(cache).parts, f"cache is not under data: {cache}"

if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
    SRV.shutdown()
    print(f"ATS_CLIENT:MET {len(tests)} tests")
