"""--dry-run and --limit (adrs/0009), without a browser."""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import hc_scraper  # noqa: E402

HITS = json.loads((ROOT / "fixtures" / "raw" / "search_hits.json").read_text())


def test_report_counts_raw_selected_new_and_source_mix():
    known = {hc_scraper._key({"apply_url": HITS[0]["apply_url"]})}   # hit 1 is already in the ledger
    lines = hc_scraper.dry_run_report({"A": HITS[:5], "B": HITS[5:]}, known=known)
    table = {l.split()[0]: l.split()[-3:] for l in lines[1:3]}
    assert table["A"][0] == "5" and table["B"][0] == str(len(HITS) - 5), lines
    total = next(l for l in lines if l.startswith("TOTAL"))
    assert total.split()[-3:] == [str(len(HITS)), "5", "3"], lines   # 5 selected; new excludes the known posting and the url-less row
    assert lines[-1].startswith("source mix under the view cap:"), lines


def test_failed_filter_is_reported_not_counted_as_zero():
    lines = hc_scraper.dry_run_report({"A": HITS, "B": None}, known=set())
    assert any(l.startswith("B") and "FAILED" in l for l in lines), lines


class _FakeSB:
    """A browser whose first navigations land without search data."""
    def __init__(self, misses):
        self.misses, self.opens = misses, 0
        self.cdp = self

    def open(self, url):
        self.opens += 1

    def sleep(self, s):
        pass

    def evaluate(self, js):
        if self.opens <= self.misses:
            return None
        return json.dumps({"props": {"pageProps": {"ssrHits": [{"objectID": "1"}], "ssrIsLastPage": True}}})


def test_fetch_page_retries_then_fails_loudly():
    hc_scraper.try_solve_captcha = lambda sb, label: False
    sb = _FakeSB(misses=2)
    assert hc_scraper.fetch_page(sb, None, {}) == ([{"objectID": "1"}], True) and sb.opens == 3
    try:
        hc_scraper.fetch_page(_FakeSB(misses=9), None, {})
        failed = False
    except hc_scraper.FetchFailed:
        failed = True
    assert failed, "a page with no search data must not pass as zero jobs"


def test_limit_prefers_new_then_greenhouse():
    rows = [{"apply_url": "https://jobs.lever.co/x/11111111-1111-1111-1111-111111111111"},
            {"apply_url": "https://boards.greenhouse.io/a/jobs/5117557001"},
            {"apply_url": "https://boards.greenhouse.io/a/jobs/5117557002"},
            {"apply_url": ""}]
    got = hc_scraper.limit_rows(rows, 2, known={"gh:5117557001"})
    assert [r["apply_url"] for r in got] == ["https://boards.greenhouse.io/a/jobs/5117557002",
                                             "https://jobs.lever.co/x/11111111-1111-1111-1111-111111111111"]


def test_scrape_filter_keeps_earlier_pages_when_a_later_page_fails():
    pages = iter([([{"objectID": "1"}], False), hc_scraper.FetchFailed("page 1")])

    def fake_fetch(sb, build_id, config, page_num=0, page_size=40):
        item = next(pages)
        if isinstance(item, Exception):
            raise item
        return item
    saved = hc_scraper.fetch_page
    hc_scraper.fetch_page = fake_fetch
    try:
        got = hc_scraper.scrape_filter(_FakeSB(0), {"name": "X", "config": {}}, 0, 1, None)
    finally:
        hc_scraper.fetch_page = saved
    assert got == [{"objectID": "1"}]


def test_cron_run_caps_rows_and_dry_run_skips_screenshots():
    seen = {}
    rows = [{"apply_url": f"https://boards.greenhouse.io/a/jobs/51175570{i:02d}", "company": "A",
             "company_linkedin": "", "company_homepage": ""} for i in range(40)]
    saved = (hc_scraper.scrape_all_filters, hc_scraper._GOAL.select_listings, hc_scraper.write_csv,
             hc_scraper.write_debug_json, hc_scraper.enrich, hc_scraper._ledger_keys)
    hc_scraper.scrape_all_filters = lambda filters, screenshots, per_filter: (seen.setdefault("shots", []).append(screenshots), [{}])[1]
    hc_scraper._GOAL.select_listings = lambda jobs, **kwargs: rows
    hc_scraper.enrich = lambda r: r
    hc_scraper.write_csv = lambda r: seen.setdefault("written", len(r))
    hc_scraper.write_debug_json = lambda r: None
    hc_scraper._ledger_keys = lambda: set()
    saved_cands = hc_scraper.write_board_candidates
    hc_scraper.write_board_candidates = lambda jobs: seen.setdefault("candidates", len(jobs))
    try:
        hc_scraper.main([])
        assert seen["candidates"] == 1, "a cron run writes the raw hits as board candidates"
        assert seen["written"] == hc_scraper.MAX_ROWS_PER_RUN, seen
        assert seen["shots"] == [True]
    finally:
        (hc_scraper.scrape_all_filters, hc_scraper._GOAL.select_listings, hc_scraper.write_csv,
         hc_scraper.write_debug_json, hc_scraper.enrich, hc_scraper._ledger_keys) = saved
        hc_scraper.write_board_candidates = saved_cands
    shots = []
    hc_scraper.scrape_all_filters = lambda filters, screenshots, per_filter: (shots.append(screenshots), per_filter.update({"A": []}), [])[2]
    hc_scraper._ledger_keys = lambda: set()
    try:
        hc_scraper.main(["--dry-run"])
    finally:
        hc_scraper.scrape_all_filters = saved[0]
        hc_scraper._ledger_keys = saved[5]
    assert shots == [False], "dry-run must not take screenshots"


def test_dry_run_writes_nothing():
    calls = []
    for fn in ("write_csv", "write_debug_json", "enrich", "save_screenshot", "ensure_screenshot_dir", "write_board_candidates"):
        setattr(hc_scraper, fn, lambda *a, _n=fn, **k: calls.append(_n))
    hc_scraper.scrape_all_filters = lambda filters, screenshots, per_filter: (per_filter.update({"A": HITS}), HITS)[1]
    hc_scraper._ledger_keys = lambda: set()
    hc_scraper.main(["--dry-run"])
    assert calls == [], calls


def test_board_candidates_file():
    import tempfile
    d = tempfile.mkdtemp()
    old = os.path.join(d, "1.txt")
    open(old, "w").write("x\n")
    os.utime(old, (1, 1))
    keep = os.path.join(d, "notes.md")
    open(keep, "w").write("x")
    hits = [{"apply_url": "https://jobs.ashbyhq.com/a/b"}, {"apply_url": "https://jobs.ashbyhq.com/a/b"},
            {"apply_url": " https://x.myworkdayjobs.com/s/job/l/t_R1 "}, {"apply_url": ""}, {}, "junk"]
    path = hc_scraper.write_board_candidates(hits, out_dir=d, now=1_800_000_000)
    assert open(path).read().split() == ["https://jobs.ashbyhq.com/a/b", "https://x.myworkdayjobs.com/s/job/l/t_R1"]
    assert oct(os.stat(path).st_mode & 0o777) == "0o644"
    assert not os.path.exists(old) and os.path.exists(keep), "old .txt files go, other files stay"
    assert hc_scraper.write_board_candidates([], out_dir=d) is None
    assert hc_scraper.write_board_candidates(hits, out_dir="/proc/no/such/dir") is None, "never raises"


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
    print(f"DRY_RUN:MET {len(tests)} tests")
