"""bin/ats-poll (adrs/0015) with a fake client and a temp root: the hiring.cafe
cron window (midnight wrap included), the liveness stamp (every exit-0 run, not
a lock-held exit, not a dry run), the caps, emitted only after the CSV is
written, and the drop folder living under the data root."""
import csv
import fcntl
import importlib.machinery
import importlib.util
import json
import os
import re
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "domain" / "ats_registry"))
from adapters import ats as A  # noqa: E402
from ats_registry import AtsRegistry  # noqa: E402

import importlib
sys.path.insert(0, str(ROOT))
P = importlib.import_module("adapters.ats_poll")

NOW = datetime(2026, 10, 24, 6, 0, tzinfo=timezone.utc)
IDLE = {"batch": False, "regen": False}
TEXT = "Python, Spark and SQL pipelines for data. The pay range is $110,000 - $140,000. 2+ years of experience."


def jobs(n):
    return {"jobs": [{"id": 8000000 + i, "title": "Data Engineer", "company_name": f"Acme {i}", "internal_job_id": i,
                      "absolute_url": f"https://job-boards.greenhouse.io/acme/jobs/{8000000 + i}",
                      "location": {"name": "Austin, TX"}, "content": TEXT,
                      "first_published": (NOW - timedelta(hours=i + 1)).isoformat(),
                      "updated_at": (NOW - timedelta(hours=i + 1)).isoformat()} for i in range(n)]}


ENRICHED = []


def stub_enrich(rows):
    for r in rows:
        ENRICHED.append(r["company"])
        r.pop("company_homepage", None)
        r["company_linkedin"] = "linkedin.com/company/stub"
    return rows


P.default_enrich = stub_enrich  # no VPN lookups from tests


class Fake:
    def __init__(self, body):
        self.body = body
        self.stats = {"requests": 0, "ok": 0, "not_modified": 0, "failed": 0, "skipped": 0}

    def get(self, url):
        self.stats["requests"] += 1
        if url == f"{A.BASES['greenhouse']}/v1/boards/acme/jobs?content=true":
            self.stats["ok"] += 1
            return A.Response(200, json.dumps(self.body))
        self.stats["failed"] += 1
        return A.Response(404)

    def post_json(self, url, body):
        return A.Response(404)

    def out_of_budget(self):
        return False


def fresh_root():
    root = Path(tempfile.mkdtemp())
    AtsRegistry(root / "ats_registry.jsonl").add_board("greenhouse", "acme", verified_status=200)
    out = root / "Downloads"
    out.mkdir()
    return root, out


def csvs(out):
    return sorted(p for p in out.iterdir() if re.match(r"job_listings_\d+\.csv$", p.name))


def test_cron_window_with_midnight_wrap():
    at = lambda h, m, d=24: datetime(2026, 10, d, h, m, tzinfo=timezone.utc)
    assert P.in_cron_window(at(23, 40)) and P.in_cron_window(at(23, 35)), "window before hour 0 of the next day"
    assert P.in_cron_window(at(0, 15)) and not P.in_cron_window(at(0, 16))
    assert not P.in_cron_window(at(3, 34)) and P.in_cron_window(at(3, 35))
    assert not P.in_cron_window(at(6, 0)) and not P.in_cron_window(at(12, 16))
    assert tuple(P.CRON_HOURS) == (0, 4, 8, 12, 16, 20)


def test_run_writes_one_capped_csv_then_marks_emitted():
    root, out = fresh_root()
    rc = P.main([], root=root, out_dir=out, client=Fake(jobs(12)), now=NOW, running=IDLE, log=lambda s: None)
    assert rc == 0
    files = csvs(out)
    assert len(files) == 1
    rows = list(csv.DictReader(open(files[0])))
    assert len(rows) == 8 and rows[0]["Scraped URL"].endswith("/8000000"), "newest first, capped at 8"
    reg = AtsRegistry(root / "ats_registry.jsonl")
    assert len(reg.emitted()) == 8 and all(e["lane"] for e in reg.emitted())
    assert (root / "ats_poll.stamp").exists()
    assert (root / "ats_poll.log").read_text().startswith(NOW.isoformat(timespec="seconds") + " ATS_POLL: boards=1 ")
    # next run: the 8 are known, 4 remain
    P.main([], root=root, out_dir=out, client=Fake(jobs(12)), now=NOW + timedelta(minutes=15), running=IDLE, log=lambda s: None)
    assert len(AtsRegistry(root / "ats_registry.jsonl").emitted()) == 12
    assert not [p for p in out.iterdir() if p.name.startswith(".")], "no temp file left behind"


def test_hosts_learned_from_board_lists_not_on_dry_run():
    root, out = fresh_root()
    body = jobs(2)
    body["jobs"][0]["absolute_url"] = "https://careers.acme.com/jobs/8000000?gh_jid=8000000"
    P.main(["--dry-run"], root=root, out_dir=out, client=Fake(body), now=NOW, running=IDLE, log=lambda s: None)
    assert dict(AtsRegistry(root / "ats_registry.jsonl").hosts()) == {}
    P.main([], root=root, out_dir=out, client=Fake(body), now=NOW, running=IDLE, log=lambda s: None)
    assert dict(AtsRegistry(root / "ats_registry.jsonl").hosts()) == {"careers.acme.com": "acme"}


def test_daily_cap_counts_emitted_today():
    root, out = fresh_root()
    reg = AtsRegistry(root / "ats_registry.jsonl")
    for i in range(38):
        reg.mark_emitted("greenhouse", "acme", f"9{i:06d}", key=f"gh:9{i:06d}", detected_at=NOW.replace(hour=1).isoformat())
    P.main([], root=root, out_dir=out, client=Fake(jobs(12)), now=NOW, running=IDLE, log=lambda s: None)
    assert len(list(csv.DictReader(open(csvs(out)[0])))) == 2


