# ADR 0020: the public core is canonical

- Status: Accepted
- Date: 2026-11-17

## Context

The private repo runs on a server with cron and a VPN namespace. The package
must stay useful to strangers while the private repo keeps running unchanged.
A one-time copy with no sync path would silently drift.

## Decision

1. This package is canonical for the code it ships: the core lane, filters,
   notify and packaging.
2. The private repo consumes it by porting through `MANIFEST.txt` and
   `SOURCE_COMMIT`; a divergence shows up as a manifest diff, not as a mystery.
3. `bin/sync-core` is deliberately not shipped yet. If porting becomes routine,
   add it with a recorded ADR rather than a silent submodule switch.
4. The private repo keeps its own resume lane, mobs, watchdog and integrity
   audit apparatus; none of that is a reason to fork this core.

## Check

`SOURCE_COMMIT` and `MANIFEST.txt` are present and `PROVENANCE.md` carries the
manifest hash; `bin/check.sh` fails if either disappears.
