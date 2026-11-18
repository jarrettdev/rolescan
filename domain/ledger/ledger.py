"""Ledger noun: every job ever DM'd to the owner, one entry per posting.

State is private. The only way in is record(), which keys a row by its
posting identity (values/posting_key.py) and refuses a second row for a key
it already holds. save() appends under a file lock; nothing edits or
removes an entry (adrs/0001).
"""

import fcntl
import os
import sys
from contextlib import contextmanager
from pathlib import Path
from types import MappingProxyType

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "values"))
from posting_key import UnkeyedListing, listing_key, posting_key  # noqa: E402,F401  (re-exported)

def _default_home() -> Path:
    """Resolved at use time so JOBKIT_DATA changed after import still wins."""
    from adapters import paths
    return paths.data_path("processed_jobs.csv")
URL_COLUMN = "Scraped URL"


class HeaderDrift(ValueError):
    """A row carries columns the ledger file's header does not; appending
    would silently drop them."""


class Ledger:
    """State changes only through record() and save(). Outside writes are
    refused: views are read-only and attribute assignment raises. This
    stops the ordinary ways in (NLC gate 1 misses subscript and setattr
    writes, and does not scan the repo root); object.__setattr__ is still
    possible in Python and is out of scope."""

    def __init__(self, path: Path | None = None, exclusive: bool = False) -> None:
        """exclusive=True takes the file lock before loading and holds it
        until __exit__: use `with Ledger(path, exclusive=True) as ledger:` so
        load -> record -> save is one decision no other writer can split."""
        self._set("_path", Path(path) if path else _default_home())
        self._set("_lock", None)
        if exclusive:
            lock = open(f"{self._path}.lock", "a")
            fcntl.flock(lock, fcntl.LOCK_EX)
            self._set("_lock", lock)
        columns, rows = self._read()
        first: dict = {}
        duplicates = 0
        legacy = 0
        for row in rows:
            key = listing_key(row)
            if key.startswith("legacy:"):
                legacy += 1
            if key in first:
                duplicates += 1
            else:
                first[key] = MappingProxyType(dict(row))
        self._set("_columns", tuple(columns))
        self._set("_entries", MappingProxyType(first))
        self._set("_pending", ())
        self._set("_history_duplicates", duplicates)
        self._set("_history_unkeyed", legacy)

    def __setattr__(self, name, value):
        raise AttributeError(f"Ledger state changes only through record()/save(); refusing to set {name!r}")

    def _set(self, name, value) -> None:
        object.__setattr__(self, name, value)

    def _read(self):
        if self._path.exists() and self._path.stat().st_size > 0:
            df = pd.read_csv(self._path)
            return list(df.columns), df.to_dict("records")
        return [], []

    def __enter__(self):
        return self

    def __exit__(self, *exc) -> None:
        if self._lock is not None:
            fcntl.flock(self._lock, fcntl.LOCK_UN)
            self._lock.close()
            self._set("_lock", None)

    @contextmanager
    def _locked(self):
        if self._lock is not None:
            yield
            return
        with open(f"{self._path}.lock", "a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)

    def __len__(self) -> int:
        return len(self._entries)

    def __contains__(self, key: str) -> bool:
        return key in self._entries

    def get(self, key: str):
        return self._entries.get(key)

    def keys(self):
        return self._entries.keys()

    @property
    def history_duplicates(self) -> int:
        """Rows on disk that repeat a posting already in the ledger (pre-ADR 0001)."""
        return self._history_duplicates

    @property
    def history_unkeyed(self) -> int:
        """Rows on disk with no usable URL, identified by the legacy fields."""
        return self._history_unkeyed

    @property
    def pending(self) -> int:
        return len(self._pending)

    def record(self, row: dict) -> bool:
        """The one mutation path. True if this posting is new and was added,
        False if the ledger already holds it (nothing changes)."""
        if not hasattr(row, "get") or not hasattr(row, "keys"):
            raise TypeError(f"record() needs a mapping row, got {type(row).__name__}")
        key = listing_key(row)
        if key in self._entries:
            return False
        frozen = MappingProxyType(dict(row))
        self._set("_entries", MappingProxyType({**self._entries, key: frozen}))
        self._set("_pending", self._pending + (frozen,))
        return True

    def save(self) -> int:
        """Append rows recorded since load; existing rows are never rewritten.
        Under the lock it re-reads the file and skips rows another writer
        already appended. Returns how many rows were appended."""
        # nlc:rule=R-ledger-append-only  # nlc:obligation=existing ledger rows are never rewritten or removed; save() only appends rows recorded since load
        if not self._pending:
            return 0
        with self._locked():
            columns, rows = self._read()
            on_disk = {listing_key(r) for r in rows}
            fresh = [dict(r) for r in self._pending if listing_key(r) not in on_disk]
            header = list(columns)
            if not header:
                for r in fresh:
                    header += [c for c in r if c not in header]
            extra = sorted({c for r in fresh for c in r} - set(header))
            if extra:
                raise HeaderDrift(f"columns {extra} are not in the ledger header; refusing to drop them")
            if fresh:
                needs_newline = False
                if self._path.exists() and self._path.stat().st_size > 0:
                    with open(self._path, "rb") as f:
                        f.seek(-1, 2)
                        needs_newline = f.read(1) != b"\n"
                with open(self._path, "a", newline="") as f:
                    if needs_newline:
                        f.write("\n")
                    pd.DataFrame(fresh).reindex(columns=header).to_csv(f, header=not columns, index=False)
            self._set("_columns", tuple(header))
            self._set("_pending", ())
            return len(fresh)
