#!/usr/bin/env python3
"""Ingest one scraped batch and notify the postings that match the user's filters.

This replaces the original watcher + resume pipeline. There is no daemon: run it
once, from cron or by hand.

    process_stream.py --once data/drop/job_listings_1767000000000.csv
    process_stream.py --fixtures fixtures/run1 --dry-run
    process_stream.py --fixtures fixtures/run1 --dry-run --filters filters/example.json

Exit codes: 0 ran, 2 nothing to read or no readable rows, 3 missing secret.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent
for entry in (ROOT, ROOT / "values", ROOT / "domain" / "ledger", ROOT / "adapters"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

import lanes as L  # noqa: E402
from adapters import config, notify, paths  # noqa: E402
from ledger import Ledger  # noqa: E402


def _load_ingest_goal():
    path = ROOT / "goals" / "ingest-listings" / "implementation.py"
    spec = importlib.util.spec_from_file_location("kit_ingest_listings", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


INGEST = _load_ingest_goal()


def batch_time(path: Path) -> datetime:
    match = re.search(r"job_listings_(\d+)\.csv$", path.name)
    if match:
        return datetime.fromtimestamp(int(match.group(1)) / 1000)
    return datetime.fromtimestamp(path.stat().st_mtime)


def match_lanes(frame: pd.DataFrame, lanes: list) -> pd.DataFrame:
    """Rows a configured lane accepts, with the lane name attached."""
    if frame.empty:
        return frame
    keep = []
    for index, row in zip(frame.index, frame.to_dict("records")):
        lane = L.lane_for(row.get("Title"), row.get("Description"), lanes)
        if lane:
            keep.append((index, lane.name))
    if not keep:
        return frame.iloc[0:0].assign(lane=[])
    indexed = frame.loc[[index for index, _ in keep]].copy()
    indexed["lane"] = [name for _, name in keep]
    return indexed


def run_batch(path: Path, *, lanes: list, dry_run: bool, title_exclude: list | None = None) -> dict:
    frame = pd.read_csv(path)
    stamped = batch_time(path)
    excluded = [x for x in (title_exclude or []) if x]
    if excluded and "Title" in frame.columns:
        pattern = "|".join(re.escape(x) for x in excluded)
        frame = frame[~frame["Title"].str.contains(pattern, case=False, na=False)]
    matching = match_lanes(frame, lanes)
    summary = {"file": str(path), "rows": len(frame), "matched": len(matching),
               "repeats": 0, "unkeyed": 0, "notified": 0, "lane": ""}
    if matching.empty:
        return summary
    ledger_path = paths.data_path("processed_jobs.csv")
    pattern = "|".join(re.escape(x) for x in (title_exclude or []) if x) or None
    if dry_run:
        ledger = Ledger(ledger_path)
        result = INGEST.ingest_listings(matching, stamped, ledger, title_exclude=pattern)
    else:
        with Ledger(ledger_path, exclusive=True) as ledger:
            result = INGEST.ingest_listings(matching, stamped, ledger, title_exclude=pattern)
            ledger.save()
    summary["repeats"] = result.repeats
    summary["unkeyed"] = result.unkeyed
    posts = [{
        "title": row.get("Title", ""),
        "company": row.get("Company", ""),
        "location": row.get("Location", ""),
        "salary": row.get("Salary", ""),
        "apply_url": row.get("Scraped URL", ""),
        "lane": row.get("lane", ""),
    } for row in result.notify.to_dict("records")]
    summary["notified"] = len(posts)
    summary["lane"] = ", ".join(sorted({str(p.get("lane", "")) for p in posts if p.get("lane")}))
    if posts:
        cfg = config.notify_config()
        notify.send(posts, cfg, dry_run=dry_run)
    return summary


def fixture_files(directory: Path) -> list[Path]:
    return sorted(directory.glob("job_listings_*.csv"))


def copy_to_drop(files: list[Path]) -> list[Path]:
    if not files:
        return []
    stamp = time.strftime("%Y%m%dT%H%M%S")
    drop = paths.data_root() / "drop" / stamp
    drop.mkdir(parents=True, exist_ok=True)
    copied = []
    for source in files:
        target = drop / source.name
        shutil.copy2(source, target)
        copied.append(target)
    return copied


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ingest a scraped batch and notify matches.")
    parser.add_argument("--once", type=Path, help="one job_listings_*.csv to ingest")
    parser.add_argument("--fixtures", type=Path, help="directory of job_listings_*.csv to ingest")
    parser.add_argument("--dry-run", action="store_true", help="notify prints; no ledger write")
    parser.add_argument("--filters", type=Path, default=None, help="filters document (default: JOBKIT_FILTERS)")
    args = parser.parse_args(argv)

    filters = args.filters or paths.filters_path()
    if not filters.exists():
        print(f"FILTERS_MISSING: {filters}", file=sys.stderr)
        return 2
    try:
        doc = json.loads(filters.read_text())
        unknown = [f.get("location") for f in doc.get("filters", []) if f.get("location") not in doc.get("locations", {})]
        if unknown:
            print(f"FILTERS_INVALID: {filters}: /filters location {unknown[0]!r} is not a key in /locations", file=sys.stderr)
            return 2
        lanes = L.load(filters)
    except (KeyError, ValueError, TypeError, OSError) as error:
        print(f"FILTERS_INVALID: {filters}: {error}", file=sys.stderr)
        return 2
    title_exclude = [str(x) for x in doc.get("title_exclude") or [] if str(x).strip()]

    if args.fixtures:
        files = copy_to_drop(fixture_files(args.fixtures)) if not args.dry_run else fixture_files(args.fixtures)
        if not files:
            print(f"NO_FIXTURES: {args.fixtures}", file=sys.stderr)
            return 2
    elif args.once:
        if not args.once.exists():
            print(f"NO_SUCH_FILE: {args.once}", file=sys.stderr)
            return 2
        files = [args.once]
    else:
        drop = paths.data_root() / "drop"
        files = sorted(drop.glob("job_listings_*.csv")) if drop.exists() else []
        if not files:
            print("NOTHING_TO_DO: no job_listings_*.csv under data/drop", file=sys.stderr)
            return 2

    try:
        summaries = [run_batch(path, lanes=lanes, dry_run=args.dry_run, title_exclude=title_exclude) for path in files]
    except config.MissingSecret as error:
        print(str(error), file=sys.stderr)
        return 3

    matched = sum(item["matched"] for item in summaries)
    notified = sum(item["notified"] for item in summaries)
    print(f"batches={len(summaries)} rows={sum(item['rows'] for item in summaries)} "
          f"matched={matched} notified={notified} "
          f"repeats={sum(item['repeats'] for item in summaries)} "
          f"dry_run={args.dry_run} filters={filters}")
    for item in summaries:
        print(f"  {Path(item['file']).name}: rows={item['rows']} matched={item['matched']} "
              f"notified={item['notified']} lane={item['lane'] or '-'}")
    return 0 if matched else 2


if __name__ == "__main__":
    raise SystemExit(main())
