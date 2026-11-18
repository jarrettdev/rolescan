"""LinkedinCache noun (adrs/0008): which LinkedIn company page belongs to a
company, so the scraper fetches each company once.

Hits only: a key is a lowercased company name and its value is
linkedin.com/company/<slug>. A miss may be a rate-limited search engine, so
it is never stored. remember() is the only mutation; it rewrites the file
atomically through the interior primitive, keeping the plain {key: value}
JSON the file has always had.
"""

import json
import sys
from pathlib import Path
from types import MappingProxyType

import os

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "primitives"))
sys.path.insert(0, str(ROOT / "values"))
from write import _load, _replace  # noqa: E402  (interior primitives)
from linkedin import cache_key, is_company_page  # noqa: E402

def _default_home() -> Path:
    from adapters import paths
    return paths.data_path("linkedin_cache.json")


class LinkedinCache:
    def __init__(self, path: Path | None = None) -> None:
        self._set("_path", Path(path) if path else _default_home())
        raw = _load(self._path)
        try:
            data = json.loads(raw) if raw else {}
        except ValueError:
            data = {}
        # entries that break the hits-only rule are not carried forward
        self._set("_entries", MappingProxyType({cache_key(k): v for k, v in data.items()
                                                if cache_key(k) and is_company_page(v)}))

    def __setattr__(self, name, value):
        raise AttributeError(f"LinkedinCache changes only through remember(); refusing to set {name!r}")

    def _set(self, name, value) -> None:
        object.__setattr__(self, name, value)

    def __len__(self) -> int:
        return len(self._entries)

    def get(self, company: str):
        """The cached page for this company, or None."""
        return self._entries.get(cache_key(company))

    def remember(self, company: str, page: str) -> bool:
        """Store a hit. True if it was new or changed. Raises ValueError for an
        empty company or a value that is not a LinkedIn company page."""
        key = cache_key(company)
        if not key:
            raise ValueError("empty company name")
        if not is_company_page(page):
            raise ValueError(f"not a LinkedIn company page: {page!r}")
        if self._entries.get(key) == page:
            return False
        entries = {**self._entries, key: page}
        _replace(self._path, json.dumps(entries, indent=0, sort_keys=True).encode())
        self._set("_entries", MappingProxyType(entries))
        return True
