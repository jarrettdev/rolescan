"""Scrape CSV contract (adrs/0004): a CSV written by hc_scraper.write_csv is
ingested by goals/ingest-listings, and every column process_stream reads off a
notified row exists. Fails when the writer and the readers disagree."""
import importlib.util
import json
import re
import sys
import tempfile
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "values"))
sys.path.insert(0, str(ROOT / "domain" / "ledger"))
import hc_scraper  # noqa: E402
from ledger import Ledger  # noqa: E402
from scrape_csv import SCRAPE_COLUMNS  # noqa: E402


def _ingest_goal():
    spec = importlib.util.spec_from_file_location(
        "ingest_listings_goal", ROOT / "goals" / "ingest-listings" / "implementation.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _rows():
    hits = json.loads((ROOT / "fixtures" / "raw" / "search_hits.json").read_text())
    rows = hc_scraper._GOAL.select_listings(hits)
    for r in rows:  # enrichment without the network
        r.pop("company_homepage")
        r["company_linkedin"] = r["company_linkedin"] or "linkedin.com/company/acme"
    return rows


def test_written_csv_ingests_and_carries_every_read_column():
    tmp = Path(tempfile.mkdtemp())
    path = hc_scraper.write_csv(_rows(), out_dir=str(tmp))
    assert re.search(r"job_listings_\d+\.csv$", path), path  # process_stream's filename pattern
    df = pd.read_csv(path)
    assert list(df.columns) == SCRAPE_COLUMNS

    goal = _ingest_goal()
    with Ledger(tmp / "processed_jobs.csv") as ledger:
        result = goal.ingest_listings(df, datetime(2026, 10, 4, 4, 0), ledger)
    assert len(result.notify) == 5 and result.unkeyed == 1, result  # the bare hit has no URL: notified, counted
    assert result.notify["Salary"].iloc[0] == "$90000"

    read = set(re.findall(r"job\['([A-Z][^']+)'\]", (ROOT / "process_stream.py").read_text()))
    missing = read - set(result.notify.columns)
    assert not missing, f"process_stream reads columns the scrape CSV lacks: {missing}"


def test_header_has_one_home():
    hits = [p for p in ROOT.rglob("*.py")
            if not any(part in {"venv", "node_modules", "autojob", "legacy", "tests"} for part in p.parts)
            and re.search(r"""['"]Years of Experience['"]\s*,""", p.read_text())]
    assert hits == [ROOT / "values" / "scrape_csv.py"], hits


if __name__ == "__main__":
    import warnings
    warnings.simplefilter("ignore", FutureWarning)
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
    print(f"SCRAPE_CONTRACT:MET {len(tests)} tests")
