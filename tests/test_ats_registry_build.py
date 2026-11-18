"""bin/ats-registry build with a fake client: a board is added only on a 200,
known boards are not re-verified, a custom Greenhouse host is mapped only when
its board's API job shows that host (a stale gh_jid is not), SmartRecruiters
needs one posting, and the summary line counts it all."""
import importlib.machinery
import importlib.util
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "domain" / "ats_registry"))
from adapters import ats as A  # noqa: E402
from ats_registry import AtsRegistry  # noqa: E402

loader = importlib.machinery.SourceFileLoader("ats_registry_bin", str(ROOT / "bin" / "ats-registry"))
spec = importlib.util.spec_from_loader("ats_registry_bin", loader)
BIN = importlib.util.module_from_spec(spec)
loader.exec_module(BIN)

GH, EMB, SR = A.BASES["greenhouse"], A.BASES["greenhouse_embed"], A.BASES["smartrecruiters"]


class Fake:
    def __init__(self, routes):
        self.routes, self.calls = routes, []
        self.stats = {"requests": 0, "skipped": 0}

    def _r(self, url):
        self.calls.append(url)
        self.stats["requests"] += 1
        code, val = self.routes.get(url, (404, None))
        if code in (301, 302):
            return A.Response(code, None, None, False, val)
        return A.Response(code, json.dumps(val) if val is not None else None)

    def get(self, url):
        return self._r(url)

    def post_json(self, url, body):
        return self._r(url)

    def location(self, url):
        r = self._r(url)
        return r.status, r.location

    def out_of_budget(self):
        return False


def routes():
    return {
        f"{GH}/v1/boards/roblox": (200, {"name": "Roblox"}),
        f"{GH}/v1/boards/gone": (404, None),
        f"{EMB}/embed/job_app?token=8000001": (301, "/embed/job_app?for=roblox&token=8000001"),
        f"{GH}/v1/boards/roblox/jobs/8000001": (200, {"id": 8000001, "absolute_url": "https://careers.roblox.com/jobs/8000001?gh_jid=8000001"}),
        f"{EMB}/embed/job_app?token=5555555": (301, "/embed/job_app?for=acme&token=5555555"),
        f"{GH}/v1/boards/acme/jobs/5555555": (200, {"id": 5555555, "absolute_url": "https://job-boards.greenhouse.io/acme/jobs/5555555"}),
        f"{SR}/v1/companies/Visa/postings?limit=1": (200, {"totalFound": 0, "content": []}),
        f"{SR}/v1/companies/Acme/postings?limit=1": (200, {"totalFound": 3, "content": [{}]}),
    }


URLS = ["https://job-boards.greenhouse.io/roblox/jobs/8283707", "https://job-boards.greenhouse.io/gone/jobs/1234567",
        "https://careers.roblox.com/jobs/8000001?gh_jid=8000001", "https://optiver.com/c/5555555?gh_jid=5555555",
        "https://jobs.smartrecruiters.com/Visa/744000012345678-x", "https://jobs.smartrecruiters.com/Acme/744000012345679-y",
        "https://example.com/not-ats"]


def test_build_adds_only_verified_and_maps_hosts():
    reg = AtsRegistry(Path(tempfile.mkdtemp()) / "r.jsonl")
    lines = []
    out = BIN.build(reg, Fake(routes()), URLS, log=lines.append)
    boards = {(b["ats"], b["tenant"]) for b in reg.boards()}
    assert boards == {("greenhouse", "roblox"), ("smartrecruiters", "Acme")}, boards
    assert dict(reg.hosts()) == {"careers.roblox.com": "roblox"}
    assert out["hosts_failed"] == ["optiver.com"], out
    assert sorted(out["failed"]) == ["greenhouse:gone 404", "smartrecruiters:Visa 404"], out
    assert lines[-1].startswith("ATS_REGISTRY: boards added=2 known=0 failed=2 hosts added=1 failed=1 boards_guessed=0 candidates_ignored=1"), lines[-1]


def test_company_guess_maps_a_single_employer_host_only():
    r = routes()
    r[f"{EMB}/embed/job_app?token=6000001"] = (404, None)          # closed sample: embed fails
    r[f"{GH}/v1/boards/acmeco"] = (200, {"name": "Acme Co"})
    r[f"{GH}/v1/boards/acmeco/jobs?content=true"] = (200, {"jobs": [{"id": 6000002, "title": "x",
                                                                     "absolute_url": "https://careers.acme.co/jobs/6000002?gh_jid=6000002"}]})
    r[f"{EMB}/embed/job_app?token=7000001"] = (404, None)
    r[f"{GH}/v1/boards/lyft"] = (200, {"name": "Lyft"})
    r[f"{GH}/v1/boards/lyft/jobs?content=true"] = (200, {"jobs": [{"id": 7000002, "title": "x",
                                                                   "absolute_url": "https://app.careerpuck.com/job-board/lyft?gh_jid=7000002"}]})
    urls = ["https://careers.acme.co/jobs/6000001?gh_jid=6000001", "https://app.careerpuck.com/a?gh_jid=7000001",
            "https://app.careerpuck.com/b?gh_jid=7000003"]
    companies = {urls[0]: "Acme Co", urls[1]: "Lyft", urls[2]: "Earnest"}
    reg = AtsRegistry(Path(tempfile.mkdtemp()) / "r.jsonl")
    BIN.build(reg, Fake(r), urls, log=lambda s: None, companies=companies)
    assert dict(reg.hosts()) == {"careers.acme.co": "acmeco"}, "a guessed board maps a single-employer host"
    assert {b["tenant"] for b in reg.boards()} == {"acmeco", "lyft"}, "an aggregator's boards are registered, its host is not"


def test_guess_needs_jobs_on_the_host():
    r = routes()
    r[f"{EMB}/embed/job_app?token=6000001"] = (404, None)
    r[f"{GH}/v1/boards/acmeco"] = (200, {"name": "Acme Co"})
    r[f"{GH}/v1/boards/acmeco/jobs?content=true"] = (200, {"jobs": [{"id": 1, "title": "x", "absolute_url": "https://other.com/1?gh_jid=1"}]})
    reg = AtsRegistry(Path(tempfile.mkdtemp()) / "r.jsonl")
    BIN.build(reg, Fake(r), ["https://careers.acme.co/jobs/6000001?gh_jid=6000001"], log=lambda s: None,
              companies={"https://careers.acme.co/jobs/6000001?gh_jid=6000001": "Acme Co"})
    assert dict(reg.hosts()) == {} and len(reg) == 0


def test_rebuild_skips_known_boards_and_hosts():
    reg = AtsRegistry(Path(tempfile.mkdtemp()) / "r.jsonl")
    BIN.build(reg, Fake(routes()), URLS, log=lambda s: None)
    fake = Fake(routes())
    out = BIN.build(reg, fake, URLS, log=lambda s: None)
    assert out["added"] == 0 and out["hosts_added"] == 0
    assert f"{GH}/v1/boards/roblox" not in fake.calls
    assert not any("8000001" in c for c in fake.calls), "a mapped host is not resolved again"


def test_limit_caps_work():
    reg = AtsRegistry(Path(tempfile.mkdtemp()) / "r.jsonl")
    fake = Fake(routes())
    BIN.build(reg, fake, URLS, limit=1, log=lambda s: None)
    assert len(reg) <= 2 and len(fake.calls) <= 5, fake.calls


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
    print(f"ATS_REGISTRY_BUILD:MET {len(tests)} tests")
