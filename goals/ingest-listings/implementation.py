"""Goal ingest-listings: decide which scraped rows are new postings to notify.

Ported from process_stream.process_file (frozen at
integrity/legacy/process_file_legacy.py), disclosed in emit-manifest.json.
Identity is the Ledger's posting key (adrs/0001), not the seven mutable
fields legacy concatenated. Records through Ledger.record() only; writes no
Ledger state. Pure otherwise: a batch in, the rows to notify out.
"""

import sys
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "domain" / "ledger"))
from ledger import Ledger, listing_key  # noqa: E402

REQUIRED_COLUMNS = ("Title", "Time Posted", "Scraped URL")
# Seniority filter, verbatim from legacy: case-insensitive words, then the
# case-sensitive Sr/SR abbreviation.
SENIOR_WORDS = "Senior|Staff|Manager|Lead|Principal"
SENIOR_ABBREV = "Sr|SR"


class MissingColumn(ValueError):
    """The scraped batch lacks a column this goal reads."""


@dataclass(frozen=True)
class IngestResult:
    notify: pd.DataFrame
    repeats: int
    unkeyed: int


def _parse_time_posted(series: pd.Series) -> pd.Series:
    # nlc:rule=R-goal-no-noun-write
    # nlc:rule=R-one-posting-one-dm  # nlc:obligation=a posting key is recorded once; Ledger.record refuses a key it already holds, so a posting is notified once
    # Same string surgery as legacy, including its 'daysays' repair for
    # values already rendered as "0 days 00:00:00" on a previous write.
    return pd.to_timedelta(series.astype(str).str.replace('h', ' hours').str.replace('d', ' days').str.replace('daysays', 'days'))


def ingest_listings(batch: pd.DataFrame, file_datetime, ledger: Ledger, title_exclude: str = SENIOR_WORDS) -> IngestResult:
    """Public goal entrypoint.

    batch: rows of one scrape CSV. file_datetime: when that scrape ran.
    Returns the rows whose postings the ledger did not hold (now recorded,
    not yet saved; the caller calls ledger.save()).
    """
    missing = [c for c in REQUIRED_COLUMNS if c not in batch.columns]
    if missing:
        raise MissingColumn(f"batch lacks columns {missing}")

    df = batch.copy()
    df['processed_at'] = file_datetime.strftime('%Y-%m-%d %H:%M:%S')
    df['Time Posted'] = _parse_time_posted(df['Time Posted'])
    df['Timestamp Posted'] = (file_datetime - df['Time Posted']).dt.strftime('%Y-%m-%d %H:%M:%S')

    df = df[~df['Title'].str.contains(title_exclude, case=False, na=False)]
    df = df[~df['Title'].str.contains(SENIOR_ABBREV, case=True, na=False)]

    keep = []
    repeats = 0
    unkeyed = 0
    for idx, row in zip(df.index, df.to_dict("records")):
        if ledger.record(row):
            keep.append(idx)
            if listing_key(row).startswith("legacy:"):
                unkeyed += 1
        else:
            repeats += 1
    return IngestResult(notify=df.loc[keep], repeats=repeats, unkeyed=unkeyed)
