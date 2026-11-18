"""values/ats.py and the posting keys built from it (adrs/0015): each ATS's
hiring.cafe apply URL and its API URL give the same key, ids are trusted only
on the ATS's own host, and the normalizers turn real response shapes into
postings whose URL keys back to the same posting."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "values"))
from ats import (AtsRef, ats_ref, ashby_postings, employer_host, is_ats_host, greenhouse_postings, lever_postings,  # noqa: E402
                 smartrecruiters_postings, workable_postings, workday_postings)
from posting_key import UnkeyedListing, posting_key  # noqa: E402

UUID = "240d459b-696d-43eb-8497-fab3e56ecd9b"


def test_greenhouse_forms():
    assert ats_ref("https://job-boards.greenhouse.io/roblox/jobs/8283707") == AtsRef("greenhouse", "roblox", "8283707")
    assert ats_ref("https://boards.greenhouse.io/Axon/jobs/8033215003?gh_src=x") == AtsRef("greenhouse", "axon", "8033215003")
    # rebranded board: the id is global, the board is unknown from the URL
    assert ats_ref("https://careers.roblox.com/jobs/8283707?gh_jid=8283707") == AtsRef("greenhouse", None, "8283707")
    assert ats_ref("https://job-boards.greenhouse.io/embed/job_app?for=roblox&token=8283707") is None
    for u in ("https://job-boards.greenhouse.io/roblox/jobs/8283707",
              "https://careers.roblox.com/jobs/8283707?gh_jid=8283707",
              "https://boards.greenhouse.io/roblox/jobs/8283707?gh_jid=8283707"):
        assert posting_key(u) == "gh:8283707", u


def test_lever_forms():
    api = f"https://jobs.lever.co/leverdemo/{UUID}"
    assert ats_ref(api) == AtsRef("lever", "leverdemo", UUID)
    assert posting_key(api) == posting_key(api + "/apply") == f"lever:{UUID}"


def test_ashby_forms():
    api = f"https://jobs.ashbyhq.com/openai/{UUID}"
    assert ats_ref(api) == AtsRef("ashby", "openai", UUID)
    assert posting_key(api) == posting_key(f"https://jobs.ashbyhq.com/OpenAI/{UUID.upper()}/application?utm_source=hc") == f"ashby:{UUID}"


def test_workable_forms():
    assert ats_ref("https://apply.workable.com/acme/j/ABC123DEF4/") == AtsRef("workable", "acme", "ABC123DEF4")
    assert posting_key("https://apply.workable.com/acme/j/ABC123DEF4/") == posting_key("https://apply.workable.com/j/abc123def4") == "workable:ABC123DEF4"


def test_smartrecruiters_forms():
    assert ats_ref("https://jobs.smartrecruiters.com/Visa/744000012345678-data-engineer") == AtsRef("smartrecruiters", "Visa", "744000012345678")
    assert posting_key("https://jobs.smartrecruiters.com/Visa/744000012345678-data-engineer") == \
        posting_key("https://jobs.smartrecruiters.com/Visa/744000012345678") == "sr:744000012345678"


def test_workday_forms():
    path = "/job/US-CA-Santa-Clara/Principal-Architect--System-Software---Orbital-Data-Center_JR2019010"
    api = f"https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite{path}"
    hc = f"https://nvidia.wd5.myworkdayjobs.com/en-US/NVIDIAExternalCareerSite{path}/apply"
    assert ats_ref(api) == AtsRef("workday", "nvidia", "jr2019010", "NVIDIAExternalCareerSite")
    assert posting_key(api) == posting_key(hc) == "workday:nvidia:jr2019010"
    site = f"https://wd1.myworkdaysite.com/recruiting/acme/External{path}"
    assert posting_key(site) == "workday:acme:jr2019010"
    # same req id at another tenant is another posting
    assert posting_key(api.replace("nvidia.wd5", "intel.wd1")) != posting_key(api)


def test_ids_only_on_own_host():
    for u in (f"https://example.com/openai/{UUID}", "https://example.com/acme/j/ABC123DEF4",
              "https://example.com/Visa/744000012345678", "https://example.com/jobs/8283707",
              f"https://notlever.co.evil.com/x/{UUID}"):
        assert ats_ref(u) is None, u
        assert posting_key(u).startswith("url:"), u


def test_unrecognised_and_malformed():
    assert ats_ref("") is None and ats_ref(None) is None and ats_ref("http://[::1") is None
    assert ats_ref("https://jobs.ashbyhq.com/openai") is None
    assert ats_ref("https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite") is None
    try:
        posting_key("nan")
        raise AssertionError("nan keyed")
    except UnkeyedListing:
        pass


def test_normalizers_key_back():
    gh = greenhouse_postings("roblox", {"jobs": [{"id": 8283707, "title": "Software Engineer, Reliability",
                                                  "absolute_url": "https://careers.roblox.com/jobs/8283707?gh_jid=8283707",
                                                  "location": {"name": "San Mateo, CA, United States"},
                                                  "first_published": "2026-10-20T10:00:00-04:00", "updated_at": "2026-10-21T10:00:00-04:00",
                                                  "internal_job_id": 40933, "company_name": "Roblox",
                                                  "content": "&lt;p&gt;Build &amp;amp; run &lt;b&gt;things&lt;/b&gt;&lt;/p&gt;"}, {"bad": 1}]})
    assert len(gh) == 1 and gh[0]["internal_id"] == "40933" and gh[0]["text"] == "Build & run things", gh
    lv = lever_postings("leverdemo", [{"id": UUID, "text": "Data Engineer", "hostedUrl": f"https://jobs.lever.co/leverdemo/{UUID}",
                                       "categories": {"location": "Atlanta, Georgia"}, "createdAt": 1788199939703,
                                       "descriptionPlain": "Python", "lists": [{"text": "Req", "content": "<li>SQL</li>"}]}])
    assert lv[0]["first_published"].startswith("2026-") and "SQL" in lv[0]["text"]
    ab = ashby_postings("openai", {"jobs": [{"id": UUID, "title": "Research Engineer", "location": "San Francisco",
                                             "jobUrl": f"https://jobs.ashbyhq.com/openai/{UUID}", "publishedAt": "2026-10-22T00:00:00Z",
                                             "descriptionPlain": "LLM evals"}, {"id": "x", "isListed": False}]})
    assert len(ab) == 1
    wk = workable_postings("acme", {"name": "Acme", "jobs": [{"shortcode": "abc123def4", "title": "SRE", "country": "United States",
                                                              "published_on": "2026-10-22"}]})
    sr = smartrecruiters_postings("Visa", {"content": [{"id": "744000012345678", "name": "Data Engineer",
                                                        "location": {"city": "Austin", "region": "TX", "country": "us"},
                                                        "releasedDate": "2026-10-22T00:00:00.000Z"}]})
    wd = workday_postings("nvidia.wd5.myworkdayjobs.com", "nvidia", "NVIDIAExternalCareerSite",
                          {"jobPostings": [{"title": "Architect", "externalPath": "/job/US-CA-Santa-Clara/Architect_JR2019010",
                                            "postedOn": "Posted Today", "locationsText": "2 Locations"}, {"title": "no path"}]})
    assert len(wd) == 1 and wd[0]["posted_text"] == "Posted Today"
    for p in gh + lv + ab + wk + sr + wd:
        ref = ats_ref(p["url"])
        assert ref and ref.job_id == p["job_id"], (p["url"], ref, p["job_id"])


def test_is_ats_host():
    for h in ("job-boards.greenhouse.io", "boards.greenhouse.io", "jobs.lever.co", "jobs.ashbyhq.com",
              "apply.workable.com", "jobs.smartrecruiters.com", "nvidia.wd5.myworkdayjobs.com",
              "wd1.myworkdaysite.com", "JOBS.LEVER.CO."):
        assert is_ats_host(h), h
    for h in ("careers.roblox.com", "notgreenhouse.io", "greenhouse.io.evil.com", "", None):
        assert not is_ats_host(h), h
    assert employer_host("https://careers.roblox.com/jobs/8283707?gh_jid=8283707") == "careers.roblox.com"
    for u in ("https://job-boards.greenhouse.io/acme/jobs/1", "https://jobs.lever.co/x/y", "", None, "http://[bad"):
        assert employer_host(u) == "", u


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
    print(f"ATS_VALUES:MET {len(tests)} tests")
