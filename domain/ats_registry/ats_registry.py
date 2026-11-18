"""AtsRegistry noun: the employer boards the ATS poller reads, the custom
domains that front a Greenhouse board, and every posting the poller handed on
(adrs/0015).

An append-only JSONL file (ats_registry.jsonl, gitignored), one event per
line. A board is added only after its public API answered 200 for it, so the
poller never polls a guess. A posting is marked emitted once, after its CSV
row was written, with when it was detected and when the ATS says it was first
published; bin/edge-report reads detection age and source from these lines.
Each writer (bin/ats-registry build, bin/ats-poll) holds its own flock, so
one process appends a given kind at a time.
"""

import json
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from types import MappingProxyType

import os

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "primitives"))
sys.path.insert(0, str(ROOT / "values"))
from write import _load, _write  # noqa: E402  (interior primitives)
from ats import ATSES  # noqa: E402

HOME = Path(os.environ.get("JOBKIT_DATA") or ROOT / "data") / "ats_registry.jsonl"


class AtsRegistry:
    """State changes only through add_board(), add_host() and mark_emitted()."""

    def __init__(self, path: Path = HOME) -> None:
        self._set("_path", Path(path))
        self._set("_mutex", threading.Lock())
        boards, hosts, emitted = {}, {}, {}
        raw = _load(self._path)
        for n, line in enumerate((raw or b"").decode("utf-8", "replace").splitlines(), 1):
            if not line.strip():
                continue
            try:
                e = json.loads(line)
                kind = e["kind"]
                if kind == "board":
                    boards.setdefault((e["ats"], e["tenant"]), e)
                elif kind == "host":
                    hosts.setdefault(e["host"], e["tenant"])
                elif kind == "emitted":
                    emitted.setdefault((e["ats"], e["tenant"], e["job_id"]), e)
            except (ValueError, KeyError, TypeError):
                print(f"⚠️ ats_registry.jsonl line {n} unreadable, skipped: {line[:120]!r}")
        self._set("_boards", boards)
        self._set("_hosts", hosts)
        self._set("_emitted", emitted)

    def __setattr__(self, name, value):
        raise AttributeError(f"AtsRegistry changes only through its verbs; refusing to set {name!r}")

    def _set(self, name, value) -> None:
        object.__setattr__(self, name, value)

    def _append(self, event: dict) -> dict:
        event.setdefault("at", datetime.now(timezone.utc).isoformat(timespec="seconds"))
        _write(self._path, (json.dumps(event, sort_keys=True) + "\n").encode())
        return event

    def add_board(self, ats: str, tenant: str, *, verified_status: int, site: str = None, host: str = None,
                  company: str = "", source: str = "") -> bool:
        """Register a board whose public API answered 200. False if known."""
        # nlc:rule=R-registry-verified-once  # nlc:obligation=a board enters the registry only after its public API answered 200, once per (ats, tenant); a posting is marked emitted at most once
        if ats not in ATSES:
            raise ValueError(f"unknown ATS {ats!r}")
        if not tenant or not isinstance(tenant, str):
            raise ValueError("empty tenant")
        if verified_status != 200:
            raise ValueError(f"unverified board {ats}:{tenant} (status {verified_status!r})")
        if ats == "workday" and not (site and host):
            raise ValueError("a Workday board needs its site and host")
        with self._mutex:
            if (ats, tenant) in self._boards:
                return False
            self._boards[(ats, tenant)] = self._append(dict(kind="board", ats=ats, tenant=tenant, site=site, host=host,
                                                            company=company, verified_status=200, source=source))
            return True

    def add_host(self, host: str, tenant: str, *, verified_status: int, source: str = "") -> bool:
        """Map a custom domain to the Greenhouse board behind it (the embed
        redirect named the board and its API answered 200). False if known."""
        if not host or not tenant:
            raise ValueError("empty host or board")
        if verified_status != 200:
            raise ValueError(f"unverified host {host} (status {verified_status!r})")
        host = host.lower()
        with self._mutex:
            if ("greenhouse", tenant) not in self._boards:
                raise ValueError(f"host {host} names greenhouse:{tenant}, which is not a registered board")
            if host in self._hosts:
                return False
            self._append(dict(kind="host", host=host, tenant=tenant, verified_status=200, source=source))
            self._hosts[host] = tenant
            return True

    def mark_emitted(self, ats: str, tenant: str, job_id: str, *, key: str, detected_at: str,
                     first_published: str = None, lane: str = "") -> bool:
        """Record a posting the poller wrote to a scrape CSV. False if it was
        already emitted."""
        job_id = str(job_id)
        if not key or not detected_at:
            raise ValueError("an emitted posting needs its key and detection time")
        with self._mutex:
            if (ats, tenant) not in self._boards:
                raise ValueError(f"{ats}:{tenant} is not a registered board")
            if (ats, tenant, job_id) in self._emitted:
                return False
            self._emitted[(ats, tenant, job_id)] = self._append(dict(
                kind="emitted", ats=ats, tenant=tenant, job_id=job_id, key=key, detected_at=detected_at,
                first_published=first_published, lane=lane))
            return True

    def boards(self) -> tuple:
        with self._mutex:
            return tuple(MappingProxyType(dict(b)) for b in self._boards.values())

    def hosts(self) -> MappingProxyType:
        with self._mutex:
            return MappingProxyType(dict(self._hosts))

    def emitted(self) -> tuple:
        with self._mutex:
            return tuple(MappingProxyType(dict(e)) for e in self._emitted.values())

    def emitted_keys(self) -> frozenset:
        with self._mutex:
            return frozenset(e["key"] for e in self._emitted.values())

    def emitted_since(self, iso: str) -> int:
        """How many postings were emitted at or after an ISO 8601 UTC time."""
        with self._mutex:
            return sum(1 for e in self._emitted.values() if str(e.get("detected_at", "")) >= iso)

    def __len__(self) -> int:
        with self._mutex:
            return len(self._boards)
