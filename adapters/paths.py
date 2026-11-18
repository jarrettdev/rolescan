"""Where this package keeps state. One variable, one default.

Everything the kit writes at runtime lives under JOBKIT_DATA (default ./data):
the ledger, the ATS registry, the drop folder, candidates, locks and debug files.
Nothing writes to the repository root.
"""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def data_root() -> Path:
    """The state directory; created on first use."""
    root = Path(os.environ.get("JOBKIT_DATA") or ROOT / "data")
    root.mkdir(parents=True, exist_ok=True)
    return root


def data_path(name: str) -> Path:
    path = data_root() / name
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def filters_path() -> Path:
    """The active filters document: JOBKIT_FILTERS, else filters/active.json, else the example."""
    explicit = os.environ.get("JOBKIT_FILTERS")
    if explicit:
        return Path(explicit)
    active = ROOT / "filters" / "active.json"
    return active if active.exists() else ROOT / "filters" / "example.json"
