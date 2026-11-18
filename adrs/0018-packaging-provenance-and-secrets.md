# ADR 0018: packaging, provenance and the secrets boundary

- Status: Accepted
- Date: 2026-11-17

## Context

This package is a copy of `job_scraper` for redistribution. The source repo is
private, cron-driven and coupled to one owner's Discord ids, resume and hosts.
A copy with no provenance rots; a copy with a secret leaks.

## Decision

1. `MANIFEST.txt` lists every path copied and `SOURCE_COMMIT` names the source
   repo and commit. `PROVENANCE.md` records the manifest hash and copy date.
2. A fresh git history. The source history is never published; it contains the
   owner's ids even though no live token appears in it.
3. No credential value ships. `.env` is gitignored, `.env.example` holds empty
   values, a missing or blank value is a named error, and `bin/secret-scan`
   runs inside `bin/check.sh`.
4. State lives under `JOBKIT_DATA` (default `./data`, gitignored). A run writes
   nothing to the repository root.
5. The public copy is the canonical core (ADR 0020). Upstream fixes are ported
   through the manifest, not by merging histories.

## Rules

- **R-no-private-identifiers**: no owner id, private host path or private note
  path in the tree (enforced by `bin/secret-scan`).
- **R-no-credential-values**: no token shape in the tree (same scan).

## Check

`bin/secret-scan` exits 0; `git grep` for the owner id and `/home/` host paths
exits 1.
