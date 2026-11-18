"""linkedin_lookup offline (adrs/0004): cache hit, homepage footer, search
fallback, misses not cached. _fetch is stubbed and subprocess is booby-trapped,
so this never touches the network or the real cache."""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import linkedin_lookup as ll  # noqa: E402


def _no_subprocess(*a, **k):
    raise AssertionError("linkedin_lookup tried to run a subprocess in a test")


subprocess.run = _no_subprocess


def _setup(pages, cache=None):
    """Point the module at a temp cache and a fake web of url -> html."""
    path = Path(tempfile.mkdtemp()) / "linkedin_cache.json"
    if cache is not None:
        path.write_text(json.dumps(cache))
    ll.CACHE_PATH = str(path)
    ll._cache = None
    fetched = []
    ll._fetch = lambda url, timeout: (fetched.append(url), pages.get(url, ""))[1]
    return path, fetched


def test_cache_hit_skips_fetch():
    _, fetched = _setup({}, cache={"acme": "linkedin.com/company/acme-inc"})
    assert ll.find_linkedin("  Acme ") == "linkedin.com/company/acme-inc"
    assert fetched == []


def test_homepage_footer_found_and_cached():
    path, fetched = _setup({"https://acme.example": '<footer><a href="https://www.linkedin.com/company/acme-co/">in</a></footer>'})
    assert ll.find_linkedin("Acme", "acme.example") == "linkedin.com/company/acme-co"
    assert fetched == ["https://acme.example"]
    assert json.loads(path.read_text()) == {"acme": "linkedin.com/company/acme-co"}


def test_search_breadcrumb_fallback():
    _, fetched = _setup({})
    ll._fetch = lambda url, timeout: (fetched.append(url), "linkedin.com › company › pathai" if "bing" in url else "")[1]
    assert ll.find_linkedin("PathAI", "") == "linkedin.com/company/pathai"
    assert len(fetched) == 1 and "bing.com" in fetched[0]


def test_fetch_failure_returns_empty_and_is_not_cached():
    path, fetched = _setup({})
    assert ll.find_linkedin("Nowhere Corp", "nowhere.example") == ""
    assert len(fetched) == 3  # homepage, bing, duckduckgo
    assert not path.exists()


def test_blank_company_returns_empty():
    _, fetched = _setup({})
    assert ll.find_linkedin("  ") == "" and fetched == []


def test_enrich_link_then_homepage_and_logs_failures():
    _, fetched = _setup({}, cache={"acme": "linkedin.com/company/acme-inc"})
    rows = [{"company": "Acme", "company_linkedin": "", "company_homepage": "acme.example"},
            {"company": "Nowhere Corp", "company_linkedin": "", "company_homepage": "careers.nowhere.example"},
            {"company": "Direct", "company_linkedin": "linkedin.com/company/direct", "company_homepage": ""}]
    out = ll.enrich(rows, log=lambda m: None)
    assert [r["company_linkedin"] for r in out] == ["linkedin.com/company/acme-inc", "careers.nowhere.example",
                                                    "linkedin.com/company/direct"]
    assert all("company_homepage" not in r for r in out)
    saved, logged = ll.find_linkedin, []
    ll.find_linkedin = lambda c, h: 1 / 0
    try:
        row = ll.enrich([{"company": "Boom", "company_linkedin": "", "company_homepage": "boom.example"}], logged.append)[0]
    finally:
        ll.find_linkedin = saved
    assert row["company_linkedin"] == "boom.example" and logged and "Boom" in logged[0]


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
    print(f"LINKEDIN_LOOKUP:MET {len(tests)} tests")
