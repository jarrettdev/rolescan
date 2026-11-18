# ADR 0021: NLC scope in this package

- Status: Accepted
- Date: 2026-11-17

## Context

The source repo adopts NLC fully, including a C1–C26 release audit built from
`integrity/audits/`, `integrity/binding-matrix.json` and repo-local
`tools/fitness-*.py`. Those audits judge the resume lane, the mobs and the
owner's operating rules. Shipping them here would audit code that is not in
the package.

## Decision

1. This package keeps NLC where it is deterministic and useful to a stranger:
   `goals/*` with input/output/failure schemas, `rules/adopted.json` with
   `nlc:rule=` markers, `.nlc/rule-ir.snapshot.json`, `.nlc/verb-primitives.json`
   and the compiler pin (0.8.0).
2. `bin/check-nlc.sh` runs `rule-coverage --check`, `rule-runner --check` and
   `call-tree --check`. All three are offline and tree-local.
3. The release profile (`nlc verify-deep`, H-CONFIRM and the AI-* gates) is
   **not claimed** here. An adopter who wants it adds their own `integrity/`
   profile; the private repo's profile is not redistributable.
4. The resume-lane rules are pruned from `adopted.json` and `enforced_by.json`
   rather than left dangling: coverage fails on a rule whose only marker is in
   deleted code.

## Consequences

- An agent sees real, checkable rules and a goal contract without inheriting
  the owner's audit apparatus.
- `nlc verify-deep` is expected to fail in this tree; documents say so, so the
  failure is information rather than a mystery.

## Check

`bin/check-nlc.sh` prints `NLC:MET`; `./nlc maintainer rule-coverage --check`
lists every adopted rule against a file that exists.