def test_empty_run_touches_stamp_writes_nothing():
    root = Path(tempfile.mkdtemp())          # no boards registered
    out = root / "Downloads"
    out.mkdir()
    # No boards registered: the run does nothing, but it must still prove liveness.
    rc = P.main([], root=root, out_dir=out, client=Fake(jobs(3)), now=NOW, running=IDLE, log=lambda s: None)
    assert rc == 0 and csvs(out) == []
    stamp = root / "ats_poll.stamp"
    assert stamp.exists(), "an exit-0 run refreshes the stamp"
    os.utime(stamp, (1, 1))
    P.main([], root=root, out_dir=out, client=Fake(jobs(3)), now=NOW.replace(hour=4, minute=5), running=IDLE, log=lambda s: None)
    assert stamp.stat().st_mtime > 1


def test_lock_held_exits_zero_without_stamp():
    root, out = fresh_root()
    fd = os.open(root / "ats_poll.lock", os.O_CREAT | os.O_RDWR)
    fcntl.flock(fd, fcntl.LOCK_EX)
    try:
        rc = P.main([], root=root, out_dir=out, client=Fake(jobs(3)), now=NOW, running=IDLE, log=lambda s: None)
    finally:
        os.close(fd)
    assert rc == 0 and not (root / "ats_poll.stamp").exists() and csvs(out) == []


def test_dry_run_writes_nothing():
    root, out = fresh_root()
    lines = []
    rc = P.main(["--dry-run"], root=root, out_dir=out, client=Fake(jobs(3)), now=NOW, running=IDLE, log=lines.append)
    assert rc == 0 and csvs(out) == [] and not (root / "ats_poll.stamp").exists() and not (root / "ats_poll.log").exists()
    assert AtsRegistry(root / "ats_registry.jsonl").emitted() == ()
    assert lines[0].startswith("ATS_POLL: ") and "rows=3" in lines[0] and "dry_run=1" in lines[0]


def test_failed_csv_write_marks_nothing():
    root, out = fresh_root()
    rc = P.main([], root=root, out_dir=root / "missing", client=Fake(jobs(3)), now=NOW, running=IDLE, log=lambda s: None)
    assert rc == 1 and AtsRegistry(root / "ats_registry.jsonl").emitted() == ()
    assert not (root / "ats_poll.stamp").exists(), "a failing run never refreshes the stamp"


def test_rows_carry_tech_stack_and_company_link():
    import pandas as pd
    root, out = fresh_root()
    os.environ["ENRICH"] = "1"
    try:
        P.main([], root=root, out_dir=out, client=Fake(jobs(3)), now=NOW, running=IDLE, log=lambda s: None)
    finally:
        os.environ.pop("ENRICH", None)
    df = pd.read_csv(csvs(out)[0])
    assert list(df["Tech Stack"]) == ["Python, Spark, SQL"] * 3
    assert list(df["Company LinkedIn"]) == ["linkedin.com/company/stub"] * 3
    assert "company_homepage" not in df.columns


def test_company_links_stop_at_deadline_and_on_errors():
    rows = [{"company": f"C{i}", "company_linkedin": "", "company_homepage": f"careers{i}.example"} for i in range(3)]
    ticks = iter([0, P.ENRICH_DEADLINE_S - 1, P.ENRICH_DEADLINE_S])
    assert P.add_company_links(rows, 0, stub_enrich, lambda: next(ticks), log=lambda m: None) == 2
    assert [r["company_linkedin"] for r in rows] == ["linkedin.com/company/stub"] * 2 + ["careers2.example"]
    assert all("company_homepage" not in r for r in rows)

    def boom(rows):
        raise RuntimeError("vpn down")
    logged = []
    row = {"company": "D", "company_linkedin": "", "company_homepage": "d.example"}
    assert P.add_company_links([row], 0, boom, lambda: 0, log=logged.append) == 0
    assert row == {"company": "D", "company_linkedin": "d.example"} and "vpn down" in logged[0]


def test_dry_run_looks_nothing_up():
    root, out = fresh_root()
    ENRICHED.clear()
    P.main(["--dry-run"], root=root, out_dir=out, client=Fake(jobs(3)), now=NOW, running=IDLE, log=lambda s: None)
    assert ENRICHED == []


def test_drop_folder_lives_under_the_data_root():
    for f in ("process_stream.py", "hc_scraper.py", "adapters/ats_poll.py"):
        text = (ROOT / f).read_text()
        private_home = "/home/" + "scraper"
        assert '"drop"' in text and private_home not in text, f




def test_blocked_companies_come_from_the_filters_document():
    import json as _json
    with tempfile.TemporaryDirectory() as tmp:
        doc = _json.loads((ROOT / "filters" / "example.json").read_text())
        doc["blocked_companies"] = ["acme"]
        path = Path(tmp) / "filters.json"
        path.write_text(_json.dumps(doc))
        old = os.environ.get("JOBKIT_FILTERS")
        os.environ["JOBKIT_FILTERS"] = str(path)
        try:
            blocked = P.blocked_companies()
        finally:
            if old is None:
                os.environ.pop("JOBKIT_FILTERS", None)
            else:
                os.environ["JOBKIT_FILTERS"] = old
    assert "acme" in blocked, blocked

if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
    print(f"ATS_POLL:MET {len(tests)} tests")
